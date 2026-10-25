"""Gunicorn entry point: `gunicorn backend.wsgi:app`."""
from .app import create_app

app = create_app()
