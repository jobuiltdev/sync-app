"""Test settings.

Used by pytest, by `manage.py test`, and by the mypy django-stubs plugin. It must
therefore import cleanly whenever DATABASE_URL and REDIS_URL are present, without
needing any other configuration.
"""

from config.settings.base import *  # noqa: F403
from config.settings.base import env

DEBUG = False

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-test-only")

ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

# Hashing is irrelevant to what these tests assert and dominates their runtime.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# The health check exercises the real cache backend, so tests need a working one
# rather than a local-memory stand-in.
