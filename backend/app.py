"""Clothes AI starter API: no user photographs are persisted."""
import os
from flask import Flask, jsonify, request, send_from_directory

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PRODUCTS = [
    {"id": "blazer-01", "name": "Minimal Blazer", "category": "Jaket", "price": 549000, "color": "Qora", "sizes": ["S", "M", "L"]},
    {"id": "dress-01", "name": "Silk Evening Dress", "category": "Ko‘ylak", "price": 790000, "color": "Binafsha", "sizes": ["XS", "S", "M"]},
    {"id": "shirt-01", "name": "Classic Linen Shirt", "category": "Ko‘ylak", "price": 329000, "color": "Oq", "sizes": ["S", "M", "L", "XL"]},
    {"id": "coat-01", "name": "Essential Trench Coat", "category": "Palto", "price": 895000, "color": "Bej", "sizes": ["S", "M", "L"]},
]

def create_app():
    app = Flask(__name__, static_folder=os.path.join(ROOT, "frontend"), static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

    @app.get("/")
    def home():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", app="clothes-ai", version="0.1.0")

    @app.get("/api/products")
    def products():
        return jsonify(items=PRODUCTS)

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
