"""Clothes AI starter API: no user photographs are persisted."""
import os
from flask import Flask, jsonify, request, send_from_directory

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SHOPS = [
    {"id": "demo-a", "name": "Namuna butik A", "city": "Toshkent", "address": "Demo do‘kon, haqiqiy manzil yo‘q", "verified": False},
    {"id": "demo-b", "name": "Namuna butik B", "city": "Toshkent", "address": "Demo do‘kon, haqiqiy manzil yo‘q", "verified": False},
]
PRODUCTS = [
    {"shop_id": "demo-a", "stock_by_size": {"S": 1, "M": 2, "L": 0}, "id": "blazer-01", "name": "Minimal Blazer", "category": "Jaket", "price": 549000, "color": "Qora", "sizes": ["S", "M", "L"]},
    {"shop_id": "demo-b", "stock_by_size": {"XS": 1, "S": 1, "M": 0}, "id": "dress-01", "name": "Silk Evening Dress", "category": "Ko‘ylak", "price": 790000, "color": "Binafsha", "sizes": ["XS", "S", "M"]},
    {"shop_id": "demo-a", "stock_by_size": {"S": 2, "M": 2, "L": 3, "XL": 1}, "id": "shirt-01", "name": "Classic Linen Shirt", "category": "Ko‘ylak", "price": 329000, "color": "Oq", "sizes": ["S", "M", "L", "XL"]},
    {"shop_id": "demo-b", "stock_by_size": {"S": 0, "M": 1, "L": 2}, "id": "coat-01", "name": "Essential Trench Coat", "category": "Palto", "price": 895000, "color": "Bej", "sizes": ["S", "M", "L"]},
]

def create_app():
    app = Flask(__name__, static_folder=os.path.join(ROOT, "frontend"), static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

    @app.get("/")
    def home():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", app="clothes-ai", version="0.3.0", demo=True)

    @app.get("/api/shops")
    def shops():
        return jsonify(items=SHOPS, demo=True)

    @app.get("/api/products")
    def products():
        q = request.args.get("q", "").casefold().strip()
        size = request.args.get("size", "").upper().strip()
        shop_id = request.args.get("shop_id", "").strip()
        items = [p for p in PRODUCTS if (not q or q in (p["name"] + " " + p["category"] + " " + p["color"]).casefold()) and (not size or p["stock_by_size"].get(size, 0) > 0) and (not shop_id or p["shop_id"] == shop_id)]
        return jsonify(items=items, demo=True)

    @app.get("/api/availability")
    def availability():
        item = next((p for p in PRODUCTS if p["id"] == request.args.get("product_id")), None)
        if item is None:
            return jsonify(error="Mahsulot topilmadi."), 404
        size = request.args.get("size", "").upper()
        if size not in item["sizes"]:
            return jsonify(error="O‘lcham mavjud emas."), 400
        shop = next(s for s in SHOPS if s["id"] == item["shop_id"])
        return jsonify(demo=True, shop=shop, size=size, stock=item["stock_by_size"][size])

    @app.post("/api/reservations")
    def reserve():
        return jsonify(code="DEMO_ONLY", error="Haqiqiy bron hali yoqilmagan."), 503

    @app.post("/api/try-on")
    def try_on():
        photo = request.files.get("photo")
        product_id = request.form.get("product_id", "")
        if photo is None or not photo.filename:
            return jsonify(error="Rasm tanlanmagan."), 400
        if not any(p["id"] == product_id for p in PRODUCTS):
            return jsonify(error="Kiyim topilmadi."), 400
        if photo.mimetype not in ("image/jpeg", "image/png", "image/webp"):
            return jsonify(error="Faqat JPEG, PNG yoki WebP qabul qilinadi."), 415
        header = photo.stream.read(16)
        photo.stream.seek(0)
        valid = (header.startswith(b"\xff\xd8\xff") or header.startswith(b"\x89PNG\r\n\x1a\n") or (header.startswith(b"RIFF") and header[8:12] == b"WEBP"))
        if not valid:
            return jsonify(error="Rasm formati noto‘g‘ri."), 415
        return jsonify(error="AI model hali ulanmagan. Surat saqlanmadi.", code="AI_NOT_CONFIGURED"), 503

    @app.errorhandler(413)
    def too_large(_):
        return jsonify(error="Rasm 8 MB dan katta bo‘lmasin."), 413

    return app

app = create_app()
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG") == "1")
