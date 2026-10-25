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


def _seller(client, login="s@b.uz"):
    client.post("/api/seller/register", json={"login": login, "password": "secret123", "shop_name": "Do'kon",
                                              "phone": "901112233", "agree": True})


def test_seller_reservation_actions(tmp_path):
    app = create_app(TESTING=True, SECRET_KEY="test", DATA_DIR=tmp_path, DATABASE_URL="")
    seller, buyer = app.test_client(), app.test_client()
    _seller(seller)
    pid = seller.post("/api/seller/products", json={"name": "Kostyum", "category": "Kostyum", "price": 500000,
                                                     "variants": [{"size": "50", "stock": 1}]}).json["product"]["id"]
    from backend.models import Shop
    with app.extensions["clothes_db"].Session() as s:
        s.query(Shop).filter(Shop.is_demo.is_(False)).update({"status": "active"})
        s.commit()
    r = buyer.post("/api/reservations", json={"product_id": pid, "size": "50", "name": "Ali",
                                              "phone": "+998 90 000 00 01", "agree": True})
    assert r.status_code == 201
    # the only unit is held: a second buyer cannot reserve it
    other = app.test_client().post("/api/reservations", json={"product_id": pid, "size": "50", "name": "Vali",
                                                              "phone": "+998 90 000 00 02", "agree": True})
    assert other.json["code"] == "OUT_OF_STOCK"
    rid = seller.get("/api/seller/reservations").json["items"][0]["id"]
    assert seller.post(f"/api/seller/reservations/{rid}/visited").status_code == 409  # must confirm first
    assert seller.post(f"/api/seller/reservations/{rid}/confirm").json["reservation"]["status"] == "confirmed"
    assert seller.post(f"/api/seller/reservations/{rid}/sold").json["reservation"]["status"] == "sold"
    stats = seller.get("/api/seller/stats").json
    assert stats["totals"]["reservation"] == 1 and stats["totals"]["visit"] == 1
    assert stats["in_stock_units"] == 0


def test_seller_cannot_touch_other_shop(tmp_path):
    app = create_app(TESTING=True, SECRET_KEY="test", DATA_DIR=tmp_path, DATABASE_URL="")
    a, b = app.test_client(), app.test_client()
    _seller(a, "a@a.uz")
    _seller(b, "b@b.uz")
    pid = a.post("/api/seller/products", json={"name": "Libos", "category": "Kechki libos", "price": 1,
                                                "variants": [{"size": "S", "stock": 1}]}).json["product"]["id"]
    assert b.patch(f"/api/seller/products/{pid}", json={"price": 2}).status_code == 404
    assert b.delete(f"/api/seller/products/{pid}").status_code == 404
    assert app.test_client().get("/api/seller/products").status_code == 401


