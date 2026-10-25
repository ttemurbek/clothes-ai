import io

import pytest
from PIL import Image

from backend.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(TESTING=True, SECRET_KEY="test", DATA_DIR=tmp_path, DATABASE_URL="")
    return app.test_client()


def jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), (200, 150, 180)).save(buf, "JPEG")
    buf.seek(0)
    return buf


def test_health(client):
    assert client.get("/api/health").json["status"] == "ok"


def test_catalog_filters(client):
    items = client.get("/api/products?category=Kostyum&size=48").json["items"]
    assert items and all(p["category"] == "Kostyum" and "48" in p["available_sizes"] for p in items)
    assert client.get("/api/products?q=ko'ylak").json["total"] >= 1  # apostrophe variants match


def test_shops_nearest(client):
    items = client.get("/api/shops?lat=41.3&lng=69.25").json["items"]
    assert [s["distance_km"] for s in items] == sorted(s["distance_km"] for s in items)


def test_reservation_flow(client):
    body = {"product_id": 1, "size": "S", "name": "Ali", "phone": "90 123 45 67", "agree": True}
    created = client.post("/api/reservations", json=body)
    assert created.status_code == 201
    code = created.json["reservation"]["code"]
    assert client.post("/api/reservations", json=body).json["code"] == "DUPLICATE"
    assert client.post(f"/api/reservations/{code}/cancel").json["reservation"]["status"] == "cancelled"


def test_reservation_validation(client):
    r = client.post("/api/reservations", json={"product_id": 1, "size": "S", "name": "Ali", "phone": "123"})
    assert r.json["code"] == "PHONE_INVALID"


def test_tryon_disabled_stores_nothing(client, tmp_path):
    r = client.post("/api/try-on/jobs", data={"product_id": "1", "consent": "1",
                                              "photo": (jpeg(), "me.jpg", "image/jpeg")})
    assert r.status_code == 503 and r.json["code"] == "AI_NOT_CONFIGURED"
    assert not list((tmp_path / "private" / "tryon").iterdir())


def test_tryon_rejects_fake_image(client):
    r = client.post("/api/try-on/jobs", data={"product_id": "1", "consent": "1",
                                              "photo": (io.BytesIO(b"\xff\xd8\xffnope"), "x.jpg", "image/jpeg")})
    assert r.json["code"] == "BAD_IMAGE"


def test_seller_register_and_product(client):
    r = client.post("/api/seller/register", json={"login": "a@b.uz", "password": "secret123",
                                                  "shop_name": "Test", "phone": "+998901112233", "agree": True})
    assert r.status_code == 201 and r.json["shop"]["status"] == "pending"
    p = client.post("/api/seller/products", json={"name": "Libos", "category": "Kechki libos", "price": 100000,
                                                  "variants": [{"size": "m", "stock": 2}]})
    assert p.status_code == 201 and p.json["product"]["variants"][0]["size"] == "M"
    # pending shops are not public
    assert client.get("/api/products?q=libos&shop=" + r.json["shop"]["slug"]).json["total"] == 0


def test_cross_site_post_rejected(client):
    r = client.post("/api/reservations", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_share_vote(client):
    t = client.post("/api/shares", json={"product_ids": [1, 2]}).json["token"]
    assert client.post(f"/api/shares/{t}/vote", json={"product_id": 2}).json["total_votes"] == 1
