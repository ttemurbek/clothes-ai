"""AI photographer for shops: cut the garment out of a phone photo and place it on a studio background.

PHOTO_PROVIDER:
  none  - off (default)
  rembg - local background removal (`pip install rembg`, downloads an ONNX model on first use)
  http  - POST the photo to PHOTO_API_URL (Bearer PHOTO_API_KEY); the reply must be a PNG/WebP with alpha
"""
import io

import requests
from PIL import Image, ImageFilter


class PhotoError(RuntimeError):
    pass


def _cutout(image, cfg):
    provider = cfg.PHOTO_PROVIDER
    if provider == "rembg":
        try:
            from rembg import remove  # optional dependency
        except ImportError as exc:
            raise PhotoError("AI fotograf moduli (rembg) oʻrnatilmagan.") from exc
        return remove(image.convert("RGB")).convert("RGBA")
    if provider == "http":
        if not cfg.PHOTO_API_URL:
            raise PhotoError("AI fotograf manzili sozlanmagan.")
        buf = io.BytesIO()
        image.convert("RGB").save(buf, "JPEG", quality=92)
        try:
            response = requests.post(cfg.PHOTO_API_URL, files={"image": ("photo.jpg", buf.getvalue(), "image/jpeg")},
                                     headers={"Authorization": f"Bearer {cfg.PHOTO_API_KEY}"} if cfg.PHOTO_API_KEY
                                     else {}, timeout=60)
            response.raise_for_status()
            return Image.open(io.BytesIO(response.content)).convert("RGBA")
        except (requests.RequestException, OSError) as exc:
            raise PhotoError("AI fotograf javob bermadi. Oddiy rasm saqlandi.") from exc
    raise PhotoError("AI fotograf hali ulanmagan. Oddiy rasm saqlandi.")


def studio(image, cfg, size=1200):
    """Return a square RGB catalog image: soft studio background, centred subject, light shadow."""
    cut = _cutout(image, cfg)
    box = cut.getchannel("A").getbbox()
    if not box:
        raise PhotoError("Rasmda kiyim aniqlanmadi. Oddiy rasm saqlandi.")
    cut = cut.crop(box)
    cut.thumbnail((int(size * 0.82), int(size * 0.86)), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (size, size), (250, 249, 246))
    top, bottom = (252, 251, 249), (236, 232, 226)
    gradient = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        gradient.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    canvas.paste(gradient.resize((size, size)))

    x = (size - cut.width) // 2
    y = (size - cut.height) // 2 + int(size * 0.02)
    shadow = Image.new("L", (size, size), 0)
    shadow.paste(cut.getchannel("A").point(lambda a: a * 0.28), (x + 10, y + 16))
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas.paste((60, 50, 40), (0, 0, size, size), shadow)
    canvas.paste(cut, (x, y), cut)
    return canvas
