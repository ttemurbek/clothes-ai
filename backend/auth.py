"""Who is calling: a Telegram Mini App user, an anonymous web visitor, or a signed-in seller."""
from functools import wraps

from flask import current_app, g, request, session
from sqlalchemy import select

from .models import Buyer, Seller, db
from .telegram import verify_init_data
from .utils import error, visitor_id


def telegram_user():
    """The verified Telegram user from the X-Telegram-Init-Data header, or None."""
    if "tg_user" not in g:
        cfg = current_app.config["CLOTHES"]
        g.tg_user = verify_init_data(request.headers.get("X-Telegram-Init-Data", ""),
                                     cfg.TELEGRAM_BOT_TOKEN, cfg.TELEGRAM_INITDATA_MAX_AGE)
    return g.tg_user


def current_visitor():
    user = telegram_user()
    return f"tg:{user['id']}" if user else f"w:{visitor_id()}"


def current_buyer():
    """The Buyer row for a Telegram user (created on first use); None for web visitors."""
    user = telegram_user()
    if not user:
        return None
    s = db()
    buyer = s.scalar(select(Buyer).where(Buyer.telegram_id == user["id"]))
    name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")]))[:120]
    if buyer is None:
        buyer = Buyer(telegram_id=user["id"], name=name, username=(user.get("username") or "")[:64])
        s.add(buyer)
        s.flush()
    elif name and buyer.name != name:
        buyer.name = name
    return buyer


def current_seller():
    if "seller" not in g:
        seller_id = session.get("seller_id")
        g.seller = db().get(Seller, seller_id) if seller_id else None
        if g.seller is None and seller_id:
            session.pop("seller_id", None)
    return g.seller


def seller_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        seller = current_seller()
        if seller is None:
            return error("Avval tizimga kiring.", 401, "AUTH_REQUIRED")
        if seller.shop.status == "blocked":
            return error("Doʻkon bloklangan. Administrator bilan bogʻlaning.", 403, "SHOP_BLOCKED")
        return view(seller, *args, **kwargs)
    return wrapper
