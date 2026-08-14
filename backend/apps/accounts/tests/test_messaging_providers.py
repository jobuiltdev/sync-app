"""The SMS and email adapters.

Two things matter here and neither needs a vendor account. The adapters must
translate correctly, and neither must ever put a verification code somewhere it
outlives the request that carried it. The third thing, that a delivery failure
leaves no challenge behind, is a property of the domain and is checked against
the failing provider rather than against Termii.
"""

import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.core import mail
from django.test import SimpleTestCase, TestCase, override_settings

from apps.accounts.models import User
from apps.accounts.sms.base import SMSDeliveryError, get_sms_provider
from apps.accounts.sms.termii import TermiiSMSProvider
from apps.accounts.verification import request_email_verification, request_phone_verification

PASSWORD = "Lagos-Rider-2026"


def make_user(email: str = "ada@example.com", **extra) -> User:
    return User.objects.create_user(email=email, password=PASSWORD, **extra)


TERMII_SETTINGS = {
    "API_KEY": "termii-test-key",
    "SENDER_ID": "Sync",
    "CHANNEL": "dnd",
    "API_ROOT": "https://api.invalid",
    "TIMEOUT_SECONDS": 5,
}

RESEND_SETTINGS = {
    "API_KEY": "re_test_key",
    "API_ROOT": "https://api.invalid",
    "TIMEOUT_SECONDS": 5,
}


