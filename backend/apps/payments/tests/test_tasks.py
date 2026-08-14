"""The background tasks, run inline.

Test settings put Celery in eager mode, so a task is called like a function and
its effect is visible immediately. That is what makes the suite runnable with no
worker and no broker, and it means these test the task bodies rather than the
queue: the queue is Celery's to get right, the idempotency is ours.
"""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.bookings.services import create_booking
from apps.bookings.state import BookingStatus
from apps.bookings.tests.factories import VALID_CLEANING_DETAILS, accept_first_offer
from apps.payments import services
from apps.payments.anomalies import AnomalyClass, AnomalyKind, FinancialAnomaly
from apps.payments.gateways.base import PaymentState
from apps.payments.gateways.fake import FakeGateway
from apps.payments.intents import PaymentIntent, PaymentStatus
from apps.payments.payouts import PayoutStatus
from apps.payments.settlements import BookingSettlement
from apps.payments.tasks import (
    execute_payout_task,
    reconcile_payouts,
    reconcile_pending_payments,
    sweep_financial_consistency,
)
from apps.payments.tests.factories import (
    DEFAULT_PRICE_KOBO,
    complete_booking,
    earn,
    earning_setup,
    make_destination,
    pay_booking,
)
from apps.payments.transfers.base import TransferState
from apps.payments.transfers.fake import FakeTransferProvider


def age(intent: PaymentIntent, seconds: int) -> PaymentIntent:
    """Backdates a payment so the reconciliation window includes it."""
    PaymentIntent.objects.filter(pk=intent.pk).update(
        created_at=timezone.now() - timedelta(seconds=seconds)
    )
    intent.refresh_from_db()
    return intent


class PaymentReconciliationTaskTests(TestCase):
    def setUp(self):
        FakeGateway.clear()
        self.setup = earning_setup()
        self.customer = self.setup["customer"]
        self.booking = self.book()

    def book(self):
        booking = create_booking(
            customer=self.customer,
            service=self.setup["service"],
            address=self.setup["address"],
            details=VALID_CLEANING_DETAILS,
        )
        accept_first_offer(booking, self.setup["provider"])
        booking.refresh_from_db()
        return booking

    def pending(self, *, seconds: int = 1800) -> PaymentIntent:
        from apps.payments import payment_services

        intent = payment_services.initialize_payment(booking=self.booking, customer=self.customer)
        return age(intent, seconds)

    def test_a_payment_the_provider_now_calls_successful_is_resolved(self):
        intent = self.pending()
        FakeGateway.arrange(intent.reference, amount_kobo=intent.amount_kobo, currency="NGN")

        result = reconcile_pending_payments()

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentStatus.SUCCESSFUL)
        self.assertEqual(result["resolved"], 1)

    def test_a_payment_the_provider_calls_failed_is_failed(self):
        intent = self.pending()
        FakeGateway.arrange(
            intent.reference,
            state=PaymentState.FAILED,
            amount_kobo=intent.amount_kobo,
            currency="NGN",
        )

        reconcile_pending_payments()

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentStatus.FAILED)

    def test_a_payment_still_pending_at_the_provider_is_left_alone(self):
        # The rule that matters. Age is not evidence: a customer part way
        # through a bank transfer is not a failed payment.
        intent = self.pending(seconds=86_400)
        FakeGateway.arrange(
            intent.reference,
            state=PaymentState.PENDING,
            amount_kobo=intent.amount_kobo,
            currency="NGN",
        )

        result = reconcile_pending_payments()

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentStatus.INITIALIZED)
        self.assertEqual(result["pending"], 1)

    def test_an_unknown_provider_state_never_becomes_successful(self):
        intent = self.pending()
        FakeGateway.payments.pop(intent.reference, None)

        reconcile_pending_payments()

        intent.refresh_from_db()
        self.assertNotEqual(intent.status, PaymentStatus.SUCCESSFUL)

    def test_a_provider_timeout_leaves_the_payment_untouched(self):
        from unittest.mock import patch

        from apps.payments.gateways.base import GatewayError

        intent = self.pending()

        with patch.object(FakeGateway, "fetch", side_effect=GatewayError("timeout")):
            result = reconcile_pending_payments()

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentStatus.INITIALIZED)
        self.assertEqual(result["unreachable"], 1)

    def test_an_amount_mismatch_is_refused_and_flagged(self):
        intent = self.pending()
        FakeGateway.arrange(intent.reference, amount_kobo=100, currency="NGN")

        result = reconcile_pending_payments()

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentStatus.INITIALIZED)
        self.assertEqual(result["mismatch"], 1)
        self.assertTrue(
            FinancialAnomaly.objects.filter(
                kind=AnomalyKind.UNRESOLVED_PAYMENT, classification=AnomalyClass.REVIEW
            ).exists()
        )

    def test_a_currency_mismatch_is_refused(self):
        intent = self.pending()
        FakeGateway.arrange(intent.reference, amount_kobo=intent.amount_kobo, currency="USD")

        reconcile_pending_payments()

        intent.refresh_from_db()
        self.assertEqual(intent.status, PaymentStatus.INITIALIZED)

    def test_a_payment_too_young_is_not_swept(self):
        # Sweeping a payment the customer is still typing their card into would
        # resolve it as failed while they were mid-checkout.
        self.pending(seconds=10)

        result = reconcile_pending_payments()

        self.assertEqual(result["resolved"] + result["pending"], 0)

    def test_running_it_twice_resolves_once(self):
        intent = self.pending()
        FakeGateway.arrange(intent.reference, amount_kobo=intent.amount_kobo, currency="NGN")

        reconcile_pending_payments()
        second = reconcile_pending_payments()

        self.assertEqual(PaymentIntent.objects.filter(booking=self.booking).count(), 1)
        self.assertEqual(second["resolved"], 0)

    def test_a_resolved_payment_settles_a_completed_booking(self):
        complete_booking(self.booking)
        intent = self.pending()
        FakeGateway.arrange(intent.reference, amount_kobo=intent.amount_kobo, currency="NGN")

        reconcile_pending_payments()

        self.assertEqual(BookingSettlement.objects.filter(booking=self.booking).count(), 1)

    @override_settings(
        PAYMENT_RECONCILIATION={"PENDING_AFTER_SECONDS": 900, "GIVE_UP_AFTER_SECONDS": 3600}
    )
    def test_a_payment_beyond_the_window_is_flagged_rather_than_swept(self):
        self.pending(seconds=7200)

        result = reconcile_pending_payments()

        self.assertEqual(result["flagged"], 1)
        anomaly = FinancialAnomaly.objects.get(kind=AnomalyKind.UNRESOLVED_PAYMENT)
        self.assertEqual(anomaly.classification, AnomalyClass.REVIEW)

    def test_no_payment_is_created_by_reconciliation(self):
        self.pending()

        reconcile_pending_payments()

        self.assertEqual(PaymentIntent.objects.count(), 1)


