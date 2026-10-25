"""Try-on jobs API and the buyer's privacy controls (delete everything)."""
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request, send_file
from sqlalchemy import delete, func, select, update

from .. import tryon
from ..auth import current_visitor
from ..images import ImageError, load_image, save_webp
from ..models import Buyer, Product, Reservation, Share, ShareVote, TryOnJob, db, utcnow
from ..security import rate_limit
from ..services import iso, public_products_query, record_event
from ..utils import error, parse_int, token

bp = Blueprint("tryon", __name__, url_prefix="/api")


def _job_public(job):
    return {"id": job.id, "status": job.status, "error": job.error or None, "product_id": job.product_id,
            "created_at": iso(job.created_at), "expires_at": iso(job.expires_at), "keep": job.keep,
            "result": f"/api/try-on/jobs/{job.id}/image" if job.status == "completed" else None,
            "demo": current_app.config["CLOTHES"].TRYON_PROVIDER == "demo"}


def _own_job(job_id):
    job = db().get(TryOnJob, job_id) if 10 < len(job_id) < 41 else None
    return job if job is not None and job.visitor == current_visitor() else None


@bp.get("/try-on/status")
def status():
    cfg = current_app.config["CLOTHES"]
    return jsonify(enabled=tryon.enabled(cfg), demo=cfg.TRYON_PROVIDER == "demo",
                   retention_hours=cfg.PHOTO_RETENTION_HOURS, daily_limit=cfg.TRYON_DAILY_LIMIT)


@bp.post("/try-on/jobs")
def create_job():
    cfg = current_app.config["CLOTHES"]
    photo = request.files.get("photo")
    product_id = parse_int(request.form.get("product_id"))
    if photo is None or not photo.filename:
        return error("Suratingizni tanlang.", 400, "NO_PHOTO")
    s = db()
    product = s.scalar(public_products_query().where(Product.id == product_id)) if product_id else None
    if product is None:
        return error("Kiyim topilmadi.", 400, "NOT_FOUND")
    if request.form.get("consent") != "1":
        return error("Suratni qayta ishlashga rozilik bering.", 400, "CONSENT_REQUIRED")
    try:
        image = load_image(photo.stream, cfg.MAX_IMAGE_PIXELS)
    except ImageError as exc:
        return error(str(exc), 415, "BAD_IMAGE")
    if not tryon.enabled(cfg):
        return error("AI kiyib koʻrish hali ulanmagan. Suratingiz saqlanmadi.", 503, "AI_NOT_CONFIGURED")
    limited = rate_limit("tryon", 20, 3600)
    if limited:
        return limited
    visitor = current_visitor()
    today = s.scalar(select(func.count(TryOnJob.id)).where(
        TryOnJob.visitor == visitor, TryOnJob.created_at >= utcnow() - timedelta(days=1)))
    if today >= cfg.TRYON_DAILY_LIMIT:
        return error(f"Bir kunda {cfg.TRYON_DAILY_LIMIT} marta kiyib koʻrish mumkin. Ertaga davom eting.",
                     429, "DAILY_LIMIT")
    job_id = token(18)
    name = f"{job_id}-in.webp"
    save_webp(image.convert("RGB"), tryon.private_dir(cfg) / name, 1536, quality=90)
    job = TryOnJob(id=job_id, visitor=visitor, product_id=product.id, photo_path=name,
                   expires_at=utcnow() + timedelta(hours=cfg.PHOTO_RETENTION_HOURS))
    s.add(job)
    record_event(s, "tryon", product.shop_id, product.id, visitor)
    s.commit()
    tryon.start(current_app._get_current_object(), job_id)
    return jsonify(job=_job_public(job)), 202


@bp.get("/try-on/jobs")
def list_jobs():
    rows = db().scalars(select(TryOnJob).where(TryOnJob.visitor == current_visitor())
                        .order_by(TryOnJob.created_at.desc()).limit(30)).all()
    return jsonify(items=[_job_public(j) for j in rows])


@bp.get("/try-on/jobs/<job_id>")
def get_job(job_id):
    job = _own_job(job_id)
    if job is None:
        return error("Topilmadi.", 404, "NOT_FOUND")
    return jsonify(job=_job_public(job))


@bp.get("/try-on/jobs/<job_id>/image")
def job_image(job_id):
    job = _own_job(job_id)
    if job is None or job.status != "completed" or not job.result_path:
        return error("Topilmadi.", 404, "NOT_FOUND")
    path = tryon.private_dir(current_app.config["CLOTHES"]) / job.result_path
    if not path.is_file():
        return error("Topilmadi.", 404, "NOT_FOUND")
    response = send_file(path, mimetype="image/webp", max_age=0)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@bp.post("/try-on/jobs/<job_id>/keep")
def keep_job(job_id):
    job = _own_job(job_id)
    if job is None:
        return error("Topilmadi.", 404, "NOT_FOUND")
    cfg = current_app.config["CLOTHES"]
    job.keep = bool((request.get_json(silent=True) or {}).get("keep"))
    job.expires_at = utcnow() + (timedelta(days=30) if job.keep else timedelta(hours=cfg.PHOTO_RETENTION_HOURS))
    db().commit()
    return jsonify(job=_job_public(job))


@bp.delete("/try-on/jobs/<job_id>")
def delete_job(job_id):
    job = _own_job(job_id)
    if job is None:
        return error("Topilmadi.", 404, "NOT_FOUND")
    tryon.delete_job_files(current_app.config["CLOTHES"], job)
    db().delete(job)
    db().commit()
    return jsonify(ok=True)


@bp.delete("/me/data")
def delete_my_data():
    """One button: remove try-on photos and results, shares, votes; anonymise reservations."""
    visitor = current_visitor()
    cfg = current_app.config["CLOTHES"]
    s = db()
    jobs = s.scalars(select(TryOnJob).where(TryOnJob.visitor == visitor)).all()
    for job in jobs:
        tryon.delete_job_files(cfg, job)
        s.delete(job)
    shares = s.scalars(select(Share.token).where(Share.visitor == visitor)).all()
    if shares:
        s.execute(delete(ShareVote).where(ShareVote.share_token.in_(shares)))
        s.execute(delete(Share).where(Share.token.in_(shares)))
    s.execute(delete(ShareVote).where(ShareVote.voter == visitor))
    s.execute(update(Reservation).where(Reservation.visitor == visitor,
                                        Reservation.status.in_(("pending", "confirmed")))
              .values(status="cancelled"))
    s.execute(update(Reservation).where(Reservation.visitor == visitor)
              .values(name="(oʻchirilgan)", phone="", note="", visitor="", buyer_id=None))
    if visitor.startswith("tg:"):
        s.execute(delete(Buyer).where(Buyer.telegram_id == int(visitor[3:])))
    s.commit()
    return jsonify(ok=True, tryon_deleted=len(jobs), shares_deleted=len(shares))
