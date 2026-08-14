"""The webhook endpoint.

Signatures are generated locally, so the whole path including rejection is tested
without a Paystack account. The endpoint is unauthenticated by design: the
signature is the authentication, and these check that it genuinely is.
"""

import json

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.bookings.services import create_booking
from apps.bookings.tests.factories import VALID_CLEANING_DETAILS, accept_first_offer
from apps.payments import payment_services
from apps.payments.gateways.fake import FakeGateway
from apps.payments.intents import PaymentIntent, PaymentStatus
from apps.payments.settlements import BookingSettlement
from apps.payments.tests.factories import (
    DEFAULT_PRICE_KOBO,
    complete_booking,
    earning_setup,
)
from apps.payments.webhooks import WebhookEvent

WEBHOOK = "/api/v1/webhooks/paystack/"


def charge_body(reference: str, *, amount_kobo: int, event_id: int = 900, **overrides) -> bytes:
    payload = {
        "event": "charge.success",
        "data": {
            "id": event_id,
            "reference": reference,
            "status": "success",
            "amount": amount_kobo,
            "currency": "NGN",
            "channel": "card",
            **overrides,
        },
    }
    return json.dumps(payload).encode()


class WebhookTestCase(APITestCase):
    def setUp(self):
        FakeGateway.clear()
        self.setup = earning_setup()
        self.customer = self.setup["customer"]

        booking = create_booking(
            customer=self.customer,
            service=self.setup["service"],
            address=self.setup["address"],
            details=VALID_CLEANING_DETAILS,
        )
        accept_first_offer(booking, self.setup["provider"])
        booking.refresh_from_db()
        self.booking = booking

        self.intent = payment_services.initialize_payment(
            booking=self.booking, customer=self.customer
        )

    def post(self, body: bytes, signature: str | None = None):
        return self.client.post(
            WEBHOOK,
            data=body,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=(FakeGateway.sign(body) if signature is None else signature),
        )


class WebhookSignatureTests(WebhookTestCase):
    def test_a_correctly_signed_event_is_accepted(self):
        body = charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO)

        self.assertEqual(self.post(body).status_code, status.HTTP_200_OK)

    def test_an_unsigned_request_is_refused(self):
        body = charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO)

        response = self.post(body, signature="")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json()["error"]["code"], "INVALID_WEBHOOK_SIGNATURE")

    def test_a_forged_signature_is_refused(self):
        body = charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO)

        response = self.post(body, signature="0" * 128)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_body_altered_after_signing_is_refused(self):
        # The attack this check exists for: a real event, intercepted, with the
        # amount raised before it is forwarded.
        body = charge_body(self.intent.reference, amount_kobo=100)
        signature = FakeGateway.sign(body)
        tampered = body.replace(b'"amount": 100', b'"amount": 2000000')

        response = self.post(tampered, signature=signature)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_refused_request_changes_nothing_and_is_not_recorded(self):
        body = charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO)

        self.post(body, signature="wrong")

        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentStatus.INITIALIZED)
        self.assertEqual(WebhookEvent.objects.count(), 0)

    def test_the_refusal_says_nothing_useful_to_whoever_sent_it(self):
        response = self.post(b"{}", signature="wrong")

        self.assertEqual(response.json()["error"]["message"], "Rejected.")
        self.assertEqual(response.json()["error"]["details"], {})

    def test_an_oversized_body_is_refused_before_it_is_parsed(self):
        response = self.post(b"x" * (300 * 1024), signature="anything")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_signed_nonsense_is_acknowledged_rather_than_retried_forever(self):
        response = self.post(b"not json at all")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], "ignored")


