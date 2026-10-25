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
