"""Buyer-facing catalog: products, filters, shops, nearest shops with a size, availability."""
from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..auth import current_visitor
from ..models import Product, Shop, Variant, db
from ..services import (expire_reservations, product_card, public_products_query, record_event,
                        reserved_counts)
from ..utils import CATEGORIES, COLORS, error, haversine_km, norm_size, norm_text, parse_float, parse_int, size_key

bp = Blueprint("catalog", __name__, url_prefix="/api")

SORTS = ("relevance", "new", "price_asc", "price_desc", "near")


def _filters():
    args = request.args
    lat = parse_float(args.get("lat"), -90, 90)
    lng = parse_float(args.get("lng"), -180, 180)
    return {
        "q": norm_text(args.get("q", ""))[:80],
        "categories": [c for c in args.get("category", "").split(",") if c][:8],
        "colors": [c for c in args.get("color", "").split(",") if c][:8],
        "size": norm_size(args.get("size", "")),
        "min_price": parse_int(args.get("min_price"), None, 0),
        "max_price": parse_int(args.get("max_price"), None, 0),
        "shop": args.get("shop", "").strip()[:80],
        "in_stock": args.get("in_stock", "1") != "0",
        "point": (lat, lng) if lat is not None and lng is not None else None,
        "radius_km": parse_float(args.get("radius_km"), 0.1, 200),
    }


def find_products(s, f):
    """Products matching the filters, with availability. Returns (product, reserved, distance) tuples."""
    expire_reservations(s)
    query = public_products_query().options(selectinload(Product.variants), selectinload(Product.shop))
    for word in f["q"].split()[:6]:
        query = query.where(Product.search_text.contains(word, autoescape=True))
    if f["categories"]:
        query = query.where(Product.category.in_(f["categories"]))
    if f["colors"]:
        query = query.where(Product.color.in_(f["colors"]))
    if f["min_price"] is not None:
        query = query.where(Product.price >= f["min_price"])
    if f["max_price"] is not None:
        query = query.where(Product.price <= f["max_price"])
    if f["shop"]:
        query = query.where((Shop.slug == f["shop"]) if not f["shop"].isdigit() else (Shop.id == int(f["shop"])))
    products = s.scalars(query).unique().all()
    reserved = reserved_counts(s, [v.id for p in products for v in p.variants])
    out = []
    for p in products:
        variants = p.variants
        if f["size"]:
            variants = [v for v in variants if v.size == f["size"]]
            if not variants:
                continue
        if f["in_stock"] and not any(v.stock - reserved.get(v.id, 0) > 0 for v in variants):
            continue
        distance = None
        if f["point"] and p.shop.lat is not None:
            distance = haversine_km(f["point"][0], f["point"][1], p.shop.lat, p.shop.lng)
            if f["radius_km"] and distance > f["radius_km"]:
                continue
        elif f["point"] and f["radius_km"]:
            continue
        out.append((p, reserved, distance))
    return out


def _sort(rows, sort, q):
    if sort == "price_asc":
        rows.sort(key=lambda r: r[0].price)
    elif sort == "price_desc":
        rows.sort(key=lambda r: -r[0].price)
    elif sort == "near":
        rows.sort(key=lambda r: (r[2] is None, r[2] or 0))
    elif sort == "new" or not q:
        rows.sort(key=lambda r: r[0].created_at, reverse=True)
    else:  # relevance: name matches first
        rows.sort(key=lambda r: (not all(w in norm_text(r[0].name) for w in q.split()), r[0].price))
    return rows


@bp.get("/meta")
def meta():
    s = db()
    cfg = current_app.config["CLOTHES"]
    base = public_products_query().subquery()
    lo, hi = s.execute(select(func.min(base.c.price), func.max(base.c.price))).one()
    categories = dict(s.execute(select(base.c.category, func.count()).group_by(base.c.category)).all())
    colors = [c for (c,) in s.execute(select(base.c.color).distinct()) if c]
    sizes = sorted({sz for (sz,) in s.execute(select(Variant.size).join(base, base.c.id == Variant.product_id))},
                   key=lambda x: (size_key(x), int(x) if x.isdigit() else 0))
    demo = bool(s.scalar(select(func.count(Shop.id)).where(Shop.is_demo.is_(True), Shop.status == "active")))
    return jsonify(
        categories=[{"name": c, "count": categories[c]} for c in CATEGORIES if c in categories]
        + [{"name": c, "count": n} for c, n in categories.items() if c not in CATEGORIES],
        colors=[c for c in COLORS if c in colors] + [c for c in colors if c not in COLORS],
        sizes=sizes, price={"min": lo or 0, "max": hi or 0}, demo=demo,
        features={"tryon": cfg.TRYON_PROVIDER != "none", "tryon_demo": cfg.TRYON_PROVIDER == "demo",
                  "telegram_bot": cfg.TELEGRAM_BOT_USERNAME or None,
                  "photo_retention_hours": cfg.PHOTO_RETENTION_HOURS,
                  "reservation_confirm_hours": cfg.RESERVATION_CONFIRM_HOURS,
                  "reservation_hold_hours": cfg.RESERVATION_HOLD_HOURS},
    )


