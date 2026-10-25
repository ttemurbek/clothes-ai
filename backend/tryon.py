"""Virtual try-on: asynchronous jobs, pluggable providers, short-lived private photo storage.

TRYON_PROVIDER:
  none - feature off (default). Uploads are rejected before anything is stored.
  demo - local UI testing only: the "result" is your own photo with a DEMO label, no AI.
  http - a commercially licensed try-on service at TRYON_API_URL (Bearer TRYON_API_KEY). The request is
         multipart `person_image` + `garment_image` + `category`; the reply is an image, or JSON with
         `image_base64` or `image_url`.
"""
import base64
import io
import logging
import threading
import time
from datetime import timedelta
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageOps

from .images import save_webp
from .models import Product, TryOnJob, utcnow

log = logging.getLogger(__name__)
_lock = threading.Semaphore(2)  # at most two jobs talk to the provider at once


class TryOnError(RuntimeError):
    pass


def private_dir(cfg):
    return Path(cfg.DATA_DIR) / "private" / "tryon"


def _demo(person, product, cfg):
    image = ImageOps.fit(person.convert("RGB"), (768, 1024), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((0, 0, 768, 92), fill=(20, 18, 24, 190))
    draw.text((24, 18), "DEMO - bu AI natija emas", fill=(255, 255, 255, 255), font_size=34)
    draw.text((24, 58), product.name[:48], fill=(220, 205, 245, 255), font_size=24)
    return image


def _garment_bytes(product, cfg):
    if not product.image:
        raise TryOnError("Bu mahsulotning rasmi yoʻq, shuning uchun kiyib koʻrib boʻlmaydi.")
    path = Path(cfg.DATA_DIR) / "media" / "products" / product.image
    if not path.is_file():
        raise TryOnError("Mahsulot rasmi topilmadi.")
    return path.read_bytes()


def _http(person, product, cfg):
    if not cfg.TRYON_API_URL:
        raise TryOnError("Try-on xizmati manzili sozlanmagan.")
    buf = io.BytesIO()
    person.convert("RGB").save(buf, "JPEG", quality=92)
    files = {"person_image": ("person.jpg", buf.getvalue(), "image/jpeg"),
             "garment_image": ("garment.webp", _garment_bytes(product, cfg), "image/webp")}
    headers = {"Authorization": f"Bearer {cfg.TRYON_API_KEY}"} if cfg.TRYON_API_KEY else {}
    try:
        response = requests.post(cfg.TRYON_API_URL, files=files, data={"category": product.category},
                                 headers=headers, timeout=cfg.TRYON_TIMEOUT)
        response.raise_for_status()
        if response.headers.get("Content-Type", "").startswith("image/"):
            raw = response.content
        else:
            body = response.json()
            if body.get("image_base64"):
                raw = base64.b64decode(body["image_base64"])
            elif body.get("image_url", "").startswith("https://"):
                raw = requests.get(body["image_url"], timeout=60).content
            else:
                raise TryOnError("Try-on xizmati natija qaytarmadi.")
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except (requests.RequestException, ValueError, OSError) as exc:
        log.warning("try-on provider failed: %s", type(exc).__name__)
        raise TryOnError("Try-on xizmati hozir javob bermadi. Keyinroq urinib koʻring.") from exc


PROVIDERS = {"demo": _demo, "http": _http}


def enabled(cfg):
    return cfg.TRYON_PROVIDER in PROVIDERS


def start(app, job_id):
    thread = threading.Thread(target=_run, args=(app, job_id), daemon=True)
    thread.start()
    return thread


def _run(app, job_id):
    cfg = app.config["CLOTHES"]
    Session = app.extensions["clothes_db"].Session
    with _lock, Session() as s:
        job = s.get(TryOnJob, job_id)
        if job is None:
            return
        job.status = "processing"
        s.commit()
        person_path = private_dir(cfg) / job.photo_path
        try:
            product = s.get(Product, job.product_id)
            with Image.open(person_path) as person:
                person.load()
                result = PROVIDERS[cfg.TRYON_PROVIDER](person, product, cfg)
            name = f"{job.id}-out.webp"
            save_webp(result, private_dir(cfg) / name, 1280, quality=88)
            job.result_path, job.status = name, "completed"
        except TryOnError as exc:
            job.status, job.error = "failed", str(exc)[:255]
        except Exception:  # never leave a job stuck in "processing"
            log.exception("try-on job crashed")
            job.status, job.error = "failed", "Kutilmagan xato. Qayta urinib koʻring."
        finally:
            person_path.unlink(missing_ok=True)  # the original photo is not kept after processing
            job.photo_path = ""
            s.commit()


def delete_job_files(cfg, job):
    for name in (job.photo_path, job.result_path):
        if name:
            (private_dir(cfg) / name).unlink(missing_ok=True)


def purge_expired(app):
    """Delete try-on photos/results past their retention time. Returns how many jobs were removed."""
    cfg = app.config["CLOTHES"]
    with app.extensions["clothes_db"].Session() as s:
        jobs = s.query(TryOnJob).filter(TryOnJob.expires_at < utcnow()).all()
        for job in jobs:
            delete_job_files(cfg, job)
            s.delete(job)
        # stuck jobs (process restarted mid-run)
        stale = utcnow() - timedelta(minutes=15)
        for job in s.query(TryOnJob).filter(TryOnJob.status.in_(("queued", "processing")),
                                            TryOnJob.created_at < stale):
            delete_job_files(cfg, job)
            job.status, job.error, job.photo_path = "failed", "Vaqt tugadi. Qayta urinib koʻring.", ""
        s.commit()
    # files whose job row is gone
    known = set()
    with app.extensions["clothes_db"].Session() as s:
        for photo, result in s.query(TryOnJob.photo_path, TryOnJob.result_path):
            known.update(filter(None, (photo, result)))
    cutoff = time.time() - 600
    for path in private_dir(cfg).glob("*.webp"):
        if path.name not in known and path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)
    return len(jobs)
