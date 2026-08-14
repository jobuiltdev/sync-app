"""Financial races, against a real database with real threads.

TransactionTestCase rather than TestCase for the same reason the offer race tests
use one: threads need committed transactions, and the usual wrapper hides every
write inside one nobody else can see, which is precisely the condition being
tested against.

Two races matter here. Two providers cannot both be paid the same earnings, and
one completed booking cannot earn its provider two settlements.
"""

import threading

from django.db import connections, transaction
from django.test import TransactionTestCase

from apps.bookings.services import transition
from apps.bookings.state import ActorType, BookingStatus
from apps.bookings.tests.factories import VALID_CLEANING_DETAILS, accept_first_offer
from apps.payments import services
from apps.payments.payouts import RESERVING_STATUSES, PayoutRequest, PayoutStatus
from apps.payments.settlements import BookingSettlement
from apps.payments.tests.factories import earn, earning_setup, make_destination


def run_together(target, arguments: list[tuple]) -> list[Exception | None]:
    """Fires one thread per argument tuple, released from a barrier together.

    The barrier is what makes this a race rather than a sequence. Each thread
    closes its own connection afterwards, since a thread that leaves one open
    holds a lock the test then waits on forever.
    """
    outcomes: list[Exception | None] = [None] * len(arguments)
    barrier = threading.Barrier(len(arguments))

    def attempt(index: int, args: tuple) -> None:
        try:
            barrier.wait(timeout=10)
            target(*args)
        except Exception as exc:
            outcomes[index] = exc
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=attempt, args=(index, args)) for index, args in enumerate(arguments)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    return outcomes


class ConcurrentPayoutRequestTests(TransactionTestCase):
    """Two requests for the same balance, at the same instant."""

    reset_sequences = True

    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)

        # 16,000 naira available, and both attempts want 10,000 of it. Together
        # they are more than exists, so a design that let both through would pay
        # out money nobody earned.
        self.available = services.available_balance(self.provider).available_kobo
        self.assertEqual(self.available, 1_600_000)

    def request(self, amount_kobo: int) -> None:
        services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=amount_kobo
        )

    def test_only_one_of_two_simultaneous_requests_succeeds(self):
        outcomes = run_together(self.request, [(1_000_000,), (1_000_000,)])

        winners = [outcome for outcome in outcomes if outcome is None]
        losers = [outcome for outcome in outcomes if outcome is not None]

        self.assertEqual(len(winners), 1, f"expected one winner, got {outcomes}")
        self.assertEqual(len(losers), 1)
        self.assertEqual(PayoutRequest.objects.count(), 1)

    def test_the_loser_fails_safely_rather_than_leaving_a_half_written_payout(self):
        run_together(self.request, [(1_000_000,), (1_000_000,)])

        payouts = PayoutRequest.objects.all()

        self.assertEqual(payouts.count(), 1)
        self.assertEqual(payouts.get().status, PayoutStatus.REQUESTED)
        self.assertEqual(payouts.get().amount_kobo, 1_000_000)

    def test_the_same_earnings_are_never_allocated_twice(self):
        run_together(self.request, [(1_000_000,), (1_000_000,)])

        reserved = sum(
            payout.amount_kobo
            for payout in PayoutRequest.objects.filter(status__in=RESERVING_STATUSES)
        )

        self.assertLessEqual(reserved, self.available)

    def test_the_available_balance_never_goes_negative(self):
        run_together(self.request, [(1_000_000,), (1_000_000,)])

        self.assertGreaterEqual(services.available_balance(self.provider).available_kobo, 0)

    def test_even_four_at_once_produce_exactly_one_payout(self):
        run_together(self.request, [(400_000,)] * 4)

        self.assertEqual(PayoutRequest.objects.count(), 1)
        self.assertGreaterEqual(services.available_balance(self.provider).available_kobo, 0)

    def test_a_retried_request_racing_itself_still_produces_one_payout(self):
        def replay(key: str) -> None:
            services.request_payout(
                provider=self.provider,
                actor=self.provider.user,
                amount_kobo=1_000_000,
                idempotency_key=key,
            )

        run_together(replay, [("retry-me",), ("retry-me",)])

        self.assertEqual(PayoutRequest.objects.count(), 1)


class ConcurrentSettlementTests(TransactionTestCase):
    """One finished job, two workers trying to settle it."""

    reset_sequences = True

    def setUp(self):
        from apps.bookings.services import create_booking

        self.setup = earning_setup()
        booking = create_booking(
            customer=self.setup["customer"],
            service=self.setup["service"],
            address=self.setup["address"],
            details=VALID_CLEANING_DETAILS,
        )
        accept_first_offer(booking, self.setup["provider"])
        booking.refresh_from_db()

        transition(
            booking,
            BookingStatus.IN_PROGRESS,
            actor_type=ActorType.PROVIDER,
            actor_id=booking.provider_id,
        )
        transition(
            booking,
            BookingStatus.AWAITING_CONFIRMATION,
            actor_type=ActorType.PROVIDER,
            actor_id=booking.provider_id,
        )
        self.booking = booking

    def complete(self) -> None:
        booking = self.booking.__class__.objects.get(pk=self.booking.pk)
        with transaction.atomic():
            transition(
                booking,
                BookingStatus.COMPLETED,
                actor_type=ActorType.CUSTOMER,
                actor_id=booking.customer_id,
            )

    def settle(self) -> None:
        booking = self.booking.__class__.objects.get(pk=self.booking.pk)
        services.create_settlement(booking)

    def test_two_simultaneous_completions_produce_exactly_one_settlement(self):
        run_together(lambda: self.complete(), [(), ()])

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.COMPLETED)
        self.assertEqual(BookingSettlement.objects.filter(booking=self.booking).count(), 1)

    def test_two_simultaneous_completions_do_not_double_the_earnings(self):
        run_together(lambda: self.complete(), [(), ()])

        earnings = services.available_balance(self.setup["provider"])

        self.assertEqual(earnings.settlement_count, 1)
        self.assertEqual(earnings.net_earned_kobo, 1_600_000)

    def test_settling_the_same_completed_booking_from_two_workers_creates_one_row(self):
        self.complete()
        BookingSettlement.objects.all().delete()

        outcomes = run_together(lambda: self.settle(), [(), (), ()])

        self.assertEqual(outcomes, [None, None, None], "every caller should get a settlement")
        self.assertEqual(BookingSettlement.objects.filter(booking=self.booking).count(), 1)
