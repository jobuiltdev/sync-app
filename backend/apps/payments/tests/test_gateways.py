"""The provider adapters, on their own.

No database and no domain. What is under test is translation: a vendor's payload
in, our vocabulary out, and a signature check that is genuinely a signature check.
The Paystack adapter is exercised against a stubbed transport rather than the
live API, so the mapping is tested without an account and without a network call.
"""

import json
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.payments.gateways.base import GatewayError, InvalidSignature, PaymentState
from apps.payments.gateways.fake import FakeGateway
from apps.payments.gateways.paystack import PaystackGateway

PAYSTACK_TEST_SETTINGS = {
    "SECRET_KEY": "sk_test_notarealkey",
    "PUBLIC_KEY": "pk_test_notarealkey",
    "CURRENCY": "NGN",
    "TIMEOUT_SECONDS": 5,
}


class FakeGatewayTests(SimpleTestCase):
    def setUp(self):
        FakeGateway.clear()
        self.gateway = FakeGateway()

    def test_initialization_returns_somewhere_to_send_the_payer(self):
        started = self.gateway.initialize(
            reference="SYP-TEST", amount_kobo=2_000_000, email="ada@example.com", currency="NGN"
        )

        self.assertIn("SYP-TEST", started.authorization_url)
        self.assertTrue(started.gateway_reference)

    def test_a_new_payment_is_pending_rather_than_successful(self):
        # A fake that reported success on initialization would let a broken flow
        # pass, since nothing is meant to be paid until the provider confirms.
        self.gateway.initialize(
            reference="SYP-TEST", amount_kobo=2_000_000, email="ada@example.com", currency="NGN"
        )

        self.assertEqual(self.gateway.fetch("SYP-TEST").state, PaymentState.PENDING)

    def test_it_records_what_it_was_asked_to_collect(self):
        self.gateway.initialize(
            reference="SYP-TEST", amount_kobo=2_000_000, email="ada@example.com", currency="NGN"
        )

        self.assertEqual(FakeGateway.initialized[0]["amount_kobo"], 2_000_000)
        self.assertEqual(FakeGateway.initialized[0]["email"], "ada@example.com")

    def test_an_unknown_reference_is_an_answer_rather_than_an_outage(self):
        reported = self.gateway.fetch("SYP-NEVER-EXISTED")

        self.assertEqual(reported.state, PaymentState.FAILED)
        self.assertEqual(reported.raw_status, "unknown")

    def test_a_correctly_signed_body_is_accepted(self):
        body = b'{"event":"charge.success"}'

        self.gateway.verify_signature(body, FakeGateway.sign(body))

    def test_a_body_altered_after_signing_is_refused(self):
        body = b'{"event":"charge.success","data":{"amount":100}}'
        signature = FakeGateway.sign(body)

        with self.assertRaises(InvalidSignature):
            self.gateway.verify_signature(body.replace(b"100", b"999"), signature)

    def test_an_absent_signature_is_refused(self):
        with self.assertRaises(InvalidSignature):
            self.gateway.verify_signature(b"{}", "")

    def test_events_about_one_transaction_deduplicate_to_one_id(self):
        payload = {"event": "charge.success", "data": {"id": 42, "reference": "SYP-TEST"}}

        first = self.gateway.parse_event(payload)
        second = self.gateway.parse_event(payload)

        self.assertEqual(first.event_id, second.event_id)

    def test_different_events_about_one_transaction_stay_distinct(self):
        data = {"id": 42, "reference": "SYP-TEST"}

        success = self.gateway.parse_event({"event": "charge.success", "data": data})
        failure = self.gateway.parse_event({"event": "charge.failed", "data": data})

        self.assertNotEqual(success.event_id, failure.event_id)


