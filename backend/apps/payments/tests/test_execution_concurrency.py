"""Payout execution under contention, with real threads and a real database.

Two workers pick up the same task. A provider taps request while a worker is
sending. A sweep runs twice at once. All of these happen in production, and the
wrong outcome for any of them is money moving twice.
"""

from django.db import connections
from django.test import TransactionTestCase
from django.utils import timezone

from apps.bookings.services import create_booking
from apps.bookings.state import BookingStatus
from apps.bookings.tests.factories import VALID_CLEANING_DETAILS
from apps.payments import services
from apps.payments.execution import execute_payout, reconcile_payout
from apps.payments.payouts import RESERVING_STATUSES, PayoutRequest, PayoutStatus
from apps.payments.settlements import BookingSettlement
from apps.payments.tests.concurrency import run_together
from apps.payments.tests.factories import earn, earning_setup, make_destination
from apps.payments.transfers.base import TransferState
from apps.payments.transfers.fake import FakeTransferProvider


class ConcurrentPayoutExecutionTests(TransactionTestCase):
    """The case that would cost real money: one payout, two workers."""

    reset_sequences = True

    def setUp(self):
        FakeTransferProvider.clear()
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)
        self.payout = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=600_000
        )

    def send(self) -> None:
        execute_payout(self.payout.pk)

    def test_two_workers_sending_one_payout_submit_one_transfer(self):
        outcomes = run_together(lambda: self.send(), [(), ()])

        self.assertEqual(
            len(FakeTransferProvider.submitted),
            1,
            f"a second transfer was submitted; outcomes were {outcomes}",
        )

    def test_the_loser_is_refused_rather_than_failing_silently(self):
        outcomes = run_together(lambda: self.send(), [(), ()])

        refused = [outcome for outcome in outcomes if outcome is not None]
        self.assertEqual(len(refused), 1)

    def test_four_workers_still_submit_one_transfer(self):
        run_together(lambda: self.send(), [(), (), (), ()])

        self.assertEqual(len(FakeTransferProvider.submitted), 1)

    def test_one_transfer_reference_exists_afterwards(self):
        run_together(lambda: self.send(), [(), ()])

        payout = PayoutRequest.objects.get(pk=self.payout.pk)
        self.assertTrue(payout.transfer_reference)
        self.assertEqual(PayoutRequest.objects.exclude(transfer_reference="").count(), 1)

    def test_two_workers_reconciling_at_once_resolve_it_once(self):
        execute_payout(self.payout.pk)
        reference = PayoutRequest.objects.get(pk=self.payout.pk).transfer_reference
        FakeTransferProvider.arrange(reference, state=TransferState.SUCCESSFUL)

        run_together(lambda: reconcile_payout(self.payout.pk), [(), ()])

        payout = PayoutRequest.objects.get(pk=self.payout.pk)
        self.assertEqual(payout.status, PayoutStatus.PAID)
        self.assertEqual(services.available_balance(self.provider).paid_out_kobo, 600_000)

    def test_sending_while_the_provider_cancels_leaves_one_outcome(self):
        # A provider tapping cancel at the moment a worker picks the payout up.
        # Either order is fine; both happening is not.
        def cancel() -> None:
            services.cancel_payout(self.payout.pk, self.provider)

        _race(self.send, cancel)

        payout = PayoutRequest.objects.get(pk=self.payout.pk)
        if payout.status == PayoutStatus.CANCELLED:
            self.assertEqual(FakeTransferProvider.submitted, [])
        else:
            self.assertEqual(payout.status, PayoutStatus.PROCESSING)
            self.assertEqual(len(FakeTransferProvider.submitted), 1)


