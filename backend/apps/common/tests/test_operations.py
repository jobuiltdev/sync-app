"""Health, request correlation, and what may never reach a log.

The three things an operator relies on when something is wrong at three in the
morning: knowing whether an instance can serve, being able to follow one request
through the logs, and being able to read those logs without handling secrets.
"""

import json
import logging
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.common.log import JSONFormatter, is_sensitive
from apps.common.middleware import MAX_LENGTH, RequestIDFilter, _clean, get_request_id

HEALTH = "/api/v1/health/"
LIVE = "/api/v1/health/live/"
READY = "/api/v1/health/ready/"


class LivenessTests(APITestCase):
    def test_it_answers_ok(self):
        response = self.client.get(LIVE)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_it_needs_no_authentication(self):
        self.assertEqual(self.client.get(LIVE).status_code, status.HTTP_200_OK)

    def test_it_answers_even_with_the_database_down(self):
        # The whole point. A liveness probe that checks PostgreSQL restarts a
        # perfectly good web process every time the database hiccups.
        with patch("apps.common.views.check_database", return_value="error"):
            self.assertEqual(self.client.get(LIVE).status_code, status.HTTP_200_OK)

    def test_it_touches_no_dependency(self):
        with (
            patch("apps.common.views.check_database") as database,
            patch("apps.common.views.check_cache") as cache,
        ):
            self.client.get(LIVE)

        database.assert_not_called()
        cache.assert_not_called()


class ReadinessTests(APITestCase):
    def test_a_healthy_instance_is_ready(self):
        response = self.client.get(READY)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["checks"], {"database": "ok", "cache": "ok", "configuration": "ok"})

    def test_an_unreachable_database_is_not_ready(self):
        with patch("apps.common.views.check_database", return_value="error"):
            response = self.client.get(READY)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["checks"]["database"], "error")

    def test_an_unreachable_cache_is_not_ready(self):
        with patch("apps.common.views.check_cache", return_value="error"):
            response = self.client.get(READY)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["checks"]["cache"], "error")

    def test_broken_configuration_is_not_ready(self):
        with patch("apps.common.views.check_configuration", return_value="error"):
            response = self.client.get(READY)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_configuration_is_ok_outside_production(self):
        from apps.common.views import check_configuration

        self.assertEqual(check_configuration(), "ok")

    def test_a_production_misconfiguration_makes_it_unready(self):
        # An instance whose configuration drifted after boot reports itself
        # unready rather than serving with a fake payment gateway.
        from apps.common.views import check_configuration

        with override_settings(
            IS_PRODUCTION=True,
            PAYMENT_GATEWAY="apps.payments.gateways.fake.FakeGateway",
        ):
            self.assertEqual(check_configuration(), "error")

    def test_it_reveals_nothing_about_the_infrastructure(self):
        with patch("apps.common.views.check_database", return_value="error"):
            body = self.client.get(READY).content.decode()

        # No driver message, no host, no user, no connection string.
        for leak in ("postgres", "psycopg", "redis://", "127.0.0.1", "password", "Traceback"):
            self.assertNotIn(leak, body.lower() if leak.islower() else body)

    def test_a_configuration_failure_does_not_name_the_setting(self):
        # An unauthenticated caller must not learn which provider this
        # deployment uses.
        with override_settings(
            IS_PRODUCTION=True,
            PAYMENT_GATEWAY="apps.payments.gateways.fake.FakeGateway",
        ):
            body = self.client.get(READY).content.decode()

        self.assertNotIn("PAYMENT_GATEWAY", body)
        self.assertNotIn("FakeGateway", body)

    def test_it_does_not_call_a_payment_provider(self):
        # Paystack being slow must not take this marketplace off the internet.
        from apps.payments.gateways.fake import FakeGateway

        with patch.object(FakeGateway, "fetch") as fetch:
            self.client.get(READY)

        fetch.assert_not_called()


class HealthContractTests(APITestCase):
    """The original endpoint, whose contract M7 does not change."""

    def test_it_still_answers_the_same_shape(self):
        response = self.client.get(HEALTH)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(), {"status": "ok", "checks": {"database": "ok", "cache": "ok"}}
        )

    def test_it_still_reports_degraded_with_a_dependency_down(self):
        with patch("apps.common.views.check_database", return_value="error"):
            response = self.client.get(HEALTH)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["status"], "degraded")


class RequestIDTests(APITestCase):
    def test_every_response_carries_one(self):
        response = self.client.get(LIVE)

        self.assertTrue(response["X-Request-ID"])

    def test_a_safe_incoming_id_is_reused(self):
        response = self.client.get(LIVE, HTTP_X_REQUEST_ID="abc123-def456")

        self.assertEqual(response["X-Request-ID"], "abc123-def456")

    def test_two_requests_get_different_ids(self):
        first = self.client.get(LIVE)["X-Request-ID"]
        second = self.client.get(LIVE)["X-Request-ID"]

        self.assertNotEqual(first, second)

    def test_an_oversized_id_is_replaced(self):
        response = self.client.get(LIVE, HTTP_X_REQUEST_ID="a" * 500)

        self.assertNotEqual(response["X-Request-ID"], "a" * 500)
        self.assertLessEqual(len(response["X-Request-ID"]), MAX_LENGTH)

    def test_an_id_that_could_forge_a_log_line_is_replaced(self):
        # A newline in a value that reaches log output is a way to write a
        # convincing fake log line.
        for hostile in ("a\nb", "a\rb", "a b", "<script>", "'; DROP TABLE", "café"):
            with self.subTest(value=hostile):
                self.assertEqual(_clean(hostile), "")

    def test_the_formats_other_systems_actually_send_are_accepted(self):
        for value in (
            "0123456789abcdef" * 2,
            "abc123-trace",
            "req_9f8e7d",
            "0HMQ9-A1B2C3",
        ):
            with self.subTest(value=value):
                self.assertEqual(_clean(value), value)

    def test_the_id_is_not_leaked_between_requests(self):
        self.client.get(LIVE, HTTP_X_REQUEST_ID="abc123")

        # The context variable is reset once the response is returned, so a task
        # or a later request does not inherit it.
        self.assertEqual(get_request_id(), "")


