"""Security headers, same-origin checks for state-changing requests and a small rate limiter."""
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from flask import current_app, request

from .utils import error

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://telegram.org https://unpkg.com",
    "style-src 'self' https://unpkg.com",
    "img-src 'self' data: blob: https://*.tile.openstreetmap.org https://unpkg.com",
    "connect-src 'self'",
    "font-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    # Telegram Web (web.telegram.org) renders Mini Apps in an iframe.
    "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org",
])


def add_headers(response):
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=(self), microphone=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


def check_origin():
    """Reject cross-site POST/PUT/PATCH/DELETE (CSRF) unless it is the Telegram webhook."""
    if request.method in ("GET", "HEAD", "OPTIONS") or request.path == "/telegram/webhook":
        return None
    origin = request.headers.get("Origin") or request.headers.get("Referer")
    if not origin:
        # Non-browser clients (curl, tests) send no Origin; browsers always do for fetch POSTs.
        return None if request.headers.get("Sec-Fetch-Site") in (None, "same-origin", "none") else \
            error("Soʻrov rad etildi.", 403, "BAD_ORIGIN")
    parts = urlsplit(origin)
    if f"{parts.scheme}://{parts.netloc}" != request.host_url.rstrip("/"):
        return error("Soʻrov rad etildi.", 403, "BAD_ORIGIN")
    return None


class RateLimiter:
    """Sliding-window limits per client key. In-memory: fine for one Gunicorn worker."""

    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key, limit, window):
        if current_app.config.get("TESTING") and not current_app.config.get("RATE_LIMIT_IN_TESTS"):
            return True
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            if len(self.hits) > 50_000:
                self.hits.clear()
            return True


limiter = RateLimiter()


def rate_limit(name, limit, window):
    key = f"{name}:{request.remote_addr}"
    if not limiter.allow(key, limit, window):
        return error("Juda koʻp soʻrov. Birozdan keyin urinib koʻring.", 429, "RATE_LIMITED")
    return None