class PayoutReconciliationTaskTests(TestCase):
    def setUp(self):
        FakeTransferProvider.clear()
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)
        self.payout = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=600_000
        )

    def submit(self, *, unknown: bool = False) -> str:
        from apps.payments.execution import execute_payout

        if unknown:
            FakeTransferProvider.fail_next_submit_with = "unknown"
        execute_payout(self.payout.pk)
        self.payout.refresh_from_db()
        return self.payout.transfer_reference

    def test_it_resolves_a_transfer_the_provider_confirms(self):
        reference = self.submit(unknown=True)
        FakeTransferProvider.arrange(reference, state=TransferState.SUCCESSFUL)

        result = reconcile_payouts()

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.PAID)
        self.assertEqual(result["paid"], 1)

    def test_it_fails_a_transfer_the_provider_rejected(self):
        reference = self.submit(unknown=True)
        FakeTransferProvider.arrange(reference, state=TransferState.FAILED)

        result = reconcile_payouts()

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.FAILED)
        self.assertEqual(result["failed"], 1)

    def test_it_leaves_a_transfer_still_in_flight(self):
        reference = self.submit()
        FakeTransferProvider.arrange(reference, state=TransferState.PENDING)

        result = reconcile_payouts()

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.PROCESSING)
        self.assertEqual(result["still_processing"], 1)

    def test_an_unknown_transfer_stays_unresolved_rather_than_failing(self):
        self.submit(unknown=True)
        FakeTransferProvider.transfers.pop(self.payout.transfer_reference)

        reconcile_payouts()

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.PROCESSING)

    def test_it_does_not_touch_a_payout_that_was_never_submitted(self):
        result = reconcile_payouts()

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.REQUESTED)
        self.assertEqual(sum(result.values()), 0)

    def test_running_it_repeatedly_is_safe(self):
        reference = self.submit(unknown=True)
        FakeTransferProvider.arrange(reference, state=TransferState.SUCCESSFUL)

        for _ in range(5):
            reconcile_payouts()

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.PAID)
        self.assertEqual(services.available_balance(self.provider).paid_out_kobo, 600_000)

    def test_it_never_submits_anything(self):
        # Reconciliation asks. If it could send, the crash window would have a
        # second door into it.
        self.submit(unknown=True)
        submitted = len(FakeTransferProvider.submitted)

        reconcile_payouts()

        self.assertEqual(len(FakeTransferProvider.submitted), submitted)