def http_response(payload: dict):
    """A stand-in for urlopen's context manager."""

    class Response(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    return Response(json.dumps(payload).encode())


@override_settings(TERMII=TERMII_SETTINGS)
class TermiiAdapterTests(SimpleTestCase):
    def test_it_sends_the_code_to_the_number(self):
        with (
            patch("urllib.request.urlopen", return_value=http_response({"message_id": "m-1"})),
            patch("urllib.request.Request") as request,
        ):
            TermiiSMSProvider().send_verification_code("+2348031234567", "123456")

        body = json.loads(request.call_args.kwargs["data"].decode())
        self.assertEqual(body["to"], "2348031234567")
        self.assertIn("123456", body["sms"])
        self.assertEqual(body["from"], "Sync")

    def test_it_strips_the_leading_plus_termii_does_not_want(self):
        with (
            patch("urllib.request.urlopen", return_value=http_response({"message_id": "m-1"})),
            patch("urllib.request.Request") as request,
        ):
            TermiiSMSProvider().send_verification_code("+2348031234567", "123456")

        self.assertEqual(
            json.loads(request.call_args.kwargs["data"].decode())["to"], "2348031234567"
        )

    def test_a_body_without_a_message_id_is_a_failure(self):
        # Termii answers 200 with a refusal in the body, so the status code alone
        # is not the outcome.
        with (
            patch(
                "urllib.request.urlopen",
                return_value=http_response({"message": "Insufficient balance"}),
            ),
            self.assertRaises(SMSDeliveryError) as caught,
        ):
            TermiiSMSProvider().send_verification_code("+2348031234567", "123456")

        self.assertIn("Insufficient balance", str(caught.exception))

    def test_an_http_error_becomes_a_delivery_error(self):
        error = HTTPError("https://api.invalid", 400, "Bad Request", {}, BytesIO(b"nope"))

        with (
            patch("urllib.request.urlopen", side_effect=error),
            self.assertRaises(SMSDeliveryError),
        ):
            TermiiSMSProvider().send_verification_code("+2348031234567", "123456")

    def test_an_unreachable_provider_becomes_a_delivery_error(self):
        with (
            patch("urllib.request.urlopen", side_effect=URLError("no route")),
            self.assertRaises(SMSDeliveryError),
        ):
            TermiiSMSProvider().send_verification_code("+2348031234567", "123456")

    def test_no_failure_message_ever_contains_the_code(self):
        # The code is a live credential for as long as the challenge stands, and
        # an exception message is exactly the sort of thing that ends up in a log.
        failures = [
            HTTPError("https://api.invalid", 400, "Bad", {}, BytesIO(b"denied")),
            URLError("no route"),
            TimeoutError(),
        ]

        for failure in failures:
            with (
                self.subTest(failure=type(failure).__name__),
                patch("urllib.request.urlopen", side_effect=failure),
            ):
                with self.assertRaises(SMSDeliveryError) as caught:
                    TermiiSMSProvider().send_verification_code("+2348031234567", "654321")

                self.assertNotIn("654321", str(caught.exception))

    def test_no_failure_message_contains_the_api_key(self):
        with (
            patch("urllib.request.urlopen", side_effect=URLError("no route")),
            self.assertRaises(SMSDeliveryError) as caught,
        ):
            TermiiSMSProvider().send_verification_code("+2348031234567", "123456")

        self.assertNotIn(TERMII_SETTINGS["API_KEY"], str(caught.exception))

    def test_it_logs_the_delivery_without_the_code(self):
        # A code with no digits in common with the number, so this asserts the
        # code is absent rather than accidentally matching part of the recipient.
        with (
            patch("urllib.request.urlopen", return_value=http_response({"message_id": "m-1"})),
            self.assertLogs("apps.accounts.sms.termii", level="INFO") as logs,
        ):
            TermiiSMSProvider().send_verification_code("+2348031234567", "909090")

        self.assertIn("m-1", logs.output[0])
        self.assertNotIn("909090", logs.output[0])

    @override_settings(TERMII={**TERMII_SETTINGS, "API_KEY": ""})
    def test_it_refuses_to_be_built_without_a_key(self):
        with self.assertRaises(SMSDeliveryError):
            TermiiSMSProvider()


class SMSSelectionTests(SimpleTestCase):
    """The setting chooses the provider, which is the whole of the boundary.

    Each case declares the backend it means rather than reading whatever the
    suite happens to have set, matching every other test here. Asserting on an
    ambient global makes a test depend on what ran before it, which is a
    different thing from what it claims to be checking.
    """

    @override_settings(SMS_BACKEND="apps.accounts.sms.locmem.LocMemSMSProvider")
    def test_it_builds_the_provider_the_setting_names(self):
        from apps.accounts.sms.locmem import LocMemSMSProvider

        self.assertIsInstance(get_sms_provider(), LocMemSMSProvider)

    @override_settings(SMS_BACKEND="apps.accounts.sms.console.ConsoleSMSProvider")
    def test_changing_the_setting_changes_the_provider(self):
        from apps.accounts.sms.console import ConsoleSMSProvider

        self.assertIsInstance(get_sms_provider(), ConsoleSMSProvider)

    def test_it_resolves_per_call_rather_than_caching_at_import(self):
        # What makes the line above true, and what stops a settings override in
        # one test being invisible because an earlier one built the provider.
        from apps.accounts.sms.console import ConsoleSMSProvider
        from apps.accounts.sms.locmem import LocMemSMSProvider

        with override_settings(SMS_BACKEND="apps.accounts.sms.locmem.LocMemSMSProvider"):
            self.assertIsInstance(get_sms_provider(), LocMemSMSProvider)

        with override_settings(SMS_BACKEND="apps.accounts.sms.console.ConsoleSMSProvider"):
            self.assertIsInstance(get_sms_provider(), ConsoleSMSProvider)


class TestSettingsUseFakesTests(SimpleTestCase):
    """The suite must not be able to reach a real provider.

    Read from the settings module itself rather than from the live settings, so
    this asserts what the file says rather than what the current test happens to
    have overridden.
    """

    def test_every_integration_is_a_fake_and_every_key_is_blank(self):
        from config.settings import test as test_settings

        self.assertIn("fake", test_settings.PAYMENT_GATEWAY.lower())
        self.assertIn("fake", test_settings.BANK_RESOLVER.lower())
        self.assertIn("locmem", test_settings.SMS_BACKEND.lower())
        self.assertIn("locmem", test_settings.EMAIL_BACKEND.lower())

        self.assertEqual(test_settings.PAYSTACK["SECRET_KEY"], "")
        self.assertEqual(test_settings.TERMII["API_KEY"], "")
        self.assertEqual(test_settings.RESEND["API_KEY"], "")


class DeliveryFailureTests(TestCase):
    """The security property: a code that did not go out leaves nothing behind."""

    def setUp(self):
        self.user = make_user("ada@example.com", phone="+2348031234567")

    @override_settings(SMS_BACKEND="apps.accounts.sms.failing.FailingSMSProvider")
    def test_an_sms_failure_leaves_no_challenge(self):
        from apps.accounts.challenges import VerificationChallenge

        with self.assertRaises(SMSDeliveryError):
            request_phone_verification(self.user)

        self.assertEqual(VerificationChallenge.objects.count(), 0)

    @override_settings(SMS_BACKEND="apps.accounts.sms.failing.FailingSMSProvider")
    def test_an_sms_failure_does_not_burn_the_cooldown(self):
        from apps.accounts.sms.locmem import LocMemSMSProvider

        with self.assertRaises(SMSDeliveryError):
            request_phone_verification(self.user)

        # The next attempt is allowed immediately, because as far as the account
        # is concerned nothing was ever sent.
        LocMemSMSProvider.clear()
        with override_settings(SMS_BACKEND="apps.accounts.sms.locmem.LocMemSMSProvider"):
            request_phone_verification(self.user)

        self.assertIsNotNone(LocMemSMSProvider.last())

    @override_settings(EMAIL_BACKEND="apps.accounts.tests.test_messaging_providers.FailingEmail")
    def test_an_email_failure_leaves_no_challenge(self):
        from apps.accounts.challenges import VerificationChallenge

        with self.assertRaises(RuntimeError):
            request_email_verification(self.user)

        self.assertEqual(VerificationChallenge.objects.count(), 0)


class FailingEmail:
    """An email backend that always fails, for the case above."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def send_messages(self, email_messages) -> int:
        raise RuntimeError("The provider rejected the message.")

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass


@override_settings(RESEND=RESEND_SETTINGS)
class ResendBackendTests(SimpleTestCase):
    def backend(self, **kwargs):
        from apps.accounts.email.resend import ResendEmailBackend

        return ResendEmailBackend(**kwargs)

    def message(self):
        from django.core.mail import EmailMessage

        return EmailMessage(
            subject="Your Sync verification code",
            body="Your Sync verification code is 123456.",
            from_email="Sync <no-reply@sync.ng>",
            to=["ada@example.com"],
        )

    def test_it_sends_the_message(self):
        with patch("urllib.request.urlopen", return_value=http_response({"id": "msg-1"})):
            sent = self.backend().send_messages([self.message()])

        self.assertEqual(sent, 1)

    def test_it_records_the_provider_message_id_on_the_message(self):
        # Django's backend contract returns a count with no room for a reference,
        # so the id is attached to the message for a caller that wants it.
        message = self.message()

        with patch("urllib.request.urlopen", return_value=http_response({"id": "msg-1"})):
            self.backend().send_messages([message])

        self.assertEqual(message.provider_message_id, "msg-1")

    def test_it_sends_the_recipient_subject_and_body(self):
        with (
            patch("urllib.request.urlopen", return_value=http_response({"id": "msg-1"})),
            patch("urllib.request.Request") as request,
        ):
            self.backend().send_messages([self.message()])

        body = json.loads(request.call_args.kwargs["data"].decode())
        self.assertEqual(body["to"], ["ada@example.com"])
        self.assertEqual(body["subject"], "Your Sync verification code")
        self.assertIn("123456", body["text"])

    def test_sending_nothing_is_not_an_error(self):
        self.assertEqual(self.backend().send_messages([]), 0)

    def test_a_missing_key_fails_loudly_by_default(self):
        with (
            override_settings(RESEND={**RESEND_SETTINGS, "API_KEY": ""}),
            self.assertRaises(ValueError),
        ):
            self.backend().send_messages([self.message()])

    def test_a_missing_key_is_silent_when_the_caller_asked_for_that(self):
        with override_settings(RESEND={**RESEND_SETTINGS, "API_KEY": ""}):
            self.assertEqual(self.backend(fail_silently=True).send_messages([self.message()]), 0)

    def test_a_provider_failure_propagates_so_the_challenge_rolls_back(self):
        with (
            patch("urllib.request.urlopen", side_effect=URLError("no route")),
            self.assertRaises(ValueError),
        ):
            self.backend().send_messages([self.message()])

    def test_no_failure_message_contains_the_api_key_or_the_code(self):
        with (
            patch("urllib.request.urlopen", side_effect=URLError("no route")),
            self.assertRaises(ValueError) as caught,
        ):
            self.backend().send_messages([self.message()])

        self.assertNotIn(RESEND_SETTINGS["API_KEY"], str(caught.exception))
        self.assertNotIn("123456", str(caught.exception))

    def test_a_body_without_an_id_is_a_failure(self):
        with (
            patch("urllib.request.urlopen", return_value=http_response({})),
            self.assertRaises(ValueError),
        ):
            self.backend().send_messages([self.message()])

    def test_it_logs_the_delivery_without_the_subject_or_body(self):
        with (
            patch("urllib.request.urlopen", return_value=http_response({"id": "msg-1"})),
            self.assertLogs("apps.accounts.email.resend", level="INFO") as logs,
        ):
            self.backend().send_messages([self.message()])

        self.assertIn("msg-1", logs.output[0])
        self.assertNotIn("123456", logs.output[0])
        self.assertNotIn("verification code", logs.output[0])


class EmailDeliveryTests(TestCase):
    """The abstraction itself: the domain sends through Django, not a vendor."""

    def setUp(self):
        self.user = make_user("ada@example.com")
        mail.outbox = []

    def test_a_verification_email_goes_out_through_the_configured_backend(self):
        request_email_verification(self.user)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ada@example.com"])

    def test_the_code_is_in_the_message_and_not_in_the_challenge(self):
        from apps.accounts.challenges import VerificationChallenge

        request_email_verification(self.user)

        challenge = VerificationChallenge.objects.get()
        body = mail.outbox[0].body

        self.assertNotIn(challenge.code_hash, body)
        for word in body.split():
            if word.rstrip(".").isdigit() and len(word.rstrip(".")) == 6:
                self.assertNotIn(word.rstrip("."), challenge.code_hash)
