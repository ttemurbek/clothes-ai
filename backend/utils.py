"""Small helpers shared by the API modules."""
import hashlib
import math
import re
import secrets
import unicodedata

from flask import jsonify, session

CATEGORIES = [
    "Kelinlik libosi", "Kechki libos", "Kostyum", "Milliy libos", "Ustki kiyim", "Sviter va kofta",
    "Koʻylak", "Shim va yubka", "Poyabzal", "Aksessuar", "Bolalar kiyimi",
]
GENDERS = {"ayol": "Ayollar", "erkak": "Erkaklar", "unisex": "Hamma uchun", "bola": "Bolalar"}
SEASONS = {"qish": "Qish", "bahor": "Bahor", "yoz": "Yoz", "kuz": "Kuz"}
OCCASIONS = {
    "oqish": "Oʻqish", "ish": "Ish / ofis", "kundalik": "Kundalik", "toy": "Toʻy",
    "bayram": "Bayram / kechki tadbir", "sport": "Sport / sayr", "sayohat": "Sayohat",
}


def csv_values(value, allowed):
    """Keep only known keys from a list or comma-separated string, in the allowed order."""
    items = value if isinstance(value, list) else str(value or "").split(",")
    wanted = {str(x).strip().lower() for x in items}
    return ",".join(k for k in allowed if k in wanted)


COLORS = [
    "Oq", "Qora", "Bej", "Kulrang", "Koʻk", "Moviy", "Yashil", "Qizil", "Pushti",
    "Binafsha", "Oltin rang", "Kumush rang", "Jigarrang", "Rang-barang",
]
SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "3XL", "4XL"] + \
    [str(n) for n in range(34, 62, 2)] + ["Standart"]

_APOSTROPHES = "'‘’`ʼʻ´"


def norm_text(value):
    """Case-folded text with every Uzbek apostrophe variant unified (o'/oʻ/o‘)."""
    value = unicodedata.normalize("NFC", str(value or "")).casefold()
    for ch in _APOSTROPHES:
        value = value.replace(ch, "'")
    return re.sub(r"\s+", " ", value).strip()


def clean_str(value, limit):
    value = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(value or "")).strip()
    return value[:limit]


def norm_size(value):
    value = clean_str(value, 16)
    upper = value.upper()
    return "Standart" if upper in ("STANDART", "ONE SIZE", "ONESIZE") else upper


def size_key(size):
    return SIZE_ORDER.index(size) if size in SIZE_ORDER else len(SIZE_ORDER)


def normalize_phone(value):
    """Uzbek mobile number as +998XXXXXXXXX, or None if it does not look valid."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 9:
        digits = "998" + digits
    if len(digits) != 12 or not digits.startswith("998"):
        return None
    return "+" + digits


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def parse_float(value, low, high):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if low <= number <= high and math.isfinite(number) else None


def parse_int(value, default=None, low=None, high=None):
    try:
        number = int(str(value).replace(" ", ""))
    except (TypeError, ValueError):
        return default
    if low is not None and number < low:
        return default
    if high is not None and number > high:
        return default
    return number


def error(message, status=400, code=None, **extra):
    body = {"error": message}
    if code:
        body["code"] = code
    body.update(extra)
    return jsonify(body), status


def visitor_id():
    """A stable anonymous id for this browser (in the signed session cookie)."""
    vid = session.get("vid")
    if not vid:
        vid = secrets.token_urlsafe(16)
        session["vid"] = vid
        session.permanent = True
    return vid


def hash_id(value):
    return hashlib.sha256(str(value).encode()).hexdigest()[:32]


def token(n=16):
    return secrets.token_urlsafe(n)
