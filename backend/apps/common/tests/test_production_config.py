"""What production refuses to start with.

These are the checks that turn a silent misconfiguration into a refusal. The
failure they exist to prevent is the quiet one: a deployment that boots happily
with a fake payment gateway, takes bookings, tells customers they have paid, and
moves no money at all.
"""

from django.core.checks import Error, Warning
from django.test import SimpleTestCase, override_settings

from apps.common import checks

PRODUCTION = {
    "IS_PRODUCTION": True,
    "DEBUG": False,
    "ALLOWED_HOSTS": ["api.sync.ng"],
    "CORS_ALLOW_ALL_ORIGINS": False,
    "CELERY_BROKER_URL": "redis://redis:6379/0",
    "SECRET_KEY": "a" * 60,
    "PAYMENT_GATEWAY": "apps.payments.gateways.paystack.PaystackGateway",
    "BANK_RESOLVER": "apps.payments.banks.paystack.PaystackBankResolver",
    "PAYOUT_TRANSFER_PROVIDER": "apps.payments.transfers.paystack.PaystackTransferProvider",
    "SMS_BACKEND": "apps.accounts.sms.termii.TermiiSMSProvider",
    "EMAIL_BACKEND": "apps.accounts.email.resend.ResendEmailBackend",
    "PAYSTACK": {"SECRET_KEY": "sk_live_x", "PUBLIC_KEY": "pk_live_x"},
    "TERMII": {"API_KEY": "termii-key", "SENDER_ID": "Sync"},
    "RESEND": {"API_KEY": "resend-key"},
    "SECURE_SSL_REDIRECT": True,
    "SESSION_COOKIE_SECURE": True,
    "CSRF_COOKIE_SECURE": True,
    "SECURE_HSTS_SECONDS": 31536000,
}


def ids(messages) -> set[str]:
    return {message.id for message in messages}


def run_all() -> list:
    """Every production check, as the readiness probe runs them."""
    return (
        checks.check_providers_are_real(None)
        + checks.check_provider_credentials(None)
        + checks.check_required_configuration(None)
        + checks.check_transport_security(None)
    )


class InertOutsideProductionTests(SimpleTestCase):
    """None of this may make local development or the test suite harder."""

    def test_the_test_settings_produce_no_production_errors(self):
        # The suite runs with fakes everywhere, which is the whole point of them.
        self.assertEqual(run_all(), [])

    @override_settings(
        IS_PRODUCTION=False,
        PAYMENT_GATEWAY="apps.payments.gateways.fake.FakeGateway",
        SMS_BACKEND="apps.accounts.sms.console.ConsoleSMSProvider",
    )
    def test_fakes_are_fine_when_this_is_not_production(self):
        self.assertEqual(checks.check_providers_are_real(None), [])


@override_settings(**PRODUCTION)
class ProviderSafetyTests(SimpleTestCase):
    def test_a_complete_production_configuration_passes(self):
        self.assertEqual(run_all(), [])

    def test_a_fake_payment_gateway_is_refused(self):
        with override_settings(PAYMENT_GATEWAY="apps.payments.gateways.fake.FakeGateway"):
            problems = checks.check_providers_are_real(None)

        self.assertIn("sync.E002", ids(problems))
        self.assertTrue(all(isinstance(problem, Error) for problem in problems))

    def test_a_fake_transfer_provider_is_refused(self):
        # The worst of them: payouts marked sent while no money leaves.
        with override_settings(
            PAYOUT_TRANSFER_PROVIDER="apps.payments.transfers.fake.FakeTransferProvider"
        ):
            self.assertIn("sync.E002", ids(checks.check_providers_are_real(None)))

    def test_a_fake_bank_resolver_is_refused(self):
        with override_settings(BANK_RESOLVER="apps.payments.banks.fake.FakeBankResolver"):
            self.assertIn("sync.E002", ids(checks.check_providers_are_real(None)))

    def test_a_console_sms_provider_is_refused(self):
        with override_settings(SMS_BACKEND="apps.accounts.sms.console.ConsoleSMSProvider"):
            self.assertIn("sync.E002", ids(checks.check_providers_are_real(None)))

    def test_a_locmem_sms_provider_is_refused(self):
        with override_settings(SMS_BACKEND="apps.accounts.sms.locmem.LocMemSMSProvider"):
            self.assertIn("sync.E002", ids(checks.check_providers_are_real(None)))

    def test_a_console_email_backend_is_refused(self):
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"):
            self.assertIn("sync.E002", ids(checks.check_providers_are_real(None)))

    def test_every_fake_is_reported_rather_than_only_the_first(self):
        # An operator fixing one at a time and redeploying five times is a bad
        # afternoon.
        with override_settings(
            PAYMENT_GATEWAY="apps.payments.gateways.fake.FakeGateway",
            BANK_RESOLVER="apps.payments.banks.fake.FakeBankResolver",
            PAYOUT_TRANSFER_PROVIDER="apps.payments.transfers.fake.FakeTransferProvider",
        ):
            self.assertEqual(len(checks.check_providers_are_real(None)), 3)

    def test_an_unset_provider_is_refused(self):
        with override_settings(PAYMENT_GATEWAY=""):
            self.assertIn("sync.E001", ids(checks.check_providers_are_real(None)))

    def test_the_refusal_says_what_would_go_wrong(self):
        with override_settings(
            PAYOUT_TRANSFER_PROVIDER="apps.payments.transfers.fake.FakeTransferProvider"
        ):
            problem = checks.check_providers_are_real(None)[0]

        self.assertIn("no money left", problem.hint)

    def test_a_future_fake_is_caught_by_its_path(self):
        # Matching on the path rather than a list of known classes means a fake
        # added later is caught without anybody updating this.
        with override_settings(PAYMENT_GATEWAY="apps.payments.gateways.dummy.DummyGateway"):
            self.assertIn("sync.E002", ids(checks.check_providers_are_real(None)))


