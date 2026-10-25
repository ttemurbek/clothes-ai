"""Telegram: Mini App initData verification and a tiny Bot API client (plain HTTPS)."""
import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

import requests

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"


def verify_init_data(init_data, bot_token, max_age):
    """Return the Telegram user dict if initData is authentic and fresh, else None.

    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data or not bot_token or len(init_data) > 4096:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    received = pairs.pop("hash", "")
    if not received:
        return None
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    if time.time() - auth_date > max_age:
        return None
    try:
        user = json.loads(pairs.get("user", "{}"))
    except ValueError:
        return None
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        return None
    return user


class Bot:
    def __init__(self, token):
        self.token = token

    @property
    def enabled(self):
        return bool(self.token)

    def call(self, method, **payload):
        if not self.token:
            return None
        try:
            response = requests.post(API.format(token=self.token, method=method), json=payload, timeout=10)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            log.warning("telegram %s failed: %s", method, type(exc).__name__)
            return None
        if not data.get("ok"):
            log.warning("telegram %s: %s", method, data.get("description", "error"))
            return None
        return data.get("result")

    def send(self, chat_id, text, buttons=None):
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                   "link_preview_options": {"is_disabled": True}}
        if buttons:
            payload["reply_markup"] = {"inline_keyboard": buttons}
        return self.call("sendMessage", **payload)

    def answer_callback(self, callback_id, text):
        return self.call("answerCallbackQuery", callback_query_id=callback_id, text=text)

    def edit_buttons(self, chat_id, message_id, buttons=None):
        return self.call("editMessageReplyMarkup", chat_id=chat_id, message_id=message_id,
                         reply_markup={"inline_keyboard": buttons or []})
