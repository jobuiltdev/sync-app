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
    "apps.payments",
]

MIDDLEWARE = [
    # First, so that every log line produced while handling a request carries the
    # id, including ones written by middleware below it.
    "apps.common.middleware.RequestIDMiddleware",
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

# Reuse a connection for this many seconds rather than opening one per request.
# Zero locally, where a new connection costs nothing and a stale one is
# confusing; production sets it. Django holds connections per worker process, so
# this is not a pool: the ceiling on PostgreSQL connections is worker processes
# times threads, which is the number to watch when scaling out.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DATABASE_CONN_MAX_AGE", default=0)
# Checks a reused connection is still usable before handing it to a request,
# which is what stops a database restart producing a wave of errors.
DATABASES["default"]["CONN_HEALTH_CHECKS"] = env.bool("DATABASE_CONN_HEALTH_CHECKS", default=False)

#: Only config.settings.prod sets this. Everything gated on it, which is every
#: production configuration check, is inert in development and in tests.
IS_PRODUCTION = False

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
        "PayoutStatus": "apps.payments.payouts.PayoutStatus",
        "SettlementStatus": "apps.payments.settlements.SettlementStatus",
        "Currency": "apps.payments.money.Currency",
    },
}

# Phone verification timings and limits, in one place. The console provider is
# the development default and prints the code instead of sending it; production
# must set SMS_BACKEND to a real provider.
SMS_BACKEND = env("SMS_BACKEND", default="apps.accounts.sms.console.ConsoleSMSProvider")

# Termii, the documented production choice. Read whatever SMS_BACKEND is set to,
# so a deployment that has not switched over carries empty values harmlessly.
# SENDER_ID must be one Termii has approved for the account; an unapproved sender
# is the usual reason messages are accepted and never delivered.
TERMII = {
    "API_KEY": env("TERMII_API_KEY", default=""),
    "SENDER_ID": env("TERMII_SENDER_ID", default="Sync"),
    "CHANNEL": env("TERMII_CHANNEL", default="dnd"),
    "API_ROOT": env("TERMII_API_ROOT", default="https://api.ng.termii.com"),
    "TIMEOUT_SECONDS": env.int("TERMII_TIMEOUT_SECONDS", default=20),
}

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

# Resend, for the same reason Termii was chosen for SMS: one API key and a
# verified domain is the whole setup, against an AWS account, an SES sandbox exit
# request and IAM for the alternative. docs/architecture.md left this open
# between Resend and SES; the decision and its reasoning are recorded there now.
# Switching to SES is a different EMAIL_BACKEND and no other change.
RESEND = {
    "API_KEY": env("RESEND_API_KEY", default=""),
    "API_ROOT": env("RESEND_API_ROOT", default="https://api.resend.com"),
    "TIMEOUT_SECONDS": env.int("RESEND_TIMEOUT_SECONDS", default=20),
}

# What Sync keeps from a completed booking, in basis points: an integer
# hundredth of a percent, so 2000 is twenty percent. Basis points rather than a
# percentage because the whole money path is integer arithmetic and a percentage
# invites a float into it.
#
# One flat rate across every category. docs/architecture.md records per-category
# commission as an open question, and answering it here by quietly adding a rate
# column to Service would settle a pricing decision nobody has taken. The rate
# each settlement used is copied onto that settlement, so moving this value
# affects the next completed booking and can never reach a past one.
PLATFORM_COMMISSION = {
    "RATE_BPS": env.int("PLATFORM_COMMISSION_RATE_BPS", default=2000),
}

# --- external providers ---------------------------------------------------
# Every integration is selected by a dotted path and configured from the
# environment. The defaults are the fake or console implementations, so a clean
# checkout runs, and its tests pass, with no external account anywhere. Nothing
# here opens a connection at import: each adapter is constructed on use.

# Takes money from customers. The fake gateway moves nothing and reports every
# payment as pending until a test says otherwise.
PAYMENT_GATEWAY = env("PAYMENT_GATEWAY", default="apps.payments.gateways.fake.FakeGateway")

# Signs and checks webhooks for the fake gateway, so the whole webhook path
# including signature rejection is exercised without a Paystack account. Not a
# production credential: with the real gateway configured this is never read.
PAYMENT_GATEWAY_FAKE = {
    "SECRET": env("PAYMENT_GATEWAY_FAKE_SECRET", default="fake-gateway-signing-secret"),
}

# Paystack. Both keys come from the dashboard. The secret key signs API requests
# and verifies webhook signatures and must never leave the server; the public key
# is safe in a client and is here only so one place describes the account.
PAYSTACK = {
    "SECRET_KEY": env("PAYSTACK_SECRET_KEY", default=""),
    "PUBLIC_KEY": env("PAYSTACK_PUBLIC_KEY", default=""),
    "CURRENCY": "NGN",
    "TIMEOUT_SECONDS": env.int("PAYSTACK_TIMEOUT_SECONDS", default=20),
}

# Confirms that a payout destination is a real account before money is sent to
# it. Paystack resolves account numbers, so the same credentials serve both.
BANK_RESOLVER = env("BANK_RESOLVER", default="apps.payments.banks.fake.FakeBankResolver")

# --- background work ------------------------------------------------------
# Celery over the Redis that is already here for the cache, which is what
# docs/architecture.md has specified since M0. Importing Django starts nothing:
# a worker and a scheduler are separate processes, started deliberately.
#
#   worker:    celery -A config worker --loglevel=info
#   scheduler: celery -A config beat --loglevel=info
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=env("REDIS_URL"))
# Results are stored so an operator can ask what a task returned. Small payloads
# with a short life: nothing here needs a task result a day later.
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=env("REDIS_URL"))
CELERY_RESULT_EXPIRES = 3600

CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True

# A task that has not finished in five minutes is stuck. The soft limit raises an
# exception the task can still record something from; the hard one kills it.
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=300)
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=360)

# Acknowledge after the task finishes, so a worker killed mid-task returns the
# job to the queue rather than losing it. Safe because every task here is
# idempotent, which is the precondition for late acknowledgement.
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_CONCURRENCY = env.int("CELERY_WORKER_CONCURRENCY", default=4)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# How much each sweep looks at in one run. Bounded so a bad day cannot produce a
# task that holds locks for minutes; whatever is left is picked up next time.
TASK_BATCH_SIZE = env.int("TASK_BATCH_SIZE", default=200)

# How the periodic work is spaced. Conservative on purpose: two of these talk to
# Paystack, and a tight schedule against a rate-limited API is its own outage.
# Every interval is seconds and every one is configurable.
CELERY_BEAT_SCHEDULE = {
    "expire-stale-offers": {
        "task": "apps.bookings.tasks.expire_stale_offers",
        # Offers expire on a fifteen minute window, so a minute of lag either way
        # costs a provider nothing and keeps a customer from waiting on a job
        # nobody can take any more.
        "schedule": env.int("SCHEDULE_OFFER_EXPIRY_SECONDS", default=60),
    },
    "reconcile-pending-payments": {
        "task": "apps.payments.tasks.reconcile_pending_payments",
        # Talks to the payment provider. Five minutes is far more often than a
        # customer waiting on a slow bank transfer needs, and gentle on the API.
        "schedule": env.int("SCHEDULE_PAYMENT_RECONCILIATION_SECONDS", default=300),
    },
    "reconcile-payouts": {
        "task": "apps.payments.tasks.reconcile_payouts",
        # The one that resolves a submitted transfer whose outcome we never saw.
        "schedule": env.int("SCHEDULE_PAYOUT_RECONCILIATION_SECONDS", default=300),
    },
    "retire-stale-challenges": {
        "task": "apps.accounts.tasks.retire_stale_challenges",
        # Housekeeping. Hourly is plenty for something that only tidies rows that
        # are already unusable.
        "schedule": env.int("SCHEDULE_CHALLENGE_CLEANUP_SECONDS", default=3600),
    },
    "sweep-financial-consistency": {
        "task": "apps.payments.tasks.sweep_financial_consistency",
        # Reads our own rows only. Hourly, because an anomaly nobody has noticed
        # for an hour is not much worse than one nobody has noticed for a minute,
        # and this is the slowest query of the five.
        "schedule": env.int("SCHEDULE_CONSISTENCY_SWEEP_SECONDS", default=3600),
    },
}

# When a payment is old enough to be worth asking the provider about. Shorter
# than this and we would be chasing customers who are still typing their card
# number into the checkout page.
PAYMENT_RECONCILIATION = {
    "PENDING_AFTER_SECONDS": env.int("PAYMENT_PENDING_AFTER_SECONDS", default=900),
    # After this, a payment nobody can resolve stops being swept and is left for
    # an operator. Sweeping the same unanswerable payment forever is how a real
    # problem gets lost among noise.
    "GIVE_UP_AFTER_SECONDS": env.int("PAYMENT_GIVE_UP_AFTER_SECONDS", default=7 * 24 * 3600),
}

# How long a submitted transfer may sit unresolved before it is flagged for a
# person. The provider usually answers in seconds; an hour means something is
# wrong that reconciliation alone will not fix.
PAYOUT_EXECUTION = {
    "STALE_AFTER_SECONDS": env.int("PAYOUT_STALE_AFTER_SECONDS", default=3600),
}

# Moves money out to providers. The fake submits nothing and reports every
# transfer as pending until a test says otherwise.
PAYOUT_TRANSFER_PROVIDER = env(
    "PAYOUT_TRANSFER_PROVIDER", default="apps.payments.transfers.fake.FakeTransferProvider"
)

# How long a provider has to answer an offer. Long enough that somebody working
# does not lose a job by not looking at their phone, short enough that a customer
# is not left waiting on a provider who has stopped reading.
BOOKING_OFFERS = {
    "TTL_SECONDS": 900,
}

CORS_ALLOWED_ORIGINS: list[str] = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])

# One JSON object per line when LOG_FORMAT is json, which is what production
# sets: logs are read by a machine before a person, and a line needing a regex is
# a line nobody greps correctly at three in the morning. Development keeps the
# readable format, where the audience really is a person at a terminal.
#
# Every record carries the current request id, or a dash when there is no request
# in flight, which is every Celery task. See apps/common/log.py for the rule
# about what may never reach a log at all.
LOG_FORMAT = env("LOG_FORMAT", default="console")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.common.middleware.RequestIDFilter"},
    },
    "formatters": {
        "standard": {
            "format": "{asctime} {levelname} [{request_id}] {name} {message}",
            "style": "{",
        },
        "json": {"()": "apps.common.log.JSONFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if LOG_FORMAT == "json" else "standard",
            "filters": ["request_id"],
        },
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
    "loggers": {
        # Django logs every 4xx and 5xx here. Kept at WARNING so a flood of 404s
        # from a scanner does not bury anything, and so 500s are always visible.
        "django.request": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        # The financial domain. Its INFO lines are the audit trail for money
        # moving, so they are never filtered out by a coarser root level.
        "apps.payments": {"level": "INFO", "handlers": ["console"], "propagate": False},
    },
}
