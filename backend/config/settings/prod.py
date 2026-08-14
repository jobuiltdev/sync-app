"""Production settings.

Two rules run through this file.

**Nothing falls back to a development value.** Anything that must be set is read
without a default, so a missing variable stops the process at import rather than
booting into a subtly wrong state. Anything that cannot be checked that way is
checked by `apps/common/checks.py`, which refuses to let the process start with a
fake payment provider or an empty Paystack key.

**Nothing here is imposed on development.** Every hardening below applies to this
module alone. Local development keeps its permissive hosts, its plain HTTP and
its console providers, because a security setting that makes local development
painful is a security setting somebody eventually turns off everywhere.
"""

import copy

from config.settings.base import *  # noqa: F403
from config.settings.base import DATABASES as BASE_DATABASES
from config.settings.base import REST_FRAMEWORK, env

#: What makes the production checks in apps/common/checks.py active. Nothing else
#: sets it, so those checks are inert in development and in the test suite.
IS_PRODUCTION = True

DEBUG = False

# Read without defaults. A deployment missing any of these must not start.
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CELERY_BROKER_URL = env("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)

# Payout execution moves real money to real people. A deployment that has not
# been given a transfer provider must not start and quietly leave every payout
# sitting in REQUESTED with nobody noticing.
PAYOUT_TRANSFER_PROVIDER = env("PAYOUT_TRANSFER_PROVIDER")
PAYMENT_GATEWAY = env("PAYMENT_GATEWAY")
BANK_RESOLVER = env("BANK_RESOLVER")
SMS_BACKEND = env("SMS_BACKEND")
EMAIL_BACKEND = env("EMAIL_BACKEND")

# --- transport -------------------------------------------------------------
# HSTS is a year, includes subdomains and is preload-ready. It is close to
# irreversible once a browser has seen it, so it is deliberate rather than a
# default, and the checks warn rather than error when it is off.
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# TLS terminates at the load balancer, so Django learns the original scheme from
# a header. This is only safe because nothing but the load balancer can reach
# this process: anything that can set the header can pretend to be HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_CONTENT_TYPE_NOSNIFF = True
# Send no referrer off-origin at all. This is an API and an admin; there is no
# outbound navigation whose destination has any business knowing the path a user
# came from, and admin paths are worth not leaking.
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# The admin is session-authenticated over the same domain, which is the whole
# reason these matter here.
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # Django's own admin JavaScript reads it.
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Needed for the admin behind HTTPS, and for nothing else: the API authenticates
# with a bearer token and is not CSRF-relevant.
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# No Content-Security-Policy is set. It is a browser mechanism, and the two
# things served here are a JSON API consumed by a native app, where it does
# nothing, and Django's own admin, whose inline scripts a useful policy would
# break. Setting a permissive one to look thorough would be worse than none.

# --- CORS ------------------------------------------------------------------
# An explicit list, never a wildcard. A native app sends no Origin header and
# needs none of this; it exists for the browsable schema and any future web
# surface. The check refuses to start if CORS_ALLOW_ALL_ORIGINS is on.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])

# --- database --------------------------------------------------------------
# Deep-copied rather than mutated. `from base import DATABASES` binds the same
# dictionary object, so editing it in place would reach back into the base
# settings, which matters the moment anything loads both.
DATABASES = copy.deepcopy(BASE_DATABASES)

# Connections are reused for ten minutes and health-checked before reuse, so a
# database restart does not produce a wave of errors from stale handles.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=600)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# Managed PostgreSQL almost always requires TLS. `require` encrypts without
# verifying the server certificate; `verify-full` also checks it and needs a root
# certificate on the host, which is the better setting where the platform
# supplies one.
DATABASES["default"].setdefault("OPTIONS", {})
DATABASES["default"]["OPTIONS"]["sslmode"] = env("DATABASE_SSLMODE", default="require")

# --- schema ----------------------------------------------------------------
# No browsable API in production: it is a debugging convenience that renders
# arbitrary API responses into HTML on an authenticated surface.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
}

# --- logging ---------------------------------------------------------------
# One JSON object per line. See apps/common/log.py for what may never be in
# one of them.
LOG_FORMAT = env("LOG_FORMAT", default="json")

# --- static ----------------------------------------------------------------
# Only the admin's own CSS and JavaScript. Collected at build time and served by
# whatever is in front of this process; there is no user-uploaded media yet, and
# when there is it belongs in object storage rather than on a container's disk.
STATIC_ROOT = env("DJANGO_STATIC_ROOT", default=str(BASE_DIR / "staticfiles"))  # noqa: F405
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Hashed filenames and a manifest, so the admin can be cached forever and
    # still change when it is redeployed.
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}