@override_settings(**PRODUCTION)
class CredentialTests(SimpleTestCase):
    def test_paystack_selected_without_a_key_is_refused(self):
        with override_settings(PAYSTACK={"SECRET_KEY": "", "PUBLIC_KEY": ""}):
            self.assertIn("sync.E003", ids(checks.check_provider_credentials(None)))

    def test_termii_selected_without_a_key_is_refused(self):
        with override_settings(TERMII={"API_KEY": "", "SENDER_ID": "Sync"}):
            self.assertIn("sync.E003", ids(checks.check_provider_credentials(None)))

    def test_resend_selected_without_a_key_is_refused(self):
        with override_settings(RESEND={"API_KEY": ""}):
            self.assertIn("sync.E003", ids(checks.check_provider_credentials(None)))

    def test_a_credential_is_only_required_when_its_provider_is_selected(self):
        # A deployment using some other SMS vendor should not be asked for a
        # Termii key it will never use.
        with override_settings(
            SMS_BACKEND="apps.accounts.sms.somebodyelse.Provider",
            TERMII={"API_KEY": "", "SENDER_ID": "Sync"},
        ):
            problems = checks.check_provider_credentials(None)

        self.assertNotIn("sync.E003", ids(problems))

    def test_no_check_message_contains_a_credential(self):
        # These messages are printed to a deploy log.
        with override_settings(PAYSTACK={"SECRET_KEY": "sk_live_supersecret", "PUBLIC_KEY": ""}):
            text = " ".join(
                f"{message.msg} {message.hint}"
                for message in checks.check_provider_credentials(None)
            )

        self.assertNotIn("sk_live_supersecret", text)


@override_settings(**PRODUCTION)
class RequiredConfigurationTests(SimpleTestCase):
    def test_debug_on_in_production_is_refused(self):
        with override_settings(DEBUG=True):
            self.assertIn("sync.E004", ids(checks.check_required_configuration(None)))

    def test_empty_allowed_hosts_is_refused(self):
        with override_settings(ALLOWED_HOSTS=[]):
            self.assertIn("sync.E005", ids(checks.check_required_configuration(None)))

    def test_a_wildcard_host_is_refused(self):
        with override_settings(ALLOWED_HOSTS=["*"]):
            self.assertIn("sync.E005", ids(checks.check_required_configuration(None)))

    def test_open_cors_is_refused(self):
        with override_settings(CORS_ALLOW_ALL_ORIGINS=True):
            self.assertIn("sync.E006", ids(checks.check_required_configuration(None)))

    def test_a_missing_broker_is_refused(self):
        # Without it nothing runs: offers never expire, payments are never
        # reconciled, payouts are never sent.
        with override_settings(CELERY_BROKER_URL=""):
            self.assertIn("sync.E007", ids(checks.check_required_configuration(None)))

    def test_a_development_secret_key_is_refused(self):
        with override_settings(SECRET_KEY="django-insecure-local-development-only"):
            self.assertIn("sync.E008", ids(checks.check_required_configuration(None)))

    def test_a_short_secret_key_is_refused(self):
        with override_settings(SECRET_KEY="short"):
            self.assertIn("sync.E008", ids(checks.check_required_configuration(None)))


@override_settings(**PRODUCTION)
class TransportSecurityTests(SimpleTestCase):
    """Warnings rather than errors: each has a legitimate reason to be off."""

    def test_a_complete_configuration_warns_about_nothing(self):
        self.assertEqual(checks.check_transport_security(None), [])

    def test_no_ssl_redirect_warns(self):
        with override_settings(SECURE_SSL_REDIRECT=False):
            problems = checks.check_transport_security(None)

        self.assertIn("sync.W001", ids(problems))
        self.assertTrue(all(isinstance(problem, Warning) for problem in problems))

    def test_insecure_cookies_warn(self):
        with override_settings(SESSION_COOKIE_SECURE=False):
            self.assertIn("sync.W002", ids(checks.check_transport_security(None)))

    def test_no_hsts_warns_rather_than_failing(self):
        # Close to irreversible once a browser has seen it, so turning it on is
        # deliberate rather than forced.
        with override_settings(SECURE_HSTS_SECONDS=0):
            self.assertIn("sync.W003", ids(checks.check_transport_security(None)))