class ExecutePayoutTaskTests(TestCase):
    def setUp(self):
        FakeTransferProvider.clear()
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)
        self.payout = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=600_000
        )

    def test_the_task_sends_the_transfer(self):
        execute_payout_task(str(self.payout.pk))

        self.assertEqual(len(FakeTransferProvider.submitted), 1)

    def test_the_task_never_retries_a_submitted_payout(self):
        execute_payout_task(str(self.payout.pk))

        # A second run answers rather than raising, and submits nothing.
        result = execute_payout_task(str(self.payout.pk))

        self.assertEqual(result, "already submitted")
        self.assertEqual(len(FakeTransferProvider.submitted), 1)

    def test_the_task_is_configured_never_to_retry(self):
        # The most important line of configuration in the project: a retry of an
        # unanswered transfer submission is how money moves twice.
        self.assertEqual(execute_payout_task.max_retries, 0)

    def test_an_unknown_outcome_does_not_raise_out_of_the_task(self):
        FakeTransferProvider.fail_next_submit_with = "unknown"

        execute_payout_task(str(self.payout.pk))

        self.payout.refresh_from_db()
        self.assertTrue(self.payout.needs_reconciliation)


class ConsistencySweepTests(TestCase):
    def setUp(self):
        FakeGateway.clear()
        self.setup = earning_setup()
        self.provider = self.setup["provider"]

    def booked(self):
        booking = create_booking(
            customer=self.setup["customer"],
            service=self.setup["service"],
            address=self.setup["address"],
            details=VALID_CLEANING_DETAILS,
        )
        accept_first_offer(booking, self.provider)
        booking.refresh_from_db()
        return booking

    def test_a_healthy_system_produces_no_anomalies(self):
        earn(self.setup)

        result = sweep_financial_consistency()

        self.assertEqual(result["review"], 0)
        self.assertFalse(
            FinancialAnomaly.objects.filter(classification=AnomalyClass.REVIEW).exists()
        )

    def test_a_completed_and_paid_booking_with_no_settlement_is_repaired(self):
        # The one anomaly with exactly one correct outcome, so the one the sweep
        # is allowed to fix.
        booking = self.booked()
        pay_booking(booking)
        complete_booking(booking)
        BookingSettlement.objects.filter(booking=booking).delete()

        result = sweep_financial_consistency()

        self.assertEqual(result["repaired"], 1)
        self.assertEqual(BookingSettlement.objects.filter(booking=booking).count(), 1)

    def test_the_repair_is_recorded_and_closed(self):
        booking = self.booked()
        pay_booking(booking)
        complete_booking(booking)
        BookingSettlement.objects.filter(booking=booking).delete()

        sweep_financial_consistency()

        anomaly = FinancialAnomaly.objects.get(kind=AnomalyKind.UNSETTLED_PAID_BOOKING)
        self.assertEqual(anomaly.classification, AnomalyClass.REPAIRED)
        self.assertFalse(anomaly.is_open)

    def test_a_completed_unpaid_booking_is_not_an_anomaly(self):
        # Ordinary. The customer simply has not paid yet.
        booking = self.booked()
        complete_booking(booking)

        result = sweep_financial_consistency()

        self.assertEqual(result["repaired"], 0)
        self.assertEqual(BookingSettlement.objects.count(), 0)

    def test_a_settlement_without_a_payment_is_flagged_and_never_repaired(self):
        # Deleting a settlement would take a provider's earnings away on the
        # say-so of a sweep. Always a person's decision.
        settlement = earn(self.setup)
        PaymentIntent.objects.filter(booking=settlement.booking).delete()

        result = sweep_financial_consistency()

        self.assertGreaterEqual(result["review"], 1)
        self.assertTrue(
            FinancialAnomaly.objects.filter(
                kind=AnomalyKind.SETTLEMENT_WITHOUT_PAYMENT,
                classification=AnomalyClass.REVIEW,
            ).exists()
        )
        self.assertTrue(BookingSettlement.objects.filter(pk=settlement.pk).exists())

    def test_a_settlement_that_disagrees_with_its_booking_is_flagged(self):
        settlement = earn(self.setup)
        booking = settlement.booking
        booking.total_kobo = DEFAULT_PRICE_KOBO * 2
        booking.save(update_fields=["total_kobo"])

        sweep_financial_consistency()

        anomaly = FinancialAnomaly.objects.get(kind=AnomalyKind.SETTLEMENT_AMOUNT_MISMATCH)
        self.assertEqual(anomaly.classification, AnomalyClass.REVIEW)

    def test_a_mismatched_settlement_is_left_exactly_as_it_was(self):
        settlement = earn(self.setup)
        booking = settlement.booking
        booking.total_kobo = 1
        booking.save(update_fields=["total_kobo"])

        sweep_financial_consistency()

        settlement.refresh_from_db()
        self.assertEqual(settlement.gross_amount_kobo, DEFAULT_PRICE_KOBO)

    @override_settings(PAYOUT_EXECUTION={"STALE_AFTER_SECONDS": 0})
    def test_a_payout_stuck_in_flight_is_flagged(self):
        from apps.payments.execution import execute_payout
        from apps.payments.payouts import PayoutRequest

        FakeTransferProvider.clear()
        make_destination(self.provider)
        earn(self.setup)
        payout = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=100_000
        )
        FakeTransferProvider.fail_next_submit_with = "unknown"
        execute_payout(payout.pk)
        PayoutRequest.objects.filter(pk=payout.pk).update(
            submitted_at=timezone.now() - timedelta(hours=2)
        )

        sweep_financial_consistency()

        anomaly = FinancialAnomaly.objects.get(kind=AnomalyKind.STALE_SUBMITTED_PAYOUT)
        self.assertEqual(anomaly.classification, AnomalyClass.REVIEW)
        self.assertIn("never received", anomaly.detail)

    def test_running_the_sweep_repeatedly_produces_one_anomaly_row(self):
        settlement = earn(self.setup)
        PaymentIntent.objects.filter(booking=settlement.booking).delete()

        for _ in range(4):
            sweep_financial_consistency()

        anomaly = FinancialAnomaly.objects.get(kind=AnomalyKind.SETTLEMENT_WITHOUT_PAYMENT)
        self.assertEqual(anomaly.times_seen, 4)
        self.assertEqual(FinancialAnomaly.objects.count(), 1)

    def test_an_anomaly_records_no_sensitive_detail(self):
        settlement = earn(self.setup)
        PaymentIntent.objects.filter(booking=settlement.booking).delete()

        sweep_financial_consistency()

        anomaly = FinancialAnomaly.objects.get(kind=AnomalyKind.SETTLEMENT_WITHOUT_PAYMENT)
        self.assertNotIn("0123456789", anomaly.detail)
        self.assertNotIn(self.setup["customer"].email, anomaly.detail)


