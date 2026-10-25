"""Inventory, reservations and statistics logic shared by the buyer, seller and bot code."""
import logging
import threading
import time
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import and_, func, select, update

from .models import ACTIVE_RESERVATION, Event, Product, Reservation, Shop, Variant, utcnow
from .telegram import Bot
from .utils import size_key

log = logging.getLogger(__name__)

STATUS_LABELS = {
    "pending": "Tasdiq kutilmoqda", "confirmed": "Tasdiqlandi — olib qoʻyildi",
    "declined": "Rad etildi", "expired": "Muddati tugadi", "cancelled": "Bekor qilindi",
    "visited": "Xaridor keldi", "sold": "Sotildi",
}


# ---------- reservations and stock ----------

_last_expiry = [0.0]


def expire_reservations(s, now=None, force=False):
    """Expire overdue reservations (at most every 15 s per process unless forced or testing)."""
    if not (force or now or current_app.config.get("TESTING")) and time.monotonic() - _last_expiry[0] < 15:
        return
    _last_expiry[0] = time.monotonic()
    now = now or utcnow()
    s.execute(update(Reservation).where(Reservation.status == "pending", Reservation.confirm_by < now)
              .values(status="expired", updated_at=now))
    s.execute(update(Reservation).where(Reservation.status == "confirmed", Reservation.hold_until < now)
              .values(status="expired", updated_at=now))
    s.commit()


def reserved_counts(s, variant_ids):
    if not variant_ids:
        return {}
    rows = s.execute(select(Reservation.variant_id, func.count()).where(
        Reservation.variant_id.in_(list(variant_ids)), Reservation.status.in_(ACTIVE_RESERVATION),
    ).group_by(Reservation.variant_id))
    return dict(rows.all())


def available(variant, reserved):
    return max(0, variant.stock - reserved.get(variant.id, 0))


def image_url(product):
    return f"/media/products/{product.image}" if product.image else None


def product_card(product, reserved, distance_km=None, with_shop=True):
    sizes = [{"size": v.size, "available": available(v, reserved)} for v in product.variants]
    data = {
        "id": product.id, "name": product.name, "category": product.category, "color": product.color,
        "price": product.price, "image": image_url(product), "description": product.description,
        "sizes": sizes, "available_sizes": [x["size"] for x in sizes if x["available"] > 0],
        "in_stock": any(x["available"] > 0 for x in sizes), "shop_id": product.shop_id,
        "demo": product.shop.is_demo,
    }
    if with_shop:
        data["shop"] = {"id": product.shop.id, "slug": product.shop.slug, "name": product.shop.name,
                        "district": product.shop.district, "verified": product.shop.public()["verified"],
                        "demo": product.shop.is_demo}
    if distance_km is not None:
        data["distance_km"] = round(distance_km, 2)
    return data


def public_products_query():
    return (select(Product).join(Shop).where(Product.active.is_(True), Shop.status == "active"))


def sort_sizes(variants):
    return sorted(variants, key=lambda v: (size_key(v.size), int(v.size) if v.size.isdigit() else 0))


# ---------- events / statistics ----------

def record_event(s, kind, shop_id=None, product_id=None, visitor="", dedupe_hours=0):
    if dedupe_hours and visitor:
        since = utcnow() - timedelta(hours=dedupe_hours)
        exists = s.scalar(select(Event.id).where(Event.kind == kind, Event.product_id == product_id,
                                                 Event.visitor == visitor, Event.created_at >= since).limit(1))
        if exists:
            return
    s.add(Event(kind=kind, shop_id=shop_id, product_id=product_id, visitor=visitor))


def shop_stats(s, shop_id, days):
    since = utcnow() - timedelta(days=days)
    where = and_(Event.shop_id == shop_id, Event.created_at >= since)
    totals = dict(s.execute(select(Event.kind, func.count()).where(where).group_by(Event.kind)).all())
    day = func.date(Event.created_at)
    series = {}
    for kind, d, n in s.execute(select(Event.kind, day, func.count()).where(where).group_by(Event.kind, day)):
        series.setdefault(str(d), {})[kind] = n
    top = s.execute(select(Product.id, Product.name, Event.kind, func.count())
                    .join(Product, Product.id == Event.product_id).where(where)
                    .group_by(Product.id, Product.name, Event.kind)).all()
    per_product = {}
    for pid, name, kind, n in top:
        per_product.setdefault(pid, {"id": pid, "name": name})[kind] = n
    ranked = sorted(per_product.values(), key=lambda p: (-p.get("view", 0), -p.get("reservation", 0)))[:10]
    keys = ["view", "tryon", "share", "reservation", "visit"]
    return {
        "days": days,
        "totals": {k: totals.get(k, 0) for k in keys},
        "series": [{"date": d, **{k: v.get(k, 0) for k in keys}} for d, v in sorted(series.items())],
        "top_products": ranked,
    }


# ---------- notifications (best effort, never block the request) ----------