@override_settings(PAYSTACK=PAYSTACK_TEST_SETTINGS)
class PaystackAdapterTests(SimpleTestCase):
    """Translation only. Nothing here reaches the network."""

    def setUp(self):
        self.gateway = PaystackGateway()

    def stub(self, data):
        return patch.object(PaystackGateway, "_request", return_value=data)

    def test_it_sends_kobo_unconverted(self):
        # Paystack counts in the currency's minor unit, which for naira is kobo,
        # so the amount crosses the boundary untouched and nothing is rounded.
        with patch.object(PaystackGateway, "_request", return_value={}) as request:
            self.gateway.initialize(
                reference="SYP-TEST",
                amount_kobo=2_000_000,
                email="ada@example.com",
                currency="NGN",
            )

        self.assertEqual(request.call_args[0][2]["amount"], 2_000_000)
        self.assertEqual(request.call_args[0][2]["currency"], "NGN")

    def test_it_returns_the_checkout_url(self):
        with self.stub({"authorization_url": "https://checkout.paystack.com/x", "reference": "r"}):
            started = self.gateway.initialize(
                reference="SYP-TEST", amount_kobo=1, email="a@b.co", currency="NGN"
            )

        self.assertEqual(started.authorization_url, "https://checkout.paystack.com/x")

    def test_a_successful_transaction_maps_to_successful(self):
        with self.stub(
            {
                "reference": "SYP-TEST",
                "status": "success",
                "amount": 2_000_000,
                "currency": "NGN",
                "channel": "card",
                "id": 99,
            }
        ):
            reported = self.gateway.fetch("SYP-TEST")

        self.assertEqual(reported.state, PaymentState.SUCCESSFUL)
        self.assertEqual(reported.amount_kobo, 2_000_000)
        self.assertEqual(reported.method, "card")
        self.assertEqual(reported.gateway_reference, "99")

    def test_every_pending_wording_maps_to_pending(self):
        for raw in ("pending", "ongoing", "processing", "queued"):
            with self.subTest(raw=raw), self.stub({"status": raw, "amount": 1}):
                self.assertEqual(self.gateway.fetch("r").state, PaymentState.PENDING)

    def test_every_unsuccessful_wording_maps_to_failed(self):
        for raw in ("failed", "abandoned", "reversed"):
            with self.subTest(raw=raw), self.stub({"status": raw, "amount": 1}):
                self.assertEqual(self.gateway.fetch("r").state, PaymentState.FAILED)

    def test_a_status_nobody_recognises_is_failed_rather_than_pending(self):
        # Leaving a payment open on a word we do not understand is the failure
        # that ends with a provider paid for work nobody paid for.
        with self.stub({"status": "something-new", "amount": 1}):
            self.assertEqual(self.gateway.fetch("r").state, PaymentState.FAILED)

    def test_the_provider_own_wording_is_kept_for_support(self):
        with self.stub({"status": "abandoned", "amount": 1}):
            self.assertEqual(self.gateway.fetch("r").raw_status, "abandoned")

    def test_a_refusal_from_paystack_becomes_a_gateway_error(self):
        with (
            patch.object(PaystackGateway, "_request", side_effect=GatewayError("Paystack refused")),
            self.assertRaises(GatewayError),
        ):
            self.gateway.fetch("r")

    def test_signature_checking_is_hmac_sha512_over_the_raw_body(self):
        import hashlib
        import hmac

        body = json.dumps({"event": "charge.success"}).encode()
        signature = hmac.new(
            PAYSTACK_TEST_SETTINGS["SECRET_KEY"].encode(), body, hashlib.sha512
        ).hexdigest()

        self.gateway.verify_signature(body, signature)

    def test_a_signature_from_the_wrong_key_is_refused(self):
        import hashlib
        import hmac

        body = b'{"event":"charge.success"}'
        forged = hmac.new(b"not-the-secret", body, hashlib.sha512).hexdigest()

        with self.assertRaises(InvalidSignature):
            self.gateway.verify_signature(body, forged)

    def test_reserialised_json_does_not_verify(self):
        # The signature covers the exact bytes. This is the reason the view checks
        # request.body rather than the parsed payload.
        import hashlib
        import hmac

        body = b'{"event":"charge.success","data":{}}'
        signature = hmac.new(
            PAYSTACK_TEST_SETTINGS["SECRET_KEY"].encode(), body, hashlib.sha512
        ).hexdigest()
        reserialised = json.dumps(json.loads(body)).encode()

        with self.assertRaises(InvalidSignature):
            self.gateway.verify_signature(reserialised, signature)

    def test_a_webhook_becomes_a_provider_neutral_event(self):
        event = self.gateway.parse_event(
            {
                "event": "charge.success",
                "data": {
                    "id": 12345,
                    "reference": "SYP-TEST",
                    "status": "success",
                    "amount": 2_000_000,
                    "currency": "NGN",
                },
            }
        )

        self.assertEqual(event.event_type, "charge.success")
        self.assertEqual(event.event_id, "charge.success:12345")
        self.assertIsNotNone(event.payment)
        self.assertEqual(event.payment.amount_kobo, 2_000_000)


class PaystackCredentialTests(SimpleTestCase):
    @override_settings(PAYSTACK={**PAYSTACK_TEST_SETTINGS, "SECRET_KEY": ""})
    def test_it_refuses_to_be_built_without_a_key(self):
        # Fails when the gateway is constructed rather than at the first payment,
        # so a misconfigured deployment is obvious the moment anything tries to
        # take money instead of at the worst possible time.
        with self.assertRaises(GatewayError) as caught:
            PaystackGateway()

        self.assertIn("PAYSTACK_SECRET_KEY", str(caught.exception))

    @override_settings(PAYSTACK=PAYSTACK_TEST_SETTINGS)
    def test_the_secret_key_never_appears_in_an_error(self):
        gateway = PaystackGateway()

        with (
            patch("urllib.request.urlopen", side_effect=TimeoutError()),
            self.assertRaises(GatewayError) as caught,
        ):
            gateway.fetch("r")

        self.assertNotIn(PAYSTACK_TEST_SETTINGS["SECRET_KEY"], str(caught.exception))
