"""Buyer reservations: hold a size at a shop until the shop confirms; the sale happens in the shop."""
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request, session
from sqlalchemy import func, select

from ..auth import current_buyer, current_visitor, telegram_user
from ..models import ACTIVE_RESERVATION, Product, Reservation, db, utcnow
from ..security import rate_limit
from ..services import (expire_reservations, notify_shop_new, public_products_query, record_event,
                        reservation_public, reserved_counts)
from ..utils import clean_str, error, norm_size, normalize_phone, parse_int, token

bp = Blueprint("reservations", __name__, url_prefix="/api/reservations")


def _remember(code):
    codes = [c for c in session.get("reservations", []) if c != code][-19:]
    session["reservations"] = codes + [code]


@bp.post("")
def create():
    limited = rate_limit("reserve", 6, 600)
    if limited:
        return limited
    data = request.get_json(silent=True) or {}
    s = db()
    expire_reservations(s, force=True)
    product_id = parse_int(data.get("product_id"))
    product = s.scalar(public_products_query().where(Product.id == product_id)) if product_id else None
    if product is None:
        return error("Mahsulot topilmadi.", 404, "NOT_FOUND")
    size = norm_size(data.get("size", ""))
    variant = next((v for v in product.variants if v.size == size), None)
    if variant is None:
        return error("Oʻlchamni tanlang.", 400, "NO_SIZE")

    tg = telegram_user()
    name = clean_str(data.get("name") or (tg and tg.get("first_name")) or "", 120)
    if len(name) < 2:
        return error("Ismingizni yozing.", 400, "NAME_REQUIRED")
    phone = normalize_phone(data.get("phone"))
    if not phone:
        return error("Telefon raqamini +998 XX XXX XX XX koʻrinishida yozing.", 400, "PHONE_INVALID")
    if not data.get("agree"):
        return error("Ism va telefon doʻkonga yuborilishiga rozilik bering.", 400, "CONSENT_REQUIRED")

    visitor = current_visitor()
    active = s.scalar(select(func.count(Reservation.id)).where(
        Reservation.status.in_(ACTIVE_RESERVATION),
        (Reservation.visitor == visitor) | (Reservation.phone == phone)))
    cfg = current_app.config["CLOTHES"]
    if active >= cfg.MAX_ACTIVE_RESERVATIONS:
        return error(f"Bir vaqtda {cfg.MAX_ACTIVE_RESERVATIONS} tadan ortiq faol bron boʻlmaydi.", 409, "TOO_MANY")
    duplicate = s.scalar(select(Reservation).where(
        Reservation.variant_id == variant.id, Reservation.status.in_(ACTIVE_RESERVATION),
        (Reservation.visitor == visitor) | (Reservation.phone == phone)))
    if duplicate:
        return error("Bu oʻlchamni allaqachon bron qilgansiz.", 409, "DUPLICATE",
                     reservation=reservation_public(duplicate))
    if variant.stock - reserved_counts(s, [variant.id]).get(variant.id, 0) <= 0:
        return error("Afsuski, bu oʻlcham hozir qolmagan.", 409, "OUT_OF_STOCK")

    buyer = current_buyer()
    reservation = Reservation(
        code=token(18), shop_id=product.shop_id, product_id=product.id, variant_id=variant.id,
        buyer_id=buyer.id if buyer else None, visitor=visitor, name=name, phone=phone,
        note=clean_str(data.get("note"), 300),
        confirm_by=utcnow() + timedelta(hours=cfg.RESERVATION_CONFIRM_HOURS))
    s.add(reservation)
    record_event(s, "reservation", product.shop_id, product.id, visitor)
    s.commit()
    _remember(reservation.code)
    notify_shop_new(reservation)
    return jsonify(reservation=reservation_public(reservation),
                   shop_notified=bool(product.shop.telegram_chat_id and cfg.TELEGRAM_BOT_TOKEN)), 201


@bp.get("/mine")
def mine():
    s = db()
    expire_reservations(s)
    visitor = current_visitor()
    codes = session.get("reservations", [])
    extra = [c for c in request.args.get("codes", "").split(",") if 10 < len(c) < 41][:20]
    query = select(Reservation).where((Reservation.visitor == visitor) | Reservation.code.in_(codes + extra))
    rows = s.scalars(query.order_by(Reservation.created_at.desc()).limit(30)).all()
    return jsonify(items=[reservation_public(r) for r in rows])


def _by_code(code):
    return db().scalar(select(Reservation).where(Reservation.code == code)) if 10 < len(code) < 41 else None


@bp.get("/<code>")
def status(code):
    expire_reservations(db())
    r = _by_code(code)
    if r is None:
        return error("Bron topilmadi.", 404, "NOT_FOUND")
    return jsonify(reservation=reservation_public(r))


@bp.post("/<code>/cancel")
def cancel(code):
    r = _by_code(code)
    if r is None:
        return error("Bron topilmadi.", 404, "NOT_FOUND")
    if r.status not in ACTIVE_RESERVATION:
        return error("Bu bronni bekor qilib boʻlmaydi.", 409, "NOT_ACTIVE")
    r.status = "cancelled"
    db().commit()
    return jsonify(reservation=reservation_public(r))
