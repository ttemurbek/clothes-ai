"""Image intake: decode with Pillow, reject anything that is not a real photo, re-encode.

Re-encoding drops EXIF (GPS location, device) and any payload hidden after the image data.
"""
import io

from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED = {"JPEG", "PNG", "WEBP"}


class ImageError(ValueError):
    pass


def load_image(stream, max_pixels):
    data = stream.read()
    if not data:
        raise ImageError("Rasm boʻsh.")
    Image.MAX_IMAGE_PIXELS = max_pixels
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ALLOWED:
                raise ImageError("Faqat JPEG, PNG yoki WebP qabul qilinadi.")
            probe.verify()
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise ImageError("Rasm formati notoʻgʻri yoki fayl buzilgan.") from exc
    if image.width < 200 or image.height < 200:
        raise ImageError("Rasm juda kichik (kamida 200×200 px).")
    image = ImageOps.exif_transpose(image)
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    return image


def save_webp(image, path, max_side, quality=84):
    image = image.copy()
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    image.save(path, "WEBP", quality=quality, method=5)
    return image.size
