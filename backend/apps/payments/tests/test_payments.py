"""Taking payment: initialization, verification, and what may not move a payment.

The security cases carry the weight. A marketplace that can be told a payment
succeeded, by a client or by an unsigned request, has no payments at all.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.bookings.services import create_booking, transition
from apps.bookings.state import ActorType, BookingStatus
from apps.bookings.tests.factories import VALID_CLEANING_DETAILS, accept_first_offer
from apps.payments import payment_services
from apps.payments.errors import BookingNotPayable, PaymentAmountMismatch, PaymentNotFound
from apps.payments.gateways.base import PaymentState
from apps.payments.gateways.fake import FakeGateway
from apps.payments.intents import PaymentIntent, PaymentStatus
from apps.payments.settlements import BookingSettlement
from apps.payments.tests.factories import (
    DEFAULT_PRICE_KOBO,
    complete_booking,
    earning_setup,
    pay_booking,
)


class PaymentTestCase(TestCase):
    """Shared setup: one taken booking, and a clean gateway."""

    def setUp(self):
        FakeGateway.clear()
        self.setup = earning_setup()
        self.customer = self.setup["customer"]
        self.provider = self.setup["provider"]
        self.booking = self.book()

    def book(self):
        booking = create_booking(
            customer=self.customer,
            service=self.setup["service"],
            address=self.setup["address"],
            details=VALID_CLEANING_DETAILS,
        )
        accept_first_offer(booking, self.provider)
        booking.refresh_from_db()
        return booking

    def start(self, booking=None, **kwargs) -> PaymentIntent:
        return payment_services.initialize_payment(
            booking=booking or self.booking, customer=self.customer, **kwargs
        )

    def report(self, intent: PaymentIntent, **overrides):
        FakeGateway.arrange(
            intent.reference,
            **{
                "state": PaymentState.SUCCESSFUL,
                "amount_kobo": intent.amount_kobo,
                "currency": intent.currency,
                **overrides,
            },
        )


class InitializationTests(PaymentTestCase):
    def test_it_charges_the_booking_snapshotted_total(self):
        intent = self.start()

        self.assertEqual(intent.amount_kobo, self.booking.total_kobo)
        self.assertEqual(intent.amount_kobo, DEFAULT_PRICE_KOBO)

    def test_a_later_catalog_price_change_does_not_change_what_is_charged(self):
        service = self.setup["service"]
        service.base_price_kobo = 99_999_999
        service.save(update_fields=["base_price_kobo"])

        self.assertEqual(self.start().amount_kobo, DEFAULT_PRICE_KOBO)

    def test_it_starts_unpaid(self):
        intent = self.start()

        self.assertEqual(intent.status, PaymentStatus.INITIALIZED)
        self.assertIsNone(intent.paid_at)
        self.assertTrue(intent.is_payable)

    def test_it_returns_somewhere_to_send_the_customer(self):
        self.assertTrue(self.start().authorization_url)

    def test_it_records_which_provider_took_it(self):
        self.assertEqual(self.start().gateway, "FAKE")

    def test_the_provider_is_told_the_amount_in_kobo(self):
        self.start()

        self.assertEqual(FakeGateway.initialized[0]["amount_kobo"], DEFAULT_PRICE_KOBO)

    def test_a_cancelled_booking_cannot_be_paid_for(self):
        transition(
            self.booking,
            BookingStatus.CANCELLED,
            actor_type=ActorType.CUSTOMER,
            actor_id=self.customer.id,
        )

        with self.assertRaises(BookingNotPayable):
            self.start()

        self.assertEqual(PaymentIntent.objects.count(), 0)

    def test_a_completed_booking_can_still_be_paid_for(self):
        # Paying after the work is done is an ordinary sequence, not an error.
        complete_booking(self.booking)

        self.assertEqual(self.start().status, PaymentStatus.INITIALIZED)

    def test_paying_for_somebody_else_booking_is_a_not_found(self):
        stranger = earning_setup(slug="stranger-clean")["customer"]

        with self.assertRaises(PaymentNotFound):
            payment_services.initialize_payment(booking=self.booking, customer=stranger)

    def test_nothing_is_written_when_a_booking_is_not_payable(self):
        transition(
            self.booking,
            BookingStatus.CANCELLED,
            actor_type=ActorType.CUSTOMER,
            actor_id=self.customer.id,
        )

        with self.assertRaises(BookingNotPayable):
            self.start()

        self.assertEqual(PaymentIntent.objects.count(), 0)
        self.assertEqual(FakeGateway.initialized, [])


class InitializationIdempotencyTests(PaymentTestCase):
    def test_the_same_key_twice_starts_one_payment(self):
        first = self.start(idempotency_key="tap-once")
        second = self.start(idempotency_key="tap-once")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PaymentIntent.objects.count(), 1)

    def test_a_retry_does_not_ask_the_provider_twice(self):
        self.start(idempotency_key="tap-once")
        self.start(idempotency_key="tap-once")

        self.assertEqual(len(FakeGateway.initialized), 1)

    def test_tapping_again_without_a_key_returns_the_attempt_in_flight(self):
        # A customer who backgrounds the app mid-payment and comes back should
        # return to the payment they left, not start a second one.
        first = self.start()
        second = self.start()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PaymentIntent.objects.count(), 1)

    def test_a_paid_booking_answers_with_the_payment_that_settled_it(self):
        intent = self.start()
        self.report(intent)
        payment_services.verify_payment(intent.pk, self.customer)

        again = self.start()

        self.assertEqual(again.pk, intent.pk)
        self.assertEqual(again.status, PaymentStatus.SUCCESSFUL)

    def test_a_new_attempt_is_allowed_after_one_failed(self):
        intent = self.start()
        self.report(intent, state=PaymentState.FAILED)
        payment_services.verify_payment(intent.pk, self.customer)

        retry = self.start()

        self.assertNotEqual(retry.pk, intent.pk)
        self.assertEqual(retry.status, PaymentStatus.INITIALIZED)

    def test_the_database_refuses_a_duplicate_key_whatever_the_service_believed(self):
        self.start(idempotency_key="tap-once")

        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentIntent.objects.create(
                booking=self.booking,
                customer=self.customer,
                amount_kobo=1,
                gateway="FAKE",
                idempotency_key="tap-once",
            )


class VerificationTests(PaymentTestCase):
    def test_a_provider_confirmed_payment_becomes_successful(self):
        intent = self.start()
        self.report(intent)

        outcome = payment_services.verify_payment(intent.pk, self.customer)

        self.assertTrue(outcome.changed)
        self.assertEqual(outcome.intent.status, PaymentStatus.SUCCESSFUL)
        self.assertIsNotNone(outcome.intent.paid_at)

    def test_it_records_how_the_customer_paid(self):
        intent = self.start()
        self.report(intent, method="bank_transfer")

        outcome = payment_services.verify_payment(intent.pk, self.customer)

        self.assertEqual(outcome.intent.method, "bank_transfer")

    def test_a_provider_reported_failure_fails_the_payment(self):
        intent = self.start()
        self.report(intent, state=PaymentState.FAILED)

        outcome = payment_services.verify_payment(intent.pk, self.customer)

        self.assertEqual(outcome.intent.status, PaymentStatus.FAILED)
        self.assertIsNotNone(outcome.intent.failed_at)

    def test_a_payment_the_provider_still_calls_pending_does_not_move(self):
        intent = self.start()
        self.report(intent, state=PaymentState.PENDING)

        outcome = payment_services.verify_payment(intent.pk, self.customer)

        self.assertFalse(outcome.changed)
        self.assertEqual(outcome.intent.status, PaymentStatus.INITIALIZED)

    def test_a_reference_the_provider_has_never_heard_of_fails_the_payment(self):
        # A provider that has no record of a transaction we started is telling us
        # the money never moved. Treated as a failure rather than left open, so
        # the booking does not sit forever waiting on a payment that will not
        # arrive.
        intent = self.start()
        FakeGateway.payments.pop(intent.reference)

        outcome = payment_services.verify_payment(intent.pk, self.customer)

        self.assertEqual(outcome.intent.status, PaymentStatus.FAILED)
        self.assertEqual(outcome.intent.gateway_status, "unknown")

    def test_a_freshly_started_payment_is_still_pending_at_the_provider(self):
        intent = self.start()

        outcome = payment_services.verify_payment(intent.pk, self.customer)

        self.assertFalse(outcome.changed)
        self.assertEqual(outcome.intent.status, PaymentStatus.INITIALIZED)

    def test_verifying_twice_changes_nothing_the_second_time(self):
        intent = self.start()
        self.report(intent)

        first = payment_services.verify_payment(intent.pk, self.customer)
        second = payment_services.verify_payment(intent.pk, self.customer)

        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(second.intent.status, PaymentStatus.SUCCESSFUL)

    def test_an_amount_that_does_not_match_is_refused(self):
        # The check the whole design turns on. A transaction for one naira must
        # never mark a twenty thousand naira booking paid.
        intent = self.start()
        self.report(intent, amount_kobo=100)

        with self.assertRaises(PaymentAmountMismatch):
            payment_services.verify_payment(intent.pk, self.customer)

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentStatus.INITIALIZED)

    def test_a_mismatched_amount_leaves_no_settlement_behind(self):
        complete_booking(self.booking)
        intent = self.start()
        self.report(intent, amount_kobo=100)

        with self.assertRaises(PaymentAmountMismatch):
            payment_services.verify_payment(intent.pk, self.customer)

        self.assertEqual(BookingSettlement.objects.count(), 0)

    def test_a_payment_in_another_currency_is_refused(self):
        intent = self.start()
        self.report(intent, currency="USD")

        with self.assertRaises(PaymentAmountMismatch):
            payment_services.verify_payment(intent.pk, self.customer)

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentStatus.INITIALIZED)

    def test_the_refusal_does_not_disclose_the_other_transaction_amount(self):
        intent = self.start()
        self.report(intent, amount_kobo=777)

        with self.assertRaises(PaymentAmountMismatch) as caught:
            payment_services.verify_payment(intent.pk, self.customer)

        self.assertEqual(caught.exception.details, {"expected_kobo": DEFAULT_PRICE_KOBO})
        self.assertNotIn("777", str(caught.exception.details))

    def test_a_provider_answering_about_a_different_reference_is_refused(self):
        intent = self.start()
        FakeGateway.payments[intent.reference] = FakeGateway.arrange(
            "SOMEBODY-ELSE", amount_kobo=intent.amount_kobo
        )

        with self.assertRaises(PaymentNotFound):
            payment_services.verify_payment(intent.pk, self.customer)

    def test_verifying_somebody_else_payment_is_a_not_found(self):
        intent = self.start()
        stranger = earning_setup(slug="stranger-clean")["customer"]

        with self.assertRaises(PaymentNotFound):
            payment_services.verify_payment(intent.pk, stranger)

    def test_an_unknown_payment_id_is_a_not_found(self):
        with self.assertRaises(PaymentNotFound):
            payment_services.verify_payment("00000000-0000-4000-8000-000000000000", self.customer)

    def test_a_malformed_payment_id_is_a_not_found_rather_than_a_crash(self):
        with self.assertRaises(PaymentNotFound):
            payment_services.verify_payment("not-a-uuid", self.customer)


class PaymentConstraintTests(PaymentTestCase):
    """What the database refuses on a payment row, whatever wrote it."""

    def test_a_zero_amount_row_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentIntent.objects.create(
                booking=self.booking, customer=self.customer, amount_kobo=0, gateway="FAKE"
            )

    def test_two_successful_payments_for_one_booking_are_refused(self):
        # A booking is paid for once. Without this a customer could be charged
        # twice for the same job.
        pay_booking(self.booking)

        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentIntent.objects.create(
                booking=self.booking,
                customer=self.customer,
                amount_kobo=1,
                gateway="FAKE",
                status=PaymentStatus.SUCCESSFUL,
                paid_at=timezone.now(),
            )

    def test_one_provider_transaction_cannot_back_two_payments(self):
        PaymentIntent.objects.create(
            booking=self.booking,
            customer=self.customer,
            amount_kobo=1,
            gateway="FAKE",
            gateway_reference="txn-1",
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentIntent.objects.create(
                booking=self.booking,
                customer=self.customer,
                amount_kobo=1,
                gateway="FAKE",
                gateway_reference="txn-1",
            )

    def test_a_successful_payment_must_say_when_it_was_paid(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentIntent.objects.create(
                booking=self.booking,
                customer=self.customer,
                amount_kobo=1,
                gateway="FAKE",
                status=PaymentStatus.SUCCESSFUL,
            )

    def test_an_unresolved_payment_cannot_claim_to_have_been_paid(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentIntent.objects.create(
                booking=self.booking,
                customer=self.customer,
                amount_kobo=1,
                gateway="FAKE",
                status=PaymentStatus.INITIALIZED,
                paid_at=timezone.now(),
            )

    def test_references_are_unique(self):
        first = self.start()

        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentIntent.objects.create(
                booking=self.booking,
                customer=self.customer,
                amount_kobo=1,
                gateway="FAKE",
                reference=first.reference,
            )
