"""Payment races, against a real database with real threads.

Two taps on a slow connection, a webhook arriving while the app is verifying, and
a customer confirming completion at the same instant their payment lands. Each of
these is ordinary on a Nigerian mobile network, and each has a wrong outcome that
costs somebody money.
"""

import json
import threading

from django.db import connections
from django.test import Client, TransactionTestCase

from apps.bookings.services import create_booking, transition
from apps.bookings.state import ActorType, BookingStatus
from apps.bookings.tests.factories import VALID_CLEANING_DETAILS, accept_first_offer
from apps.payments import payment_services, services
from apps.payments.banks.fake import FakeBankResolver
from apps.payments.destinations import PayoutDestination
from apps.payments.gateways.fake import FakeGateway
from apps.payments.intents import PaymentIntent, PaymentStatus
from apps.payments.settlements import BookingSettlement
from apps.payments.tests.concurrency import run_together
from apps.payments.tests.factories import earning_setup, make_destination

WEBHOOK = "/api/v1/webhooks/paystack/"


class PaymentRaceTestCase(TransactionTestCase):
    reset_sequences = True

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

    def initialize(self, key: str = "") -> None:
        payment_services.initialize_payment(
            booking=self.booking, customer=self.customer, idempotency_key=key
        )

    def arranged_intent(self) -> PaymentIntent:
        self.initialize()
        intent = PaymentIntent.objects.get(booking=self.booking)
        FakeGateway.arrange(
            intent.reference, amount_kobo=intent.amount_kobo, currency=intent.currency
        )
        return intent

    def success_body(self, intent: PaymentIntent) -> bytes:
        return json.dumps(
            {
                "event": "charge.success",
                "data": {
                    "id": 555,
                    "reference": intent.reference,
                    "status": "success",
                    "amount": intent.amount_kobo,
                    "currency": "NGN",
                },
            }
        ).encode()


class ConcurrentInitializationTests(PaymentRaceTestCase):
    def test_two_simultaneous_taps_start_one_payment(self):
        run_together(self.initialize, [(), ()])

        self.assertEqual(PaymentIntent.objects.filter(booking=self.booking).count(), 1)

    def test_the_provider_is_only_asked_to_collect_once(self):
        # The part a customer would notice, since two collections is two entries
        # on their statement.
        run_together(self.initialize, [(), ()])

        self.assertEqual(len(FakeGateway.initialized), 1)

    def test_two_simultaneous_retries_of_one_request_start_one_payment(self):
        run_together(self.initialize, [("tap-once",), ("tap-once",)])

        self.assertEqual(PaymentIntent.objects.filter(booking=self.booking).count(), 1)
        self.assertEqual(len(FakeGateway.initialized), 1)

    def test_four_at_once_still_start_one_payment(self):
        run_together(self.initialize, [(), (), (), ()])

        self.assertEqual(PaymentIntent.objects.filter(booking=self.booking).count(), 1)


