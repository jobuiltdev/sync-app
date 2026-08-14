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

# Every external integration is a fake in tests. This is the line that makes the
# suite runnable with no Paystack, Termii or Resend account, and it is also what
# stops a misconfigured machine reaching a real provider from a test run.
PAYMENT_GATEWAY = "apps.payments.gateways.fake.FakeGateway"
BANK_RESOLVER = "apps.payments.banks.fake.FakeBankResolver"
SMS_BACKEND = "apps.accounts.sms.locmem.LocMemSMSProvider"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# The real keys must be absent, not merely unused, so a test that would only pass
# by talking to a live provider fails instead.
PAYSTACK = {**PAYSTACK, "SECRET_KEY": "", "PUBLIC_KEY": ""}  # noqa: F405
TERMII = {**TERMII, "API_KEY": ""}  # noqa: F405
RESEND = {**RESEND, "API_KEY": ""}  # noqa: F405