class BalanceUnderExecutionTests(TransactionTestCase):
    """The derived balance must not go negative, whatever happens at once."""

    reset_sequences = True

    def setUp(self):
        FakeTransferProvider.clear()
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)

    def request(self, amount_kobo: int) -> None:
        services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=amount_kobo
        )

    def test_requesting_while_another_payout_executes_cannot_overdraw(self):
        first = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=1_600_000
        )

        def send() -> None:
            execute_payout(first.pk)

        def ask_again() -> None:
            self.request(1_600_000)

        _race(send, ask_again)

        earnings = services.available_balance(self.provider)
        self.assertGreaterEqual(earnings.available_kobo, 0)
        reserved = sum(
            payout.amount_kobo
            for payout in PayoutRequest.objects.filter(status__in=RESERVING_STATUSES)
        )
        self.assertLessEqual(reserved, earnings.net_earned_kobo)

    def test_a_paid_payout_and_a_new_request_cannot_spend_the_same_money(self):
        first = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=1_600_000
        )
        execute_payout(first.pk)
        reference = PayoutRequest.objects.get(pk=first.pk).transfer_reference
        FakeTransferProvider.arrange(reference, state=TransferState.SUCCESSFUL)

        def settle() -> None:
            reconcile_payout(first.pk)

        def ask_again() -> None:
            self.request(1_600_000)

        _race(settle, ask_again)

        earnings = services.available_balance(self.provider)
        self.assertGreaterEqual(earnings.available_kobo, 0)
        self.assertLessEqual(
            earnings.paid_out_kobo + earnings.reserved_kobo, earnings.net_earned_kobo
        )

    def test_a_failed_transfer_returns_availability_by_arithmetic_alone(self):
        payout = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=1_600_000
        )
        FakeTransferProvider.fail_next_submit_with = "unknown"
        execute_payout(payout.pk)
        FakeTransferProvider.arrange(
            PayoutRequest.objects.get(pk=payout.pk).transfer_reference,
            state=TransferState.FAILED,
        )

        run_together(lambda: reconcile_payout(payout.pk), [(), ()])

        # Nothing credited anything back. The failed payout simply stopped being
        # subtracted.
        self.assertEqual(services.available_balance(self.provider).available_kobo, 1_600_000)


class ConcurrentSweepTests(TransactionTestCase):
    """Two schedulers, or one scheduler and a slow previous run."""

    reset_sequences = True

    def setUp(self):
        self.setup = earning_setup()

    def test_two_offer_sweeps_at_once_expire_a_booking_once(self):
        from datetime import timedelta

        from apps.bookings.offers import Offer
        from apps.bookings.tasks import expire_stale_offers

        booking = create_booking(
            customer=self.setup["customer"],
            service=self.setup["service"],
            address=self.setup["address"],
            details=VALID_CLEANING_DETAILS,
        )
        Offer.objects.filter(booking=booking).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        run_together(lambda: expire_stale_offers(), [(), ()])

        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.EXPIRED)
        self.assertEqual(
            booking.events.filter(to_status=BookingStatus.EXPIRED).count(),
            1,
            "the booking was expired twice",
        )

    def test_two_consistency_sweeps_at_once_settle_once(self):
        from apps.bookings.tests.factories import accept_first_offer
        from apps.payments.tasks import sweep_financial_consistency
        from apps.payments.tests.factories import complete_booking, pay_booking

        booking = create_booking(
            customer=self.setup["customer"],
            service=self.setup["service"],
            address=self.setup["address"],
            details=VALID_CLEANING_DETAILS,
        )
        accept_first_offer(booking, self.setup["provider"])
        booking.refresh_from_db()
        pay_booking(booking)
        complete_booking(booking)
        BookingSettlement.objects.filter(booking=booking).delete()

        run_together(lambda: sweep_financial_consistency(), [(), ()])

        self.assertEqual(BookingSettlement.objects.filter(booking=booking).count(), 1)


def _race(first, second) -> list:
    """Runs two different callables at the same instant.

    `run_together` fires one callable with several argument sets; this fires two
    different ones, which is what most of the interesting races here are.
    """
    import threading

    outcomes: list = [None, None]
    barrier = threading.Barrier(2)

    def attempt(index: int, action) -> None:
        try:
            barrier.wait(timeout=10)
            action()
        except Exception as exc:
            outcomes[index] = exc
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=attempt, args=(0, first)),
        threading.Thread(target=attempt, args=(1, second)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    return outcomes
