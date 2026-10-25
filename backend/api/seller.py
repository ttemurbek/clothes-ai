"""Seller panel API: account, shop profile, products and stock, photos, reservations, statistics."""
import secrets
import uuid

from flask import Blueprint, current_app, jsonify, request, session
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from werkzeug.security import check_password_hash, generate_password_hash

from .. import photo
from ..auth import current_seller, seller_required
from ..images import ImageError, load_image, save_webp
from ..models import Product, Reservation, Seller, Shop, Variant, db
from ..security import rate_limit
from ..seed import product_search_text
from ..services import (apply_seller_action, expire_reservations, product_card, reservation_public,
                        reserved_counts, shop_stats, sort_sizes)
from ..utils import (CATEGORIES, COLORS, GENDERS, OCCASIONS, SEASONS, clean_str, csv_values, error, norm_size,
                     normalize_phone, parse_float, parse_int)

bp = Blueprint("seller", __name__, url_prefix="/api/seller")

_DUMMY_HASH = generate_password_hash(secrets.token_hex(8))
SHOP_FIELDS = {"name": 120, "district": 80, "address": 255, "hours": 64, "instagram": 80, "description": 1000}


def _slugify(name):
    base = "".join(ch if ch.isalnum() else "-" for ch in name.lower().encode("ascii", "ignore").decode())
    base = "-".join(filter(None, base.split("-")))[:50] or "dokon"
    return f"{base}-{secrets.token_hex(2)}"


def _me(seller):
    shop = seller.shop
    cfg = current_app.config["CLOTHES"]
    return {
        "seller": {"id": seller.id, "login": seller.login, "name": seller.name},
        "shop": {**shop.public(), "status": shop.status, "telegram_linked": bool(shop.telegram_chat_id)},
        "options": {"categories": CATEGORIES, "colors": COLORS,
                    "genders": [{"key": k, "label": v} for k, v in GENDERS.items()],
                    "seasons": [{"key": k, "label": v} for k, v in SEASONS.items()],
                    "occasions": [{"key": k, "label": v} for k, v in OCCASIONS.items()],
                    "ai_photo": cfg.PHOTO_PROVIDER != "none",
                    "telegram_bot": cfg.TELEGRAM_BOT_USERNAME or None},
    }


# ---------- account ----------

@bp.post("/register")
def register():
    limited = rate_limit("register", 5, 3600)
    if limited:
        return limited
    data = request.get_json(silent=True) or {}
    login = clean_str(data.get("login"), 120).lower()
    password = str(data.get("password") or "")
    shop_name = clean_str(data.get("shop_name"), 120)
    phone = normalize_phone(data.get("phone"))
    if len(login) < 5 or ("@" not in login and not normalize_phone(login)):
        return error("Login sifatida email yoki telefon raqam yozing.", 400, "LOGIN_INVALID")
    if len(password) < 8:
        return error("Parol kamida 8 belgidan iborat boʻlsin.", 400, "PASSWORD_SHORT")
    if len(shop_name) < 2:
        return error("Doʻkon nomini yozing.", 400, "SHOP_NAME_REQUIRED")
    if not phone:
        return error("Doʻkon telefon raqamini +998 XX XXX XX XX koʻrinishida yozing.", 400, "PHONE_INVALID")
    if not data.get("agree"):
        return error("Shartlarga rozilik bering.", 400, "CONSENT_REQUIRED")
    if normalize_phone(login):
        login = normalize_phone(login)
    s = db()
    shop = Shop(slug=_slugify(shop_name), name=shop_name, phone=phone, status="pending",
                district=clean_str(data.get("district"), 80), address=clean_str(data.get("address"), 255))
    seller = Seller(shop=shop, login=login, name=clean_str(data.get("name"), 120),
                    password_hash=generate_password_hash(password))
    s.add_all([shop, seller])
    try:
        s.commit()
    except IntegrityError:
        s.rollback()
        return error("Bu login bilan hisob allaqachon bor.", 409, "LOGIN_TAKEN")
    session.clear()
    session["seller_id"] = seller.id
    session.permanent = True
    return jsonify(_me(seller)), 201