class RequestIDLoggingTests(SimpleTestCase):
    def test_a_record_made_outside_a_request_says_so(self):
        record = logging.LogRecord("x", logging.INFO, "", 0, "hello", None, None)

        RequestIDFilter().filter(record)

        self.assertEqual(record.request_id, "-")

    def test_a_record_made_during_a_request_carries_the_id(self):
        from apps.common.middleware import reset_request_id, set_request_id

        token = set_request_id("abc123")
        record = logging.LogRecord("x", logging.INFO, "", 0, "hello", None, None)
        RequestIDFilter().filter(record)
        reset_request_id(token)

        self.assertEqual(record.request_id, "abc123")


class JSONLoggingTests(SimpleTestCase):
    def format(self, **extra) -> dict:
        record = logging.LogRecord(
            "apps.payments", logging.INFO, "x.py", 1, "payout submitted", None, None
        )
        for key, value in extra.items():
            setattr(record, key, value)
        record.request_id = extra.get("request_id", "-")

        return json.loads(JSONFormatter().format(record))

    def test_it_emits_one_json_object(self):
        payload = self.format()

        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["logger"], "apps.payments")
        self.assertEqual(payload["message"], "payout submitted")

    def test_safe_context_is_promoted_to_top_level(self):
        payload = self.format(payout_id="abc", amount_kobo=600_000, outcome="PAID")

        self.assertEqual(payload["payout_id"], "abc")
        self.assertEqual(payload["amount_kobo"], 600_000)
        self.assertEqual(payload["outcome"], "PAID")

    def test_anything_that_looks_like_a_secret_is_dropped(self):
        payload = self.format(
            api_key="sk_live_x",
            password="hunter2",
            access_token="eyJhbG",
            refresh_token="eyJhbG",
            otp="123456",
            verification_code="123456",
            account_number="0123456789",
            card_last4="4081",
            cvv="123",
            payload={"raw": "provider body"},
            code_hash="argon2$x",
        )

        for key in (
            "api_key",
            "password",
            "access_token",
            "refresh_token",
            "otp",
            "verification_code",
            "account_number",
            "card_last4",
            "cvv",
            "payload",
            "code_hash",
        ):
            self.assertNotIn(key, payload)

        serialised = json.dumps(payload)
        for value in ("sk_live_x", "hunter2", "eyJhbG", "123456", "0123456789", "4081"):
            self.assertNotIn(value, serialised)

    def test_a_secret_nested_in_a_dict_is_dropped_too(self):
        payload = self.format(context={"booking": "SY-1", "api_key": "sk_live_x"})

        self.assertEqual(payload["context"], {"booking": "SY-1"})

    def test_an_exception_is_summarised_without_a_traceback(self):
        try:
            raise ValueError("something went wrong")
        except ValueError:
            import sys

            record = logging.LogRecord(
                "x", logging.ERROR, "x.py", 1, "failed", None, sys.exc_info()
            )
            payload = json.loads(JSONFormatter().format(record))

        self.assertEqual(payload["error"], "ValueError")
        self.assertIn("something went wrong", payload["error_detail"])
        self.assertNotIn("Traceback", json.dumps(payload))

    def test_the_sensitive_key_test_is_substring_based(self):
        # So paystack_secret_key and X-Api-Key are both caught without listing
        # every spelling anybody might use.
        for key in ("PAYSTACK_SECRET_KEY", "X-Api-Key", "user_password", "bearer_token"):
            self.assertTrue(is_sensitive(key), key)

    def test_ordinary_keys_are_not_treated_as_secrets(self):
        for key in ("booking_id", "amount_kobo", "outcome", "provider_id", "status"):
            self.assertFalse(is_sensitive(key), key)


class ErrorResponseTests(APITestCase):
    """Unexpected failures must be safe, and expected ones must stay themselves."""

    def test_a_driver_failure_is_reported_without_its_message(self):
        # The real check_database has to cope, so the failure is injected
        # underneath it rather than by replacing it.
        with patch(
            "apps.common.views.connection.cursor",
            side_effect=RuntimeError("could not connect to host db.internal user sync"),
        ):
            response = self.client.get(READY)

        body = response.content.decode()
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["checks"]["database"], "error")
        # A driver message readily names a host and a user.
        self.assertNotIn("db.internal", body)
        self.assertNotIn("could not connect", body)

    def test_a_domain_error_keeps_its_code_rather_than_becoming_a_500(self):
        response = self.client.get("/api/v1/provider/earnings/")

        # Unauthenticated, so this is a 401 in the standard envelope, not a 500.
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("error", response.json())

    def test_a_malformed_uuid_is_a_not_found_rather_than_a_crash(self):
        response = self.client.get("/api/v1/customer/payments/not-a-uuid/")

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_404_NOT_FOUND),
        )


class SchemaSecrecyTests(TestCase):
    """The published API description must not carry configuration."""

    def test_the_schema_contains_no_credential_or_internal_host(self):
        from apps.accounts.models import User

        admin = User.objects.create_superuser(email="admin@example.com", password="Lagos-2026-xyz")
        self.client.force_login(admin)

        schema = self.client.get("/api/v1/schema/").content.decode()

        for leak in ("sk_test", "sk_live", "SECRET_KEY", "TERMII_API_KEY", "RESEND_API_KEY"):
            self.assertNotIn(leak, schema)