#: A complete production environment, with values that are structurally valid
#: and functionally worthless. Needed because importing the production settings
#: at all fails without one, which is itself the behaviour under test.
PRODUCTION_ENVIRON = {
    "DJANGO_SECRET_KEY": "x" * 60,
    "DJANGO_ALLOWED_HOSTS": "api.example.invalid",
    "DATABASE_URL": "postgres://u:p@localhost:5432/db",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "PAYMENT_GATEWAY": "apps.payments.gateways.paystack.PaystackGateway",
    "BANK_RESOLVER": "apps.payments.banks.paystack.PaystackBankResolver",
    "PAYOUT_TRANSFER_PROVIDER": "apps.payments.transfers.paystack.PaystackTransferProvider",
    "SMS_BACKEND": "apps.accounts.sms.termii.TermiiSMSProvider",
    "EMAIL_BACKEND": "apps.accounts.email.resend.ResendEmailBackend",
}


def import_production_settings(environ: dict | None = None, *, clear: bool = False):
    """Imports config.settings.prod under a given environment.

    Dropped from sys.modules first, so the module body genuinely re-executes and
    reads the environment as a fresh process would. A cached copy left over from
    another test would prove nothing about what a deployment does at startup.
    """
    import importlib
    import os
    import sys
    from unittest import mock

    sys.modules.pop("config.settings.prod", None)

    with mock.patch.dict(os.environ, environ or PRODUCTION_ENVIRON, clear=clear):
        return importlib.import_module("config.settings.prod")


class ProductionSettingsModuleTests(SimpleTestCase):
    """The module itself, rather than the checks that run against it."""

    def test_it_refuses_to_import_without_its_environment(self):
        # The property everything else here depends on: a deployment missing a
        # required variable stops at import rather than booting half configured.
        from django.core.exceptions import ImproperlyConfigured

        for missing in (
            "DJANGO_SECRET_KEY",
            "DJANGO_ALLOWED_HOSTS",
            "CELERY_BROKER_URL",
            "PAYMENT_GATEWAY",
            "PAYOUT_TRANSFER_PROVIDER",
        ):
            incomplete = dict(PRODUCTION_ENVIRON)
            del incomplete[missing]

            with self.subTest(missing=missing), self.assertRaises(ImproperlyConfigured):
                # cleared, so the developer .env at the repository root cannot
                # quietly supply what the platform forgot.
                import_production_settings(incomplete, clear=True)

        # Left importable for whatever runs next.
        import_production_settings()

    def test_it_reads_the_things_that_must_never_default(self):
        import inspect

        prod = import_production_settings()
        source = inspect.getsource(prod)

        # env("NAME") with no default is what makes a missing variable stop the
        # process at import. A default on any of these would let a deployment
        # boot with a development value.
        for variable in (
            'env("DJANGO_SECRET_KEY")',
            'env.list("DJANGO_ALLOWED_HOSTS")',
            'env("CELERY_BROKER_URL")',
            'env("PAYOUT_TRANSFER_PROVIDER")',
            'env("PAYMENT_GATEWAY")',
            'env("BANK_RESOLVER")',
            'env("SMS_BACKEND")',
            'env("EMAIL_BACKEND")',
        ):
            self.assertIn(variable, source, f"{variable} must be read without a default")

    def test_it_marks_itself_as_production(self):
        self.assertIs(import_production_settings().IS_PRODUCTION, True)

    def test_it_turns_debug_off(self):
        self.assertIs(import_production_settings().DEBUG, False)

    def test_it_serves_no_browsable_api(self):
        # The browsable renderer turns arbitrary API responses into HTML on an
        # authenticated surface.
        renderers = import_production_settings().REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"]

        self.assertNotIn("rest_framework.renderers.BrowsableAPIRenderer", renderers)

    def test_it_requires_transport_security_by_default(self):
        prod = import_production_settings()

        self.assertTrue(prod.SECURE_SSL_REDIRECT)
        self.assertTrue(prod.SESSION_COOKIE_SECURE)
        self.assertTrue(prod.CSRF_COOKIE_SECURE)
        self.assertTrue(prod.SECURE_CONTENT_TYPE_NOSNIFF)
        self.assertEqual(prod.SECURE_REFERRER_POLICY, "same-origin")
        self.assertEqual(prod.X_FRAME_OPTIONS, "DENY")

    def test_it_never_allows_every_cors_origin(self):
        self.assertIs(import_production_settings().CORS_ALLOW_ALL_ORIGINS, False)

    def test_it_keeps_database_connections_and_health_checks_them(self):
        prod = import_production_settings()

        self.assertGreater(prod.DATABASES["default"]["CONN_MAX_AGE"], 0)
        self.assertTrue(prod.DATABASES["default"]["CONN_HEALTH_CHECKS"])

    def test_it_requires_database_tls_by_default(self):
        prod = import_production_settings()

        self.assertEqual(prod.DATABASES["default"]["OPTIONS"]["sslmode"], "require")

    def test_it_logs_as_json(self):
        self.assertEqual(import_production_settings().LOG_FORMAT, "json")

    def test_the_base_settings_are_not_production(self):
        from config.settings import base

        self.assertIs(base.IS_PRODUCTION, False)