class WebhookApplicationTests(WebhookTestCase):
    def test_a_success_event_marks_the_payment_paid(self):
        self.post(charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO))

        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentStatus.SUCCESSFUL)
        self.assertIsNotNone(self.intent.paid_at)

    def test_the_event_is_recorded(self):
        self.post(charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO))

        event = WebhookEvent.objects.get()
        self.assertEqual(event.event_type, "charge.success")
        self.assertEqual(event.reference, self.intent.reference)
        self.assertIsNotNone(event.processed_at)

    def test_the_payload_itself_is_not_stored(self):
        # A charge payload carries the customer's email and their card's last four
        # digits. What is kept is a digest, so a disputed event can still be
        # matched without our holding a copy of everybody's card details.
        body = charge_body(
            self.intent.reference,
            amount_kobo=DEFAULT_PRICE_KOBO,
            customer={"email": "ada@example.com"},
            authorization={"last4": "4081"},
        )
        self.post(body)

        stored = " ".join(str(value) for value in WebhookEvent.objects.get().__dict__.values())

        self.assertNotIn("ada@example.com", stored)
        self.assertNotIn("4081", stored)
        self.assertEqual(len(WebhookEvent.objects.get().payload_digest), 64)

    def test_an_event_for_the_wrong_amount_is_recorded_and_not_applied(self):
        # A hostile or misrouted event claiming success for one naira must not
        # mark a twenty thousand naira booking paid.
        self.post(charge_body(self.intent.reference, amount_kobo=100))

        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentStatus.INITIALIZED)
        self.assertIn("mismatch", WebhookEvent.objects.get().outcome)

    def test_an_event_in_the_wrong_currency_is_not_applied(self):
        self.post(
            charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO, currency="USD")
        )

        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentStatus.INITIALIZED)

    def test_an_event_about_a_reference_we_never_issued_is_ignored(self):
        response = self.post(charge_body("SYP-NOTOURS", amount_kobo=DEFAULT_PRICE_KOBO))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(WebhookEvent.objects.get().outcome, "unknown reference")

    def test_a_failure_event_fails_the_payment(self):
        body = json.dumps(
            {
                "event": "charge.failed",
                "data": {
                    "id": 901,
                    "reference": self.intent.reference,
                    "status": "failed",
                    "amount": DEFAULT_PRICE_KOBO,
                    "currency": "NGN",
                },
            }
        ).encode()

        self.post(body)

        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentStatus.FAILED)


class WebhookIdempotencyTests(WebhookTestCase):
    def test_the_same_event_delivered_twice_is_applied_once(self):
        body = charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO)

        first = self.post(body)
        second = self.post(body)

        self.assertEqual(first.json()["status"], "SUCCESSFUL")
        self.assertEqual(second.json()["status"], "duplicate")
        self.assertEqual(WebhookEvent.objects.count(), 1)

    def test_replaying_an_event_ten_times_changes_nothing(self):
        body = charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO)

        for _ in range(10):
            self.assertEqual(self.post(body).status_code, status.HTTP_200_OK)

        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.assertEqual(PaymentIntent.objects.filter(status=PaymentStatus.SUCCESSFUL).count(), 1)

    def test_a_later_failure_event_cannot_unpay_a_paid_payment(self):
        # Out of order delivery. Terminal is terminal: only a fresh attempt can
        # change what a payment says.
        self.post(charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO))

        late_failure = json.dumps(
            {
                "event": "charge.failed",
                "data": {
                    "id": 902,
                    "reference": self.intent.reference,
                    "status": "failed",
                    "amount": DEFAULT_PRICE_KOBO,
                    "currency": "NGN",
                },
            }
        ).encode()
        self.post(late_failure)

        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentStatus.SUCCESSFUL)

    def test_a_second_success_event_does_not_create_a_second_payment(self):
        self.post(charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO, event_id=1))
        self.post(charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO, event_id=2))

        self.assertEqual(PaymentIntent.objects.count(), 1)
        self.assertEqual(BookingSettlement.objects.count(), 0)

    def test_a_webhook_and_a_verification_do_not_both_settle(self):
        complete_booking(self.booking)

        self.post(charge_body(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO))
        FakeGateway.arrange(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO, currency="NGN")
        payment_services.verify_payment(self.intent.pk, self.customer)

        self.assertEqual(BookingSettlement.objects.count(), 1)


class WebhookDeduplicationTests(TestCase):
    """The dedup key itself, without the HTTP layer."""

    def test_two_events_with_the_same_id_cannot_both_be_recorded(self):
        from django.db import IntegrityError, transaction

        WebhookEvent.objects.create(
            gateway="FAKE",
            event_id="charge.success:1",
            event_type="charge.success",
            payload_digest="a" * 64,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            WebhookEvent.objects.create(
                gateway="FAKE",
                event_id="charge.success:1",
                event_type="charge.success",
                payload_digest="b" * 64,
            )

    def test_the_same_event_id_from_two_providers_is_two_events(self):
        WebhookEvent.objects.create(
            gateway="FAKE",
            event_id="charge.success:1",
            event_type="charge.success",
            payload_digest="a" * 64,
        )
        WebhookEvent.objects.create(
            gateway="PAYSTACK",
            event_id="charge.success:1",
            event_type="charge.success",
            payload_digest="a" * 64,
        )

        self.assertEqual(WebhookEvent.objects.count(), 2)
