"""What must be true before this process is allowed to serve production traffic.

Django's system check framework rather than a bespoke validator, because it
already runs everywhere it needs to: `manage.py check`, `migrate`, `runserver`,
and a Celery worker through its Django fixup. An `Error` stops all of them, which
is the point. A deployment missing its Paystack key should refuse to start, not
start and then fail at the first payment with a customer watching.

**Every check here is inert outside production.** They are gated on
`settings.IS_PRODUCTION`, which only `config.settings.prod` sets, so local
development and the test suite keep their fakes and their conveniences.

The failure mode these exist to prevent is the quiet one. A missing secret key
raises on its own. A production deployment that silently kept the fake payment
gateway would take bookings, tell customers they had paid, and move no money at
all, and nothing would look wrong until somebody asked where the money was.
"""

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Warning, register

#: Anything whose dotted path contains one of these is a stand-in. Matching on
#: the path rather than on a list of class names means a fake added later is
#: caught without anybody remembering to update this.
FAKE_MARKERS = ("fake", "locmem", "console", "dummy", "inmemory")

#: The provider selections that must name something real in production, with what
#: goes wrong if they do not.
PROVIDER_SETTINGS = {
    "PAYMENT_GATEWAY": "customers would be told they had paid while no money moved",
    "BANK_RESOLVER": "payout accounts would be confirmed without any bank being asked",
    "PAYOUT_TRANSFER_PROVIDER": "payouts would be marked sent while no money left",
    "SMS_BACKEND": (
        "verification codes and job offers would be printed to a log instead of sent, "
        "so nobody could sign up and no provider would hear about work"
    ),
    "EMAIL_BACKEND": (
        "verification emails and every booking, payment and payout notice would be "
        "printed to a log instead of sent"
    ),
    "IDENTITY_PROVIDER": (
        "provider identity checks would return synthetic passes, so anybody who "
        "asked would reach a reviewer looking at a result no government register "
        "ever confirmed"
    ),
}

#: Credentials that must be present, keyed by the provider path that needs them.
#: Checked only when that provider is actually selected, so a deployment using
#: one payment provider is not asked for another's key.
CREDENTIALS = [
    ("PAYMENT_GATEWAY", "paystack", ("PAYSTACK", "SECRET_KEY"), "PAYSTACK_SECRET_KEY"),
    ("BANK_RESOLVER", "paystack", ("PAYSTACK", "SECRET_KEY"), "PAYSTACK_SECRET_KEY"),
    (
        "PAYOUT_TRANSFER_PROVIDER",
        "paystack",
        ("PAYSTACK", "SECRET_KEY"),
        "PAYSTACK_SECRET_KEY",
    ),
    ("SMS_BACKEND", "termii", ("TERMII", "API_KEY"), "TERMII_API_KEY"),
    ("EMAIL_BACKEND", "resend", ("RESEND", "API_KEY"), "RESEND_API_KEY"),
]


def in_production() -> bool:
    return bool(getattr(settings, "IS_PRODUCTION", False))


def looks_fake(path: str) -> bool:
    return any(marker in path.lower() for marker in FAKE_MARKERS)


def _nested(names: tuple[str, str]) -> Any:
    container = getattr(settings, names[0], {}) or {}
    return container.get(names[1], "")


