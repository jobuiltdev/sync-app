"""Production settings.

Values that must never fall back to a default are read without one, so a missing
environment variable stops the process at startup instead of booting insecurely.
"""

from config.settings.base import *  # noqa: F403
from config.settings.base import env

DEBUG = False

SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
X_FRAME_OPTIONS = "DENY"

# Payout execution moves real money to real people. A deployment that has not
# been given a transfer provider must not start and quietly leave every payout
# sitting in REQUESTED, so this is read without a fallback.
PAYOUT_TRANSFER_PROVIDER = env("PAYOUT_TRANSFER_PROVIDER")
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