@bp.post("/login")
def login():
    limited = rate_limit("login", 10, 900)
    if limited:
        return limited
    data = request.get_json(silent=True) or {}
    login_value = clean_str(data.get("login"), 120).lower()
    login_value = normalize_phone(login_value) or login_value
    seller = db().scalar(select(Seller).where(Seller.login == login_value))
    ok = check_password_hash(seller.password_hash if seller else _DUMMY_HASH, str(data.get("password") or ""))
    if not seller or not ok:
        return error("Login yoki parol notoʻgʻri.", 401, "BAD_CREDENTIALS")
    session.clear()
    session["seller_id"] = seller.id
    session.permanent = True
    return jsonify(_me(seller))


@bp.post("/logout")
def logout():
    session.pop("seller_id", None)
    return jsonify(ok=True)


@bp.get("/me")
def me():
    seller = current_seller()
    if seller is None:
        return error("Avval tizimga kiring.", 401, "AUTH_REQUIRED")
    return jsonify(_me(seller))


@bp.post("/password")
@seller_required
def change_password(seller):
    data = request.get_json(silent=True) or {}
    if not check_password_hash(seller.password_hash, str(data.get("current") or "")):
        return error("Joriy parol notoʻgʻri.", 400, "BAD_CREDENTIALS")
    new = str(data.get("new") or "")
    if len(new) < 8:
        return error("Parol kamida 8 belgidan iborat boʻlsin.", 400, "PASSWORD_SHORT")
    seller.password_hash = generate_password_hash(new)
    db().commit()
    return jsonify(ok=True)


# ---------- shop profile ----------

@bp.patch("/shop")
@seller_required
def update_shop(seller):
    data = request.get_json(silent=True) or {}
    shop = seller.shop
    for field, limit in SHOP_FIELDS.items():
        if field in data:
            setattr(shop, field, clean_str(data[field], limit))
    if len(shop.name) < 2:
        return error("Doʻkon nomini yozing.", 400, "SHOP_NAME_REQUIRED")
    if "phone" in data:
        phone = normalize_phone(data["phone"])
        if not phone:
            return error("Telefon raqami notoʻgʻri.", 400, "PHONE_INVALID")
        shop.phone = phone
    if "lat" in data or "lng" in data:
        lat, lng = parse_float(data.get("lat"), 37, 46), parse_float(data.get("lng"), 55, 74)
        if lat is None or lng is None:
            return error("Xaritada Oʻzbekiston ichidagi nuqtani tanlang.", 400, "LOCATION_INVALID")
        shop.lat, shop.lng = round(lat, 6), round(lng, 6)
    s = db()
    for product in shop.products:
        product.search_text = product_search_text(product, shop)
    s.commit()
    return jsonify(_me(seller))


@bp.post("/shop/telegram-link")
@seller_required
def telegram_link(seller):
    cfg = current_app.config["CLOTHES"]
    if not cfg.TELEGRAM_BOT_USERNAME:
        return error("Telegram bot hali sozlanmagan.", 503, "BOT_NOT_CONFIGURED")
    seller.shop.link_code = secrets.token_hex(8)
    db().commit()
    return jsonify(url=f"https://t.me/{cfg.TELEGRAM_BOT_USERNAME}?start=link_{seller.shop.link_code}")


# ---------- products ----------

def _own_product(seller, product_id):
    product = db().get(Product, product_id)
    return product if product is not None and product.shop_id == seller.shop_id else None


def _seller_card(product):
    reserved = reserved_counts(db(), [v.id for v in product.variants])
    card = product_card(product, reserved, with_shop=False)
    card["active"] = product.active
    card["variants"] = [{"size": v.size, "stock": v.stock, "reserved": reserved.get(v.id, 0)}
                        for v in product.variants]
    return card