@register("sync.production")
def check_providers_are_real(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """Refuses to start production with a stand-in wired in where money moves.

    The single most valuable check in this module. Every one of these failures is
    silent at runtime: nothing errors, requests succeed, and the damage is only
    visible later when somebody reconciles.
    """
    if not in_production():
        return []

    problems: list[CheckMessage] = []

    for name, consequence in PROVIDER_SETTINGS.items():
        path = str(getattr(settings, name, "") or "")

        if not path:
            problems.append(
                Error(
                    f"{name} is not set.",
                    hint=f"Without it, {consequence}.",
                    id="sync.E001",
                )
            )
        elif looks_fake(path):
            problems.append(
                Error(
                    f"{name} is set to {path}, which is a development stand-in.",
                    hint=(
                        f"In production this means {consequence}. Set {name} to a real provider."
                    ),
                    id="sync.E002",
                )
            )

    return problems


@register("sync.production")
def check_provider_credentials(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """Refuses to start when a selected provider has no credentials.

    Checked per selection rather than as a blanket list, so a deployment that
    uses Paystack for payments but some other provider for SMS is asked only for
    what it actually needs.
    """
    if not in_production():
        return []

    problems: list[CheckMessage] = []

    for setting_name, vendor, credential, variable in CREDENTIALS:
        path = str(getattr(settings, setting_name, "") or "")
        if vendor not in path.lower():
            continue
        if _nested(credential):
            continue

        problems.append(
            Error(
                f"{setting_name} is set to {path} but {variable} is empty.",
                hint=f"Set {variable} in the environment.",
                id="sync.E003",
            )
        )

    return problems


@register("sync.production")
def check_required_configuration(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """The rest of what a deployment cannot function without."""
    if not in_production():
        return []

    problems: list[CheckMessage] = []

    if settings.DEBUG:
        problems.append(
            Error(
                "DEBUG is on in production.",
                hint="Debug pages expose settings, SQL and stack traces to anybody who "
                "triggers an error.",
                id="sync.E004",
            )
        )

    if not settings.ALLOWED_HOSTS or "*" in settings.ALLOWED_HOSTS:
        problems.append(
            Error(
                "ALLOWED_HOSTS is empty or accepts any host.",
                hint="Set DJANGO_ALLOWED_HOSTS to the hostnames this deployment serves.",
                id="sync.E005",
            )
        )

    if getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False):
        problems.append(
            Error(
                "CORS_ALLOW_ALL_ORIGINS is on in production.",
                hint="Set DJANGO_CORS_ALLOWED_ORIGINS to the origins that need it.",
                id="sync.E006",
            )
        )

    if not str(getattr(settings, "CELERY_BROKER_URL", "") or ""):
        problems.append(
            Error(
                "CELERY_BROKER_URL is not set.",
                hint="Without it no background work runs: offers never expire, payments "
                "are never reconciled, and payouts are never sent.",
                id="sync.E007",
            )
        )

    secret = str(getattr(settings, "SECRET_KEY", "") or "")
    if "insecure" in secret or len(secret) < 50:
        problems.append(
            Error(
                "DJANGO_SECRET_KEY is a development value or is too short.",
                hint="Generate one with django.core.management.utils.get_random_secret_key.",
                id="sync.E008",
            )
        )

    return problems


@register("sync.production")
def check_no_env_file_in_production(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """Warns when a production deployment is carrying a .env file.

    Real environment variables take precedence over the file, so its presence is
    not itself dangerous. What makes it worth flagging is that it silently fills
    in anything the platform forgot to set: a deployment missing its database URL
    would quietly connect to whatever the file mentions rather than refusing to
    start, which is the exact failure this module exists to prevent.

    Production configuration should come from the platform. The image should not
    contain the file, which is why `.dockerignore` excludes it.
    """
    if not in_production():
        return []

    from config.settings.base import ROOT_DIR

    if not (ROOT_DIR / ".env").exists():
        return []

    return [
        Warning(
            "A .env file is present in a production deployment.",
            hint="Environment variables win over it, but it will silently supply "
            "anything the platform forgot to set. Configure production through the "
            "platform and keep the file out of the image.",
            id="sync.W004",
        )
    ]


@register("sync.production")
def check_transport_security(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    """Warns where a deployment has relaxed something it probably should not.

    Warnings rather than errors, because each of these has a legitimate reason to
    be off behind particular infrastructure. A deployment that terminates TLS at a
    load balancer and sets no forwarded-proto header would loop forever with
    SECURE_SSL_REDIRECT on, and that is the operator's call rather than ours.
    """
    if not in_production():
        return []

    problems: list[CheckMessage] = []

    if not settings.SECURE_SSL_REDIRECT:
        problems.append(
            Warning(
                "SECURE_SSL_REDIRECT is off.",
                hint="Turn it off deliberately only when something in front of this "
                "process already refuses plain HTTP.",
                id="sync.W001",
            )
        )

    if not settings.SESSION_COOKIE_SECURE or not settings.CSRF_COOKIE_SECURE:
        problems.append(
            Warning(
                "Session or CSRF cookies are not marked secure.",
                hint="The admin is a session-authenticated surface over the same domain.",
                id="sync.W002",
            )
        )

    if not settings.SECURE_HSTS_SECONDS:
        problems.append(
            Warning(
                "HSTS is not enabled.",
                hint="Set it once the domain is only ever served over HTTPS. It is hard "
                "to undo, so it is a warning rather than an error.",
                id="sync.W003",
            )
        )

    return problems