class OfferExpiryTaskTests(TestCase):
    def setUp(self):
        self.setup = earning_setup()

    def make_booking(self):
        return create_booking(
            customer=self.setup["customer"],
            service=self.setup["service"],
            address=self.setup["address"],
            details=VALID_CLEANING_DETAILS,
        )

    def lapse(self, booking) -> None:
        from apps.bookings.offers import Offer

        Offer.objects.filter(booking=booking).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

    def test_an_offer_past_its_window_is_expired(self):
        from apps.bookings.offers import Offer, OfferStatus
        from apps.bookings.tasks import expire_stale_offers

        booking = self.make_booking()
        self.lapse(booking)

        result = expire_stale_offers()

        self.assertEqual(result["offers_expired"], 1)
        self.assertEqual(Offer.objects.get(booking=booking).status, OfferStatus.EXPIRED)

    def test_a_booking_whose_offers_all_lapsed_expires(self):
        from apps.bookings.tasks import expire_stale_offers

        booking = self.make_booking()
        self.lapse(booking)

        result = expire_stale_offers()

        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.EXPIRED)
        self.assertEqual(result["bookings_expired"], 1)

    def test_the_expiry_is_recorded_in_the_booking_history(self):
        from apps.bookings.tasks import expire_stale_offers

        booking = self.make_booking()
        self.lapse(booking)
        expire_stale_offers()

        event = booking.events.filter(to_status=BookingStatus.EXPIRED).get()
        self.assertEqual(event.actor_type, "SYSTEM")
        self.assertEqual(event.metadata["task"], "expire_stale_offers")

    def test_an_offer_still_in_its_window_is_untouched(self):
        from apps.bookings.offers import Offer, OfferStatus
        from apps.bookings.tasks import expire_stale_offers

        booking = self.make_booking()

        expire_stale_offers()

        self.assertEqual(Offer.objects.get(booking=booking).status, OfferStatus.PENDING)
        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.MATCHING)

    def test_an_accepted_booking_is_not_expired_by_a_lapsed_sibling_offer(self):
        from apps.bookings.offers import Offer
        from apps.bookings.tasks import expire_stale_offers
        from apps.bookings.tests.factories import make_provider_offering

        second = make_provider_offering(self.setup["service"], email="rival@example.com")
        booking = self.make_booking()
        accept_first_offer(booking, self.setup["provider"])
        Offer.objects.filter(booking=booking).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        expire_stale_offers()

        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.ASSIGNED)
        self.assertIsNotNone(second)

    def test_running_it_twice_expires_nothing_the_second_time(self):
        from apps.bookings.tasks import expire_stale_offers

        booking = self.make_booking()
        self.lapse(booking)

        expire_stale_offers()
        second = expire_stale_offers()

        self.assertEqual(second["offers_expired"], 0)
        self.assertEqual(second["bookings_expired"], 0)
        self.assertEqual(booking.events.filter(to_status=BookingStatus.EXPIRED).count(), 1)

    @override_settings(TASK_BATCH_SIZE=1)
    def test_the_sweep_is_bounded(self):
        from apps.bookings.tasks import expire_stale_offers

        for _ in range(3):
            self.lapse(self.make_booking())

        result = expire_stale_offers()

        self.assertEqual(result["offers_expired"], 1)