@bp.get("/products")
def products():
    f = _filters()
    sort = request.args.get("sort", "relevance")
    if sort not in SORTS:
        sort = "relevance"
    limit = parse_int(request.args.get("limit"), 24, 1, 60)
    offset = parse_int(request.args.get("offset"), 0, 0, 100_000)
    rows = _sort(find_products(db(), f), sort, f["q"])
    page = rows[offset:offset + limit]
    return jsonify(items=[product_card(p, r, d) for p, r, d in page], total=len(rows),
                   offset=offset, limit=limit, demo=any(p.shop.is_demo for p, _, _ in page))


@bp.get("/products/<int:product_id>")
def product_detail(product_id):
    s = db()
    expire_reservations(s)
    p = s.scalar(public_products_query().where(Product.id == product_id)
                 .options(selectinload(Product.variants), selectinload(Product.shop)))
    if p is None:
        return error("Mahsulot topilmadi.", 404, "NOT_FOUND")
    reserved = reserved_counts(s, [v.id for v in p.variants])
    point = (parse_float(request.args.get("lat"), -90, 90), parse_float(request.args.get("lng"), -180, 180))
    distance = haversine_km(*point, p.shop.lat, p.shop.lng) if None not in point and p.shop.lat is not None else None
    data = product_card(p, reserved, distance)
    data["shop"] = p.shop.public(distance)
    similar = s.scalars(public_products_query().where(Product.category == p.category, Product.id != p.id)
                        .options(selectinload(Product.variants), selectinload(Product.shop))
                        .order_by(func.abs(Product.price - p.price)).limit(8)).all()
    sim_reserved = reserved_counts(s, [v.id for x in similar for v in x.variants])
    data["similar"] = [product_card(x, sim_reserved) for x in similar][:4]
    record_event(s, "view", p.shop_id, p.id, current_visitor(), dedupe_hours=12)
    s.commit()
    return jsonify(data)


@bp.get("/shops")
def shops():
    """Active shops; with product filters (q/category/size/...) only shops that have a match."""
    s = db()
    f = _filters()
    filtered = any([f["q"], f["categories"], f["colors"], f["size"], f["min_price"], f["max_price"]])
    counts = {}
    if filtered:
        for p, _, _ in find_products(s, f):
            counts[p.shop_id] = counts.get(p.shop_id, 0) + 1
    else:
        counts = dict(s.execute(select(Product.shop_id, func.count()).where(Product.active.is_(True))
                                .group_by(Product.shop_id)).all())
    items = []
    for shop in s.scalars(select(Shop).where(Shop.status == "active")):
        if filtered and shop.id not in counts:
            continue
        distance = None
        if f["point"] and shop.lat is not None:
            distance = haversine_km(f["point"][0], f["point"][1], shop.lat, shop.lng)
            if f["radius_km"] and distance > f["radius_km"]:
                continue
        item = shop.public(distance)
        item["matches"] = counts.get(shop.id, 0)
        items.append(item)
    items.sort(key=lambda x: (x.get("distance_km") is None, x.get("distance_km") or 0, x["name"]))
    return jsonify(items=items, demo=any(x["demo"] for x in items))


@bp.get("/shops/<slug>")
def shop_detail(slug):
    s = db()
    shop = s.scalar(select(Shop).where(Shop.slug == slug, Shop.status == "active"))
    if shop is None:
        return error("Doʻkon topilmadi.", 404, "NOT_FOUND")
    f = _filters()
    f["shop"], f["in_stock"] = shop.slug, False
    rows = _sort(find_products(s, f), "new", "")
    return jsonify(shop=shop.public(), items=[product_card(p, r, with_shop=False) for p, r, _ in rows])


@bp.get("/availability")
def availability():
    s = db()
    expire_reservations(s)
    product_id = parse_int(request.args.get("product_id"))
    p = s.scalar(public_products_query().where(Product.id == product_id)) if product_id else None
    if p is None:
        return error("Mahsulot topilmadi.", 404, "NOT_FOUND")
    size = norm_size(request.args.get("size", ""))
    variant = next((v for v in p.variants if v.size == size), None)
    if variant is None:
        return error("Bu oʻlcham mavjud emas.", 400, "NO_SIZE")
    reserved = reserved_counts(s, [variant.id])
    return jsonify(shop=p.shop.public(), size=size, available=max(0, variant.stock - reserved.get(variant.id, 0)),
                   demo=p.shop.is_demo)