def _send_async(token, chat_id, text, buttons=None):
    if not token or not chat_id:
        return
    threading.Thread(target=Bot(token).send, args=(chat_id, text, buttons), daemon=True).start()


def _esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_price(n):
    return f"{n:,}".replace(",", " ") + " soʻm"


def reservation_buttons(reservation):
    if reservation.status == "pending":
        return [[{"text": "✅ Tasdiqlash", "callback_data": f"r:{reservation.id}:confirm"},
                 {"text": "❌ Rad etish", "callback_data": f"r:{reservation.id}:decline"}]]
    if reservation.status == "confirmed":
        return [[{"text": "🚶 Xaridor keldi", "callback_data": f"r:{reservation.id}:visited"},
                 {"text": "🛍 Sotildi", "callback_data": f"r:{reservation.id}:sold"}]]
    return None


def notify_shop_new(reservation):
    cfg = current_app.config["CLOTHES"]
    shop = reservation.shop
    text = (f"🆕 <b>Yangi bron</b> #{reservation.id}\n"
            f"{_esc(reservation.product.name)} — <b>{_esc(reservation.variant.size)}</b>\n"
            f"{fmt_price(reservation.product.price)}\n"
            f"👤 {_esc(reservation.name)}, {_esc(reservation.phone)}\n"
            + (f"💬 {_esc(reservation.note)}\n" if reservation.note else "")
            + f"⏳ {cfg.RESERVATION_CONFIRM_HOURS} soat ichida tasdiqlang.")
    _send_async(cfg.TELEGRAM_BOT_TOKEN, shop.telegram_chat_id, text, reservation_buttons(reservation))


def notify_buyer(reservation):
    buyer = reservation.buyer
    if not buyer or not buyer.telegram_id:
        return
    cfg = current_app.config["CLOTHES"]
    lines = {
        "confirmed": f"✅ <b>{_esc(reservation.shop.name)}</b> broningizni tasdiqladi: "
                     f"{_esc(reservation.product.name)} ({_esc(reservation.variant.size)}). "
                     f"Kiyim {cfg.RESERVATION_HOLD_HOURS} soat olib qoʻyiladi."
                     + (f"\n📍 {_esc(reservation.shop.address)}" if reservation.shop.address else "")
                     + (f"\n🕘 {_esc(reservation.shop.hours)}" if reservation.shop.hours else ""),
        "declined": f"😔 {_esc(reservation.shop.name)} bronni tasdiqlay olmadi: "
                    f"{_esc(reservation.product.name)} ({_esc(reservation.variant.size)}). "
                    "Boshqa doʻkonlardan izlab koʻring.",
    }
    if reservation.status in lines:
        _send_async(cfg.TELEGRAM_BOT_TOKEN, buyer.telegram_id, lines[reservation.status])


SELLER_TRANSITIONS = {
    "confirm": ("pending", "confirmed"),
    "decline": ("pending", "declined"),
    "visited": ("confirmed", "visited"),
    "sold": ("confirmed", "sold"),
}


def apply_seller_action(s, reservation, action):
    """Move a reservation along; returns an error message or None."""
    if action not in SELLER_TRANSITIONS:
        return "Nomaʼlum amal."
    expire_reservations(s, force=True)
    s.refresh(reservation)
    before, after = SELLER_TRANSITIONS[action]
    if action == "sold" and reservation.status == "visited":
        before = "visited"  # a visitor may still buy after being marked as arrived
    if reservation.status != before:
        return f"Bron holati: {STATUS_LABELS.get(reservation.status, reservation.status)}."
    cfg = current_app.config["CLOTHES"]
    reservation.status = after
    if after == "confirmed":
        reservation.hold_until = utcnow() + timedelta(hours=cfg.RESERVATION_HOLD_HOURS)
    if after in ("visited", "sold") and before != "visited":
        record_event(s, "visit", reservation.shop_id, reservation.product_id, reservation.visitor)
    if after == "sold":
        variant = reservation.variant
        variant.stock = max(0, variant.stock - 1)
    s.commit()
    notify_buyer(reservation)
    return None


def reservation_public(r, for_seller=False):
    data = {
        "code": r.code if not for_seller else None, "id": r.id, "status": r.status,
        "status_label": STATUS_LABELS.get(r.status, r.status),
        "created_at": iso(r.created_at), "confirm_by": iso(r.confirm_by), "hold_until": iso(r.hold_until),
        "size": r.variant.size, "product": {"id": r.product.id, "name": r.product.name, "price": r.product.price,
                                            "image": image_url(r.product)},
        "shop": {"slug": r.shop.slug, "name": r.shop.name, "address": r.shop.address, "phone": r.shop.phone,
                 "hours": r.shop.hours, "lat": r.shop.lat, "lng": r.shop.lng},
    }
    if for_seller:
        data.pop("code")
        data.update(name=r.name, phone=r.phone, note=r.note, via_telegram=bool(r.buyer_id))
    return data


def iso(dt):
    return dt.isoformat() + "Z" if isinstance(dt, datetime) else None