class ConcurrentVerificationTests(PaymentRaceTestCase):
    def test_two_simultaneous_verifications_produce_one_successful_payment(self):
        intent = self.arranged_intent()

        def verify() -> None:
            payment_services.verify_payment(intent.pk, self.customer)

        run_together(lambda: verify(), [(), ()])

        self.assertEqual(
            PaymentIntent.objects.filter(
                booking=self.booking, status=PaymentStatus.SUCCESSFUL
            ).count(),
            1,
        )

    def test_a_webhook_and_a_verification_at_once_leave_one_paid_payment(self):
        intent = self.arranged_intent()
        body = self.success_body(intent)

        def by_webhook() -> None:
            Client().post(
                WEBHOOK,
                data=body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE=FakeGateway.sign(body),
            )

        def by_verification() -> None:
            payment_services.verify_payment(intent.pk, self.customer)

        self.race(by_webhook, by_verification)

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentStatus.SUCCESSFUL)
        self.assertEqual(PaymentIntent.objects.filter(booking=self.booking).count(), 1)

    def test_two_deliveries_of_one_webhook_at_once_are_applied_once(self):
        from apps.payments.webhooks import WebhookEvent

        intent = self.arranged_intent()
        body = self.success_body(intent)

        def deliver() -> None:
            Client().post(
                WEBHOOK,
                data=body,
                content_type="application/json",
                HTTP_X_PAYSTACK_SIGNATURE=FakeGateway.sign(body),
            )

        run_together(lambda: deliver(), [(), ()])

        self.assertEqual(WebhookEvent.objects.count(), 1)
        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentStatus.SUCCESSFUL)

    def race(self, first, second) -> None:
        barrier = threading.Barrier(2)

        def attempt(action) -> None:
            try:
                barrier.wait(timeout=10)
                action()
            except Exception:
                pass
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=attempt, args=(first,)),
            threading.Thread(target=attempt, args=(second,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)


class ConcurrentSettlementTriggerTests(ConcurrentVerificationTests):
    """The two conditions for a settlement, arriving at the same instant."""

    def test_a_completion_and_a_payment_at_once_settle_exactly_once(self):
        intent = self.arranged_intent()

        for target, actor in (
            (BookingStatus.IN_PROGRESS, ActorType.PROVIDER),
            (BookingStatus.AWAITING_CONFIRMATION, ActorType.PROVIDER),
        ):
            self.booking.refresh_from_db()
            transition(self.booking, target, actor_type=actor, actor_id=self.booking.provider_id)

        def complete() -> None:
            booking = self.booking.__class__.objects.get(pk=self.booking.pk)
            transition(
                booking,
                BookingStatus.COMPLETED,
                actor_type=ActorType.CUSTOMER,
                actor_id=self.customer.id,
            )

        def pay() -> None:
            payment_services.verify_payment(intent.pk, self.customer)

        self.race(complete, pay)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.COMPLETED)
        self.assertEqual(
            BookingSettlement.objects.filter(booking=self.booking).count(),
            1,
            "one completed and paid booking must earn exactly one settlement",
        )

    def test_the_provider_earns_the_right_amount_once(self):
        intent = self.arranged_intent()

        for target, actor in (
            (BookingStatus.IN_PROGRESS, ActorType.PROVIDER),
            (BookingStatus.AWAITING_CONFIRMATION, ActorType.PROVIDER),
        ):
            self.booking.refresh_from_db()
            transition(self.booking, target, actor_type=actor, actor_id=self.booking.provider_id)

        def complete() -> None:
            booking = self.booking.__class__.objects.get(pk=self.booking.pk)
            transition(
                booking,
                BookingStatus.COMPLETED,
                actor_type=ActorType.CUSTOMER,
                actor_id=self.customer.id,
            )

        def pay() -> None:
            payment_services.verify_payment(intent.pk, self.customer)

        self.race(complete, pay)

        earnings = services.available_balance(self.setup["provider"])
        self.assertEqual(earnings.settlement_count, 1)
        self.assertEqual(earnings.net_earned_kobo, 1_600_000)


class ConcurrentBankVerificationTests(TransactionTestCase):
    """Two taps on confirm, at once."""

    reset_sequences = True

    def setUp(self):
        FakeBankResolver.clear()
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider, verified=False)
        FakeBankResolver.arrange(
            account_number="0123456789", bank_code="058", account_name="Adaeze Okonkwo"
        )

    def verify(self) -> None:
        services.verify_destination(self.provider, "0123456789")

    def test_two_simultaneous_verifications_leave_one_verified_destination(self):
        outcomes = run_together(self.verify, [(), ()])

        self.assertEqual(outcomes, [None, None])
        destinations = PayoutDestination.objects.filter(provider=self.provider)
        self.assertEqual(destinations.count(), 1)
        self.assertTrue(destinations.get().is_verified)