def _apply_product(product, data):
    if "name" in data:
        product.name = clean_str(data["name"], 160)
    if "category" in data:
        product.category = clean_str(data["category"], 60)
    if "color" in data:
        product.color = clean_str(data["color"], 40)
    if "description" in data:
        product.description = clean_str(data["description"], 2000)
    if "price" in data:
        product.price = parse_int(data["price"], -1, 0, 1_000_000_000)
    if "active" in data:
        product.active = bool(data["active"])
    if "gender" in data:
        product.gender = data["gender"] if data["gender"] in GENDERS else "unisex"
    if "seasons" in data:
        product.seasons = csv_values(data["seasons"], SEASONS)
    if "occasions" in data:
        product.occasions = csv_values(data["occasions"], OCCASIONS)
    if "warmth" in data:
        product.warmth = parse_int(data["warmth"], 0, 0, 3)
    if len(product.name or "") < 2:
        return "Mahsulot nomini yozing."
    if not product.category:
        return "Kategoriyani tanlang."
    if product.price is None or product.price <= 0:
        return "Narxni soʻmda yozing."
    if "variants" in data:
        return _apply_variants(product, data["variants"])
    return None


def _apply_variants(product, variants):
    if not isinstance(variants, list) or not 1 <= len(variants) <= 20:
        return "Kamida bitta oʻlcham qoʻshing (20 tagacha)."
    existing = {v.size: v for v in product.variants}
    wanted = {norm_size(item.get("size")) for item in variants if isinstance(item, dict)}
    dropped = [v.id for size, v in existing.items() if size not in wanted and v.id]
    if dropped and reserved_counts(db(), dropped):
        return "Faol broni bor oʻlchamni oʻchirib boʻlmaydi — qoldiqni 0 qiling."
    keep = []
    for item in variants:
        if not isinstance(item, dict):
            return "Oʻlchamlar notoʻgʻri."
        size = norm_size(item.get("size"))
        stock = parse_int(item.get("stock"), None, 0, 9999)
        if not size or stock is None:
            return "Har bir oʻlcham uchun nom va qoldiq (0–9999) yozing."
        if size in [v.size for v in keep]:
            return f"{size} oʻlchami ikki marta yozilgan."
        variant = existing.get(size) or Variant(size=size)
        variant.stock = stock
        keep.append(variant)
    for i, v in enumerate(sort_sizes(keep)):
        v.position = i
    product.variants = sort_sizes(keep)
    return None


@bp.get("/products")
@seller_required
def list_products(seller):
    s = db()
    expire_reservations(s)
    rows = s.scalars(select(Product).where(Product.shop_id == seller.shop_id)
                     .options(selectinload(Product.variants)).order_by(Product.created_at.desc())).all()
    return jsonify(items=[_seller_card(p) for p in rows])


@bp.post("/products")
@seller_required
def create_product(seller):
    data = request.get_json(silent=True) or {}
    if "variants" not in data:
        return error("Kamida bitta oʻlcham qoʻshing.", 400, "VALIDATION")
    s = db()
    if s.scalar(select(func.count(Product.id)).where(Product.shop_id == seller.shop_id)) >= 2000:
        return error("Mahsulotlar soni chegarasiga yetildi.", 400, "LIMIT")
    product = Product(shop_id=seller.shop_id, name="", category="", price=0)
    problem = _apply_product(product, data)
    if problem:
        return error(problem, 400, "VALIDATION")
    product.search_text = product_search_text(product, seller.shop)
    s.add(product)
    s.commit()
    return jsonify(product=_seller_card(product)), 201


@bp.patch("/products/<int:product_id>")
@seller_required
def update_product(seller, product_id):
    product = _own_product(seller, product_id)
    if product is None:
        return error("Mahsulot topilmadi.", 404, "NOT_FOUND")
    s = db()
    problem = _apply_product(product, request.get_json(silent=True) or {})
    if problem:
        s.rollback()
        return error(problem, 400, "VALIDATION")
    product.search_text = product_search_text(product, seller.shop)
    s.commit()
    return jsonify(product=_seller_card(product))