def test_login_errors(client):
    _seller(client)
    client.post("/api/seller/logout")
    assert client.post("/api/seller/login", json={"login": "s@b.uz", "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/seller/login", json={"login": "s@b.uz", "password": "secret123"}).status_code == 200


def test_tryon_demo_job(tmp_path):
    import time
    app = create_app(TESTING=True, SECRET_KEY="test", DATA_DIR=tmp_path, DATABASE_URL="", TRYON_PROVIDER="demo")
    c = app.test_client()
    job = c.post("/api/try-on/jobs", data={"product_id": "1", "consent": "1",
                                           "photo": (jpeg(), "me.jpg", "image/jpeg")}).json["job"]
    for _ in range(50):
        job = c.get(f"/api/try-on/jobs/{job['id']}").json["job"]
        if job["status"] == "completed":
            break
        time.sleep(0.05)
    assert job["status"] == "completed"
    assert c.get(job["result"]).mimetype == "image/webp"
    assert app.test_client().get(job["result"]).status_code == 404  # other visitors cannot see it
    files = [p.name for p in (tmp_path / "private" / "tryon").iterdir()]
    assert files == [f"{job['id']}-out.webp"]  # the original photo is gone
    assert c.delete("/api/me/data").json["tryon_deleted"] == 1
    assert not list((tmp_path / "private" / "tryon").iterdir())


def test_telegram_init_data():
    import hashlib, hmac, json, time
    from urllib.parse import urlencode
    from backend.telegram import verify_init_data
    token = "123:ABC"
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": 42, "first_name": "Ali"})}
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    data = urlencode(fields)
    assert verify_init_data(data, token, 3600)["id"] == 42
    assert verify_init_data(data.replace("Ali", "Bob"), token, 3600) is None
    assert verify_init_data(data, "other:token", 3600) is None


def test_webhook_requires_secret(tmp_path):
    app = create_app(TESTING=True, SECRET_KEY="test", DATA_DIR=tmp_path, DATABASE_URL="",
                     TELEGRAM_BOT_TOKEN="1:x", TELEGRAM_WEBHOOK_SECRET="s3cret")
    c = app.test_client()
    assert c.post("/telegram/webhook", json={}).status_code == 403
    assert c.post("/telegram/webhook", json={}, headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"}).status_code == 200


def test_pages_and_headers(client):
    r = client.get("/p/1")
    assert r.status_code == 200 and b"Clothes AI" in r.data
    assert "frame-ancestors" in r.headers["Content-Security-Policy"]
    assert client.get("/nope").status_code == 404
    assert client.get("/api/nope").json["code"] == "HTTP_404"
    assert client.get("/media/products/../../clothes.db").status_code == 404


STUDENT = {"height_cm": 175, "weight_kg": 60, "gender": "erkak", "skin_tone": "bugdoy",
           "season": "qish", "occasion": "oqish"}


def test_stylist_winter_student(client):
    r = client.post("/api/stylist", json=STUDENT)
    assert r.status_code == 200
    data = r.json
    assert data["engine"] == "rules"
    assert data["analysis"]["size"]["letter"] == "S" and data["analysis"]["size"]["numeric"] == "46"
    slots = {i["slot"]: i["product"] for i in data["outfit"]}
    assert {"outer", "layer", "bottom", "shoes"} <= set(slots)
    assert slots["outer"]["warmth"] >= 2 and "qish" in slots["outer"]["seasons"]
    for product in slots.values():
        assert product["gender"] in ("erkak", "unisex")
    assert data["total_price"] == sum(p["price"] for p in slots.values())


def test_stylist_budget_and_validation(client):
    fits = client.post("/api/stylist", json={**STUDENT, "budget": 2000000}).json
    assert fits["total_price"] <= 2000000 and not fits["over_budget"]
    assert {i["slot"] for i in fits["outfit"]} >= {"outer", "bottom", "shoes"}
    tight = client.post("/api/stylist", json={**STUDENT, "budget": 500000}).json
    assert tight["over_budget"] is True  # a winter coat alone costs more: say so instead of hiding it
    assert client.post("/api/stylist", json={**STUDENT, "height_cm": 400}).json["code"] == "VALIDATION"
    assert client.post("/api/stylist", json={**STUDENT, "skin_tone": "x"}).status_code == 400


def test_stylist_wedding_picks_formal_wear(client):
    data = client.post("/api/stylist", json={**STUDENT, "gender": "ayol", "occasion": "toy", "weight_kg": 55,
                                             "height_cm": 163}).json
    full = next(i for i in data["outfit"] if i["slot"] == "full")
    assert full["product"]["category"] in ("Kelinlik libosi", "Kechki libos", "Milliy libos")


def test_stylist_uses_claude_choice(tmp_path, monkeypatch):
    import json
    import types
    import anthropic

    app = create_app(TESTING=True, SECRET_KEY="t", DATA_DIR=tmp_path, DATABASE_URL="",
                     STYLIST_PROVIDER="anthropic", ANTHROPIC_API_KEY="test-key")
    c = app.test_client()
    rules = c.post("/api/stylist", json=STUDENT)  # first call: see what the candidates are
    seen = {}

    class FakeMessages:
        def create(self, **kwargs):
            seen.update(kwargs)
            request = json.loads(kwargs["messages"][0]["content"].split("\n", 1)[1])
            outer = [x for x in request["candidates"] if x["slot"] == "outer"]
            pick = outer[-1]["product_id"]
            body = {"summary": "Sizga issiq va qulay toʻplam.", "tips": ["Qatlamlab kiying."], "color_note": "Yashil yarashadi.",
                    "items": [{"slot": "outer", "product_id": pick, "why": "Eng issiq."},
                              {"slot": "outer", "product_id": 999999, "why": "bogus"}]}
            return types.SimpleNamespace(stop_reason="end_turn",
                                         content=[types.SimpleNamespace(type="text", text=json.dumps(body))])

    class FakeClient:
        def __init__(self, **kwargs):
            self.beta = types.SimpleNamespace(messages=FakeMessages())

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    data = c.post("/api/stylist", json=STUDENT).json
    assert data["engine"] == "ai" and data["summary"].startswith("Sizga")
    outer = next(i for i in data["outfit"] if i["slot"] == "outer")
    assert outer["why"] == "Eng issiq."
    assert seen["model"] == "claude-opus-5-5"
    assert seen["output_config"]["format"]["type"] == "json_schema"
    assert len(data["outfit"]) == len(rules.json["outfit"])  # slots the model skipped keep the rule pick


def test_stylist_falls_back_when_claude_fails(tmp_path, monkeypatch):
    import anthropic

    app = create_app(TESTING=True, SECRET_KEY="t", DATA_DIR=tmp_path, DATABASE_URL="",
                     STYLIST_PROVIDER="anthropic", ANTHROPIC_API_KEY="test-key")

    class Broken:
        def __init__(self, **kwargs):
            raise anthropic.AnthropicError("no credentials")

    monkeypatch.setattr(anthropic, "Anthropic", Broken)
    data = app.test_client().post("/api/stylist", json=STUDENT).json
    assert data["engine"] == "rules" and data["outfit"]


def test_seller_sets_stylist_attributes(client):
    _seller(client)
    p = client.post("/api/seller/products", json={"name": "Kurtka", "category": "Ustki kiyim", "price": 500000,
                                                  "gender": "erkak", "seasons": ["qish", "nope"], "occasions": "oqish,ish",
                                                  "warmth": 3, "variants": [{"size": "M", "stock": 1}]}).json["product"]
    assert p["seasons"] == ["qish"] and p["occasions"] == ["oqish", "ish"] and p["warmth"] == 3


def test_migration_adds_columns(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, shop_id INTEGER, name TEXT, category TEXT, color TEXT,"
                " price INTEGER, description TEXT, image TEXT, search_text TEXT, active BOOLEAN, created_at DATETIME,"
                " updated_at DATETIME)")
    con.commit()
    con.close()
    create_app(TESTING=True, SECRET_KEY="t", DATA_DIR=tmp_path, DATABASE_URL=f"sqlite:///{db}", SEED_DEMO=False)
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(products)")}
    assert {"gender", "seasons", "occasions", "warmth"} <= cols


def test_3d_assets_served(client):
    r = client.get("/vendor/three.module.min.js")
    assert r.status_code == 200 and b"Three.js Authors" in r.data[:300]
    assert client.get("/js/fitting3d.js").status_code == 200
    page = client.get("/").data
    assert b'id="fitting-dialog"' in page and b"fitting3d.js" in page


def test_demo_photos_have_credits(client):
    items = client.get("/api/products?limit=60").json["items"]
    with_photo = [p for p in items if p["image"]]
    assert len(with_photo) >= 30  # 32 of 39 demo products have a photo
    for p in with_photo:
        credit = p["photo_credit"]
        assert credit and credit["author"] and credit["license"] and credit["source_url"].startswith("http")
        assert client.get(p["image"]).status_code == 200


def test_remove_demo(tmp_path):
    app = create_app(TESTING=True, SECRET_KEY="t", DATA_DIR=tmp_path, DATABASE_URL="")
    media = tmp_path / "media" / "products"
    assert any(media.iterdir())
    result = app.test_cli_runner().invoke(args=["remove-demo", "--yes"])
    assert result.exit_code == 0, result.output
    assert app.test_client().get("/api/products").json["total"] == 0
    assert not any(media.iterdir())
