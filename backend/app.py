"""Clothes AI: one catalog of city shops + virtual fitting room + reservation at the nearest shop."""
import logging
import re
import time

import click
from flask import Flask, g, jsonify, request, send_from_directory
from sqlalchemy import select, text
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from . import tryon
from .config import ROOT, Config
from .models import Database, Seller, Shop
from .security import add_headers, check_origin
from .seed import seed_demo
from .telegram import Bot

VERSION = "0.4.0"
FRONTEND = ROOT / "frontend"


def create_app(**overrides):
    cfg = Config(**overrides)
    app = Flask(__name__, static_folder=str(FRONTEND), static_url_path="")
    app.config.update(cfg.as_flask())
    app.config["CLOTHES"] = cfg
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if cfg.TRUST_PROXY:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    database = Database(cfg.DATABASE_URL)
    database.create_all()
    app.extensions["clothes_db"] = database
    if cfg.SEED_DEMO:
        with database.Session() as s:
            seed_demo(s, cfg.DATA_DIR / "media" / "products")

    from .api import bot, catalog, reservations, seller, shares
    from .api import stylist as stylist_api
    from .api import tryon as tryon_api
    for module in (catalog, reservations, seller, tryon_api, shares, stylist_api, bot):
        app.register_blueprint(module.bp)

    last_purge = [0.0]

    @app.before_request
    def before():
        if time.monotonic() - last_purge[0] > 600 and not app.testing:
            last_purge[0] = time.monotonic()
            try:
                tryon.purge_expired(app)
            except Exception:  # cleanup must never break a request
                app.logger.exception("purge failed")
        return check_origin()

    @app.after_request
    def after(response):
        return add_headers(response)

    @app.teardown_appcontext
    def close_db(_exc):
        session = g.pop("db", None)
        if session is not None:
            session.close()

    # ---------- pages ----------
    def page(name, status=200):
        response = send_from_directory(FRONTEND, name)
        response.headers["Cache-Control"] = "no-cache"
        return response, status

    @app.get("/")
    @app.get("/p/<int:_id>")
    @app.get("/shop/<_slug>")
    def home(**_):
        return page("index.html")

    @app.get("/s/<_token>")
    def share_page(_token):
        return page("share.html")

    @app.get("/seller")
    @app.get("/seller.html")
    def seller_page():
        return page("seller.html")

    @app.get("/privacy")
    def privacy_page():
        return page("privacy.html")

    @app.get("/media/products/<name>")
    def media(name):
        if not re.fullmatch(r"[0-9a-f]{32}\.webp", name):
            return jsonify(error="Topilmadi."), 404
        return send_from_directory(cfg.DATA_DIR / "media" / "products", name, max_age=30 * 24 * 3600)

    @app.get("/api/health")
    def health():
        try:
            with database.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        return jsonify(status="ok" if db_ok else "degraded", app="clothes-ai", version=VERSION,
                       database=db_ok, tryon=cfg.TRYON_PROVIDER), 200 if db_ok else 503

    # ---------- errors ----------
    @app.errorhandler(HTTPException)
    def http_error(exc):
        messages = {404: "Sahifa topilmadi.", 405: "Bu amal ruxsat etilmagan.",
                    413: "Fayl 8 MB dan katta boʻlmasin.", 429: "Juda koʻp soʻrov."}
        if request.path.startswith("/api/") or exc.code != 404:
            return jsonify(error=messages.get(exc.code, exc.name), code=f"HTTP_{exc.code}"), exc.code
        return page("404.html", 404)

    @app.errorhandler(Exception)
    def server_error(exc):
        app.logger.exception("unhandled error")
        return jsonify(error="Serverda xatolik. Birozdan keyin urinib koʻring.", code="SERVER_ERROR"), 500

    _register_cli(app)
    return app


