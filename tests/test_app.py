import io
from backend.app import create_app

def test_health():
    assert create_app().test_client().get("/api/health").json["status"] == "ok"

def test_catalog():
    assert len(create_app().test_client().get("/api/products").json["items"]) == 4

def test_missing_photo():
    assert create_app().test_client().post("/api/try-on", data={"product_id": "blazer-01"}).status_code == 400

def test_unconfigured_ai():
    response = create_app().test_client().post("/api/try-on", data={
        "product_id": "blazer-01",
        "photo": (io.BytesIO(b"\xff\xd8\xfftest"), "person.jpg", "image/jpeg"),
    })
    assert response.status_code == 503
    assert response.json["code"] == "AI_NOT_CONFIGURED"


def test_shops_demo():
    result = create_app().test_client().get("/api/shops")
    assert result.status_code == 200
    assert result.json["demo"] is True
    assert len(result.json["items"]) == 2


def test_filter_available_size():
    response = create_app().test_client().get("/api/products?size=XL")
    assert [item["id"] for item in response.json["items"]] == ["shirt-01"]


def test_shop_inventory():
    response = create_app().test_client().get("/api/availability?product_id=blazer-01&size=L")
    assert response.json["stock"] == 0
    assert response.json["shop"]["verified"] is False


def test_booking_not_active():
    response = create_app().test_client().post("/api/reservations", json={"product_id": "blazer-01", "size": "M"})
    assert response.status_code == 503
    assert response.json["code"] == "DEMO_ONLY"