@bp.delete("/products/<int:product_id>")
@seller_required
def delete_product(seller, product_id):
    product = _own_product(seller, product_id)
    if product is None:
        return error("Mahsulot topilmadi.", 404, "NOT_FOUND")
    s = db()
    active = s.scalar(select(func.count(Reservation.id)).where(
        Reservation.product_id == product.id, Reservation.status.in_(("pending", "confirmed"))))
    if active:
        return error("Bu mahsulotda faol bron bor. Avval bronlarni yakunlang yoki mahsulotni yashiring.",
                     409, "HAS_RESERVATIONS")
    image = product.image
    s.delete(product)
    s.commit()
    _remove_image(image)
    return jsonify(ok=True)


def _media_dir():
    return current_app.config["CLOTHES"].DATA_DIR / "media" / "products"


def _remove_image(name):
    if name:
        (_media_dir() / name).unlink(missing_ok=True)


@bp.post("/products/<int:product_id>/image")
@seller_required
def upload_image(seller, product_id):
    limited = rate_limit("upload", 60, 3600)
    if limited:
        return limited
    product = _own_product(seller, product_id)
    if product is None:
        return error("Mahsulot topilmadi.", 404, "NOT_FOUND")
    file = request.files.get("image")
    if file is None or not file.filename:
        return error("Rasm tanlanmagan.", 400, "NO_FILE")
    cfg = current_app.config["CLOTHES"]
    try:
        image = load_image(file.stream, cfg.MAX_IMAGE_PIXELS)
    except ImageError as exc:
        return error(str(exc), 415, "BAD_IMAGE")
    ai_used, ai_note = False, None
    if request.form.get("ai") == "1":
        try:
            image = photo.studio(image, cfg)
            ai_used = True
        except photo.PhotoError as exc:
            ai_note = str(exc)
    name = f"{uuid.uuid4().hex}.webp"
    save_webp(image.convert("RGBA") if image.mode == "RGBA" else image, _media_dir() / name,
              cfg.PRODUCT_IMAGE_SIZE)
    old, product.image = product.image, name
    product.photo_credit = ""
    db().commit()
    _remove_image(old)
    return jsonify(product=_seller_card(product), ai_used=ai_used, ai_note=ai_note)


@bp.delete("/products/<int:product_id>/image")
@seller_required
def delete_image(seller, product_id):
    product = _own_product(seller, product_id)
    if product is None:
        return error("Mahsulot topilmadi.", 404, "NOT_FOUND")
    old, product.image = product.image, None
    db().commit()
    _remove_image(old)
    return jsonify(product=_seller_card(product))


# ---------- reservations and statistics ----------

@bp.get("/reservations")
@seller_required
def reservations(seller):
    s = db()
    expire_reservations(s)
    status = request.args.get("status", "")
    query = select(Reservation).where(Reservation.shop_id == seller.shop_id)
    if status == "active":
        query = query.where(Reservation.status.in_(("pending", "confirmed")))
    elif status:
        query = query.where(Reservation.status == status)
    rows = s.scalars(query.order_by(Reservation.created_at.desc()).limit(200)).all()
    pending = s.scalar(select(func.count(Reservation.id)).where(
        Reservation.shop_id == seller.shop_id, Reservation.status == "pending"))
    return jsonify(items=[reservation_public(r, for_seller=True) for r in rows], pending=pending)


@bp.post("/reservations/<int:reservation_id>/<action>")
@seller_required
def reservation_action(seller, reservation_id, action):
    s = db()
    r = s.get(Reservation, reservation_id)
    if r is None or r.shop_id != seller.shop_id:
        return error("Bron topilmadi.", 404, "NOT_FOUND")
    problem = apply_seller_action(s, r, action)
    if problem:
        return error(problem, 409, "BAD_STATE")
    return jsonify(reservation=reservation_public(r, for_seller=True))


@bp.get("/stats")
@seller_required
def stats(seller):
    days = parse_int(request.args.get("days"), 30, 1, 365)
    s = db()
    data = shop_stats(s, seller.shop_id, days)
    data["products"] = s.scalar(select(func.count(Product.id)).where(Product.shop_id == seller.shop_id))
    data["in_stock_units"] = s.scalar(select(func.coalesce(func.sum(Variant.stock), 0)).join(Product)
                                      .where(Product.shop_id == seller.shop_id)) or 0
    return jsonify(data)

