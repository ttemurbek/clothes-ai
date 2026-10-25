"""Settings read from the environment (see .env.example). Secrets never live in code."""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _load_dotenv(path):
    """Minimal .env reader so local runs work without python-dotenv."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _secret_key(data_dir):
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    if os.environ.get("APP_ENV") == "production":
        raise RuntimeError("SECRET_KEY must be set in production")
    # Development: keep one key across restarts so sessions survive.
    path = data_dir / ".secret_key"
    if path.is_file():
        return path.read_text().strip()
    key = secrets.token_hex(32)
    path.write_text(key)
    path.chmod(0o600)
    return key


class Config:
    def __init__(self, **overrides):
        if not overrides.get("TESTING"):
            _load_dotenv(ROOT / ".env")
        self.ENV = os.environ.get("APP_ENV", "development")
        self.TESTING = False
        self.DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
        self.DATABASE_URL = os.environ.get("DATABASE_URL", "")
        self.SEED_DEMO = _env_bool("SEED_DEMO", True)
        self.TRUST_PROXY = _env_bool("TRUST_PROXY", self.ENV == "production")
        self.PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")

        # Uploads
        self.MAX_CONTENT_LENGTH = 8 * 1024 * 1024
        self.MAX_IMAGE_PIXELS = 40_000_000
        self.PRODUCT_IMAGE_SIZE = 1200

        # Reservations
        self.RESERVATION_CONFIRM_HOURS = int(os.environ.get("RESERVATION_CONFIRM_HOURS", "3"))
        self.RESERVATION_HOLD_HOURS = int(os.environ.get("RESERVATION_HOLD_HOURS", "24"))
        self.MAX_ACTIVE_RESERVATIONS = 3

        # Try-on: "none" keeps the feature off; "demo" is for local UI work only
        self.TRYON_PROVIDER = os.environ.get("TRYON_PROVIDER", "none").strip().lower()
        self.TRYON_API_URL = os.environ.get("TRYON_API_URL", "")
        self.TRYON_API_KEY = os.environ.get("TRYON_API_KEY", "")
        self.TRYON_TIMEOUT = int(os.environ.get("TRYON_TIMEOUT", "120"))
        self.PHOTO_RETENTION_HOURS = int(os.environ.get("PHOTO_RETENTION_HOURS", "24"))
        self.TRYON_DAILY_LIMIT = int(os.environ.get("TRYON_DAILY_LIMIT", "10"))

        # AI photographer (background removal) for shop photos
        self.PHOTO_PROVIDER = os.environ.get("PHOTO_PROVIDER", "none").strip().lower()
        self.PHOTO_API_URL = os.environ.get("PHOTO_API_URL", "")
        self.PHOTO_API_KEY = os.environ.get("PHOTO_API_KEY", "")

        # Telegram
        self.TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "").lstrip("@")
        self.TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
        self.TELEGRAM_INITDATA_MAX_AGE = 24 * 3600

        for key, value in overrides.items():
            setattr(self, key, value)

        self.DATA_DIR = Path(self.DATA_DIR)
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        (self.DATA_DIR / "media" / "products").mkdir(parents=True, exist_ok=True)
        (self.DATA_DIR / "private" / "tryon").mkdir(parents=True, exist_ok=True)
        if not self.DATABASE_URL:
            self.DATABASE_URL = "sqlite:///" + str(self.DATA_DIR / "clothes.db")
        if self.DATABASE_URL.startswith("postgres://"):
            self.DATABASE_URL = "postgresql+psycopg://" + self.DATABASE_URL[len("postgres://"):]
        self.SECRET_KEY = overrides.get("SECRET_KEY") or _secret_key(self.DATA_DIR)

    def as_flask(self):
        return {
            "SECRET_KEY": self.SECRET_KEY,
            "TESTING": self.TESTING,
            "MAX_CONTENT_LENGTH": self.MAX_CONTENT_LENGTH,
            "SESSION_COOKIE_HTTPONLY": True,
            "SESSION_COOKIE_SAMESITE": "Lax",
            "SESSION_COOKIE_SECURE": self.ENV == "production",
            "PERMANENT_SESSION_LIFETIME": 14 * 24 * 3600,
            "JSON_AS_ASCII": False,
        }