def _register_cli(app):
    database = app.extensions["clothes_db"]
    cfg = app.config["CLOTHES"]

    @app.cli.command("seed-demo")
    def seed_cmd():
        """Insert demo shops and products into an empty database."""
        with database.Session() as s:
            changed = seed_demo(s, cfg.DATA_DIR / "media" / "products")
            click.echo("Demo maʼlumotlar yangilandi." if changed else "Oʻzgarish yoʻq.")

    @app.cli.command("remove-demo")
    @click.confirmation_option(prompt="Barcha namuna doʻkonlar, mahsulotlar va ularning suratlari oʻchirilsinmi?")
    def remove_demo_cmd():
        """Delete demo shops with their products, reservations, stats and photos (run before launch)."""
        from .models import Product
        media = cfg.DATA_DIR / "media" / "products"
        with database.Session() as s:
            shops = s.scalars(select(Shop).where(Shop.is_demo.is_(True))).all()
            images = [p.image for shop in shops for p in s.scalars(select(Product).where(Product.shop_id == shop.id)) if p.image]
            for shop in shops:
                s.delete(shop)
            s.commit()
        for name in images:
            (media / name).unlink(missing_ok=True)
        click.echo(f"Oʻchirildi: {len(shops)} ta namuna doʻkon, {len(images)} ta surat. Endi SEED_DEMO=0 qoʻying.")

    @app.cli.command("shops")
    def shops_cmd():
        """List shops and their status."""
        with database.Session() as s:
            for shop in s.scalars(select(Shop).order_by(Shop.id)):
                demo = "demo" if shop.is_demo else "    "
                click.echo(f"{shop.id:>4}  {shop.status:<8} {demo}  {shop.slug}  {shop.name}")

    def _set_status(slug, status, founding=False):
        with database.Session() as s:
            shop = s.scalar(select(Shop).where(Shop.slug == slug))
            if shop is None:
                raise click.ClickException("Doʻkon topilmadi")
            shop.status = status
            if founding:
                shop.founding_partner = True
            s.commit()
            click.echo(f"{shop.name}: {status}")

    @app.cli.command("approve-shop")
    @click.argument("slug")
    @click.option("--founding", is_flag=True, help="Mark as a founding partner (asoschi hamkor)")
    def approve_cmd(slug, founding):
        """Publish a shop's catalog after checking its details."""
        _set_status(slug, "active", founding)

    @app.cli.command("block-shop")
    @click.argument("slug")
    def block_cmd(slug):
        """Hide a shop and lock its seller panel."""
        _set_status(slug, "blocked")

    @app.cli.command("reset-password")
    @click.argument("login")
    @click.password_option()
    def reset_password_cmd(login, password):
        """Set a seller's password (prompted, never echoed)."""
        with database.Session() as s:
            seller = s.scalar(select(Seller).where(Seller.login == login.lower()))
            if seller is None:
                raise click.ClickException("Sotuvchi topilmadi")
            seller.password_hash = generate_password_hash(password)
            s.commit()
        click.echo("Parol yangilandi.")

    @app.cli.command("purge")
    def purge_cmd():
        """Delete expired try-on photos and results now."""
        click.echo(f"Oʻchirildi: {tryon.purge_expired(app)}")

    @app.cli.command("set-webhook")
    def webhook_cmd():
        """Point the Telegram bot at PUBLIC_URL/telegram/webhook and set the menu button."""
        if not (cfg.TELEGRAM_BOT_TOKEN and cfg.TELEGRAM_WEBHOOK_SECRET and cfg.PUBLIC_URL.startswith("https://")):
            raise click.ClickException("TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET va https PUBLIC_URL kerak")
        bot = Bot(cfg.TELEGRAM_BOT_TOKEN)
        ok = bot.call("setWebhook", url=cfg.PUBLIC_URL + "/telegram/webhook", secret_token=cfg.TELEGRAM_WEBHOOK_SECRET,
                      allowed_updates=["message", "callback_query"])
        bot.call("setChatMenuButton", menu_button={"type": "web_app", "text": "Katalog",
                                                   "web_app": {"url": cfg.PUBLIC_URL + "/"}})
        click.echo("Webhook oʻrnatildi." if ok else "Xato: webhook oʻrnatilmadi (loglarni koʻring).")
