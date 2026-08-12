"""Settings shared by every environment.

Environment modules import everything from here and override only what differs.
No credential or secret value belongs in this file: everything sensitive is read
from the environment, and the environments that require a value read it without a
fallback so a missing one fails loudly at startup rather than silently degrading.
"""

from datetime import timedelta
from pathlib import Path

import environ

# backend/config/settings/base.py -> backend/
BASE_DIR = Path(__file__).resolve().parents[2]
# backend/ -> repository root, where .env and docker-compose.yml live
ROOT_DIR = BASE_DIR.parent

env = environ.Env()
environ.Env.read_env(ROOT_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="")
DEBUG = False
ALLOWED_HOSTS: list[str] = env.list("DJANGO_ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    "apps.common",
    "apps.accounts",
    "apps.catalog",
    "apps.providers",
    "apps.bookings",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL")}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
    }
}

AUTH_USER_MODEL = "accounts.User"

# Argon2 first, so new and rehashed passwords use it. The rest of the chain stays
# so any hash written by an earlier default can still be verified and upgraded on
# the owner's next successful login.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("email", "phone", "first_name", "last_name")},
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Endpoints are private unless they opt out. Public routes such as the health
    # check declare AllowAny explicitly, so forgetting a permission fails closed.
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.api_exception_handler",
    # Page numbers suit the catalog, which is small, stable and browsed by a person.
    # Time-ordered feeds such as booking history move to cursor pagination when they
    # arrive, since page numbers shift under inserts. Small owned collections opt out
    # entirely with pagination_class = None.
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # Verification hashes a code with Argon2 on every attempt, which is deliberate
    # CPU cost. These bound how much of it an unauthenticated flood can provoke;
    # the per-challenge attempt cap and resend cooldown do the rest.
    "DEFAULT_THROTTLE_RATES": {
        "phone_verification_request": "10/hour",
        "phone_verification_confirm": "20/hour",
        "email_verification_request": "10/hour",
        "email_verification_confirm": "20/hour",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    # Rotation means a refresh token is single use. Blacklisting the one just spent
    # is what makes that real: without it a stolen refresh token stays valid for its
    # full thirty days even after the legitimate owner has used it.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Sync API",
    "DESCRIPTION": "Everyday services marketplace API.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    # Booking status appears on several fields. Naming it once stops the generator
    # emitting a differently named enum component per field.
    "ENUM_NAME_OVERRIDES": {
        "BookingStatus": "apps.bookings.state.BookingStatus",
        "OfferStatus": "apps.bookings.offers.OfferStatus",
        "OfferKind": "apps.bookings.offers.OfferKind",
    },
}

# Phone verification timings and limits, in one place. The console provider is
# the development default and prints the code instead of sending it; production
# must set SMS_BACKEND to a real provider.
SMS_BACKEND = env("SMS_BACKEND", default="apps.accounts.sms.console.ConsoleSMSProvider")

PHONE_VERIFICATION = {
    "CODE_LENGTH": 6,
    "TTL_SECONDS": 600,
    "MAX_ATTEMPTS": 5,
    "RESEND_COOLDOWN_SECONDS": 60,
    "MAX_SENDS_PER_WINDOW": 5,
    "SEND_WINDOW_SECONDS": 3600,
}

# Email codes live longer than SMS ones. Mail queues, gets filtered and gets read
# later, so a ten minute window would expire on people through no fault of theirs.
EMAIL_VERIFICATION = {
    "CODE_LENGTH": 6,
    "TTL_SECONDS": 1800,
    "MAX_ATTEMPTS": 5,
    "RESEND_COOLDOWN_SECONDS": 60,
    "MAX_SENDS_PER_WINDOW": 5,
    "SEND_WINDOW_SECONDS": 3600,
}

# Django's own email framework is the abstraction; the backend setting selects the
# implementation. The default prints to the console and sends nothing. No real
# mail provider is configured.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Sync <no-reply@sync.ng>")

# How long a provider has to answer an offer. Long enough that somebody working
# does not lose a job by not looking at their phone, short enough that a customer
# is not left waiting on a provider who has stopped reading.
BOOKING_OFFERS = {
    "TTL_SECONDS": 900,
}

CORS_ALLOWED_ORIGINS: list[str] = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
}
