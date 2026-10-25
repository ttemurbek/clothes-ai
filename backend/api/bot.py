"""Telegram bot webhook: opens the Mini App, links a shop chat, confirms reservations from buttons."""
import hmac

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy import select

from ..models import Reservation, Shop, db
from ..services import apply_seller_action, reservation_buttons, STATUS_LABELS
from ..telegram import Bot

bp = Blueprint("bot", __name__)


def _app_button(cfg, start=""):
    if not cfg.PUBLIC_URL.startswith("https://"):
        return None
    url = cfg.PUBLIC_URL + "/" + (f"?startapp={start}" if start else "")
    return [[{"text": "🛍 Clothes AI ni ochish", "web_app": {"url": url}}]]


def _on_message(bot, cfg, message):
    chat_id = message.get("chat", {}).get("id")
    text = (message.get("text") or "").strip()
    if not chat_id or not text.startswith("/start"):
        return
    payload = text[len("/start"):].strip()
    if payload.startswith("link_"):
        s = db()
        shop = s.scalar(select(Shop).where(Shop.link_code == payload[5:])) if len(payload) > 5 else None
        if shop is None:
            bot.send(chat_id, "Havola eskirgan. Sotuvchi panelidan yangi havola oling.")
            return
        shop.telegram_chat_id, shop.link_code = chat_id, None
        s.commit()
        bot.send(chat_id, f"✅ <b>{shop.name}</b> shu chatga ulandi. Yangi bronlar shu yerga keladi.")
        return
    bot.send(chat_id, "Assalomu alaykum! Clothes AI — Toshkent doʻkonlaridagi kiyimlarni toping, "
                      "oʻzingizda koʻring va yaqin doʻkondan bron qiling.", _app_button(cfg, payload[:64]))


def _on_callback(bot, callback):
    data = callback.get("data", "")
    message = callback.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "r" or not parts[1].isdigit():
        bot.answer_callback(callback["id"], "Nomaʼlum amal")
        return
    s = db()
    reservation = s.get(Reservation, int(parts[1]))
    if reservation is None or reservation.shop.telegram_chat_id != chat_id:
        bot.answer_callback(callback["id"], "Bron topilmadi")
        return
    problem = apply_seller_action(s, reservation, parts[2])
    bot.answer_callback(callback["id"], problem or STATUS_LABELS.get(reservation.status, "OK"))
    if message.get("message_id"):
        bot.edit_buttons(chat_id, message["message_id"], reservation_buttons(reservation))


@bp.post("/telegram/webhook")
def webhook():
    cfg = current_app.config["CLOTHES"]
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_WEBHOOK_SECRET or \
            not hmac.compare_digest(secret, cfg.TELEGRAM_WEBHOOK_SECRET):
        return jsonify(ok=False), 403
    update = request.get_json(silent=True) or {}
    bot = Bot(cfg.TELEGRAM_BOT_TOKEN)
    if "message" in update:
        _on_message(bot, cfg, update["message"])
    elif "callback_query" in update:
        _on_callback(bot, update["callback_query"])
    return jsonify(ok=True)
