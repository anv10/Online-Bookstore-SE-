"""Explicit offline preview/test profile; PostgreSQL remains the project default."""
import os
os.environ.setdefault("DJANGO_SECRET_KEY", "offline-preview-only-never-deploy")
os.environ.setdefault("DB_PASSWORD", "unused-offline")
from .settings import *
DEBUG = True
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