class ChallengeCleanupTaskTests(TestCase):
    def setUp(self):
        from apps.accounts.models import User

        self.user = User.objects.create_user(
            email="ada@example.com", password="Lagos-Rider-2026", phone="+2348031234567"
        )

    def make_challenge(self, **overrides):
        from apps.accounts.challenges import VerificationChallenge

        defaults = {
            "user": self.user,
            "channel": "PHONE",
            "destination": "+2348031234567",
            "code_hash": "argon2$notarealhash",
            "expires_at": timezone.now() + timedelta(minutes=10),
            "max_attempts": 5,
        }
        return VerificationChallenge.objects.create(**{**defaults, **overrides})

    def test_an_expired_challenge_is_retired(self):
        from apps.accounts.tasks import retire_stale_challenges

        challenge = self.make_challenge(expires_at=timezone.now() - timedelta(minutes=1))

        result = retire_stale_challenges()

        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.superseded_at)
        self.assertEqual(result["retired"], 1)

    def test_an_exhausted_challenge_is_retired(self):
        from apps.accounts.tasks import retire_stale_challenges

        challenge = self.make_challenge(attempt_count=5)

        retire_stale_challenges()

        challenge.refresh_from_db()
        self.assertIsNotNone(challenge.superseded_at)

    def test_a_live_challenge_is_left_alone(self):
        from apps.accounts.tasks import retire_stale_challenges

        challenge = self.make_challenge()

        retire_stale_challenges()

        challenge.refresh_from_db()
        self.assertIsNone(challenge.superseded_at)
        self.assertTrue(challenge.is_usable)

    def test_a_consumed_challenge_is_never_touched(self):
        # It is the record of a successful verification and the most useful row
        # in the table.
        from apps.accounts.tasks import retire_stale_challenges

        challenge = self.make_challenge(
            consumed_at=timezone.now(), expires_at=timezone.now() - timedelta(days=30)
        )

        retire_stale_challenges()

        challenge.refresh_from_db()
        self.assertIsNone(challenge.superseded_at)

    def test_nothing_is_ever_deleted(self):
        from apps.accounts.challenges import VerificationChallenge
        from apps.accounts.tasks import retire_stale_challenges

        self.make_challenge(expires_at=timezone.now() - timedelta(minutes=1))
        self.make_challenge(consumed_at=timezone.now())

        retire_stale_challenges()

        self.assertEqual(VerificationChallenge.objects.count(), 2)

    def test_the_hash_survives_so_a_replayed_code_still_fails(self):
        from apps.accounts.tasks import retire_stale_challenges

        challenge = self.make_challenge(expires_at=timezone.now() - timedelta(minutes=1))

        retire_stale_challenges()

        challenge.refresh_from_db()
        self.assertEqual(challenge.code_hash, "argon2$notarealhash")

    def test_running_it_twice_retires_nothing_the_second_time(self):
        from apps.accounts.tasks import retire_stale_challenges

        self.make_challenge(expires_at=timezone.now() - timedelta(minutes=1))

        retire_stale_challenges()
        second = retire_stale_challenges()

        self.assertEqual(second["retired"], 0)

    @override_settings(TASK_BATCH_SIZE=1)
    def test_the_cleanup_is_bounded(self):
        from apps.accounts.tasks import retire_stale_challenges

        for _ in range(3):
            self.make_challenge(expires_at=timezone.now() - timedelta(minutes=1))

        self.assertEqual(retire_stale_challenges()["retired"], 1)
