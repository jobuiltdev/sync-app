"""The derived balance.

There is no stored balance to test, which is the point. What these check is that
the arithmetic over the immutable records answers the only question that matters:
how much may this provider ask for right now.
"""

from django.test import TestCase

from apps.bookings.state import ActorType
from apps.payments import services
from apps.payments.payouts import PayoutRequest, PayoutStatus
from apps.payments.services import available_balance
from apps.payments.tests.factories import earn, earning_setup, make_destination


class EmptyBalanceTests(TestCase):
    def setUp(self):
        self.setup = earning_setup()

    def test_a_provider_who_has_finished_nothing_has_nothing(self):
        earnings = available_balance(self.setup["provider"])

        self.assertEqual(earnings.settlement_count, 0)
        self.assertEqual(earnings.net_earned_kobo, 0)
        self.assertEqual(earnings.available_kobo, 0)

    def test_a_booking_that_is_not_finished_earns_nothing_yet(self):
        from apps.bookings.services import create_booking
        from apps.bookings.tests.factories import VALID_CLEANING_DETAILS, accept_first_offer

        booking = create_booking(
            customer=self.setup["customer"],
            service=self.setup["service"],
            address=self.setup["address"],
            details=VALID_CLEANING_DETAILS,
        )
        accept_first_offer(booking, self.setup["provider"])

        self.assertEqual(available_balance(self.setup["provider"]).available_kobo, 0)


class EarnedBalanceTests(TestCase):
    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]

    def test_one_completed_booking_is_the_provider_share_of_it(self):
        earn(self.setup)

        earnings = available_balance(self.provider)

        self.assertEqual(earnings.settlement_count, 1)
        self.assertEqual(earnings.gross_earned_kobo, 2_000_000)
        self.assertEqual(earnings.commission_kobo, 400_000)
        self.assertEqual(earnings.net_earned_kobo, 1_600_000)
        self.assertEqual(earnings.available_kobo, 1_600_000)

    def test_several_settlements_add_up(self):
        earn(self.setup)
        earn(self.setup, price_kobo=1_000_000)
        earn(self.setup, price_kobo=500_000)

        earnings = available_balance(self.provider)

        self.assertEqual(earnings.settlement_count, 3)
        self.assertEqual(earnings.gross_earned_kobo, 3_500_000)
        self.assertEqual(earnings.net_earned_kobo, 2_800_000)
        self.assertEqual(earnings.available_kobo, 2_800_000)

    def test_another_provider_earnings_are_not_counted(self):
        earn(self.setup)
        other = earning_setup(slug="other-clean")
        earn(other, price_kobo=5_000_000)

        self.assertEqual(available_balance(self.provider).available_kobo, 1_600_000)
        self.assertEqual(available_balance(other["provider"]).available_kobo, 4_000_000)


class BalanceAfterPayoutTests(TestCase):
    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)

    def request(self, amount_kobo: int) -> PayoutRequest:
        return services.request_payout(
            provider=self.provider,
            actor=self.provider.user,
            amount_kobo=amount_kobo,
        )

    def test_a_requested_payout_is_reserved_rather_than_available(self):
        self.request(600_000)

        earnings = available_balance(self.provider)

        self.assertEqual(earnings.net_earned_kobo, 1_600_000)
        self.assertEqual(earnings.reserved_kobo, 600_000)
        self.assertEqual(earnings.paid_out_kobo, 0)
        self.assertEqual(earnings.available_kobo, 1_000_000)

    def test_a_payout_being_processed_is_still_reserved(self):
        services.start_processing(self.request(600_000))

        earnings = available_balance(self.provider)

        self.assertEqual(earnings.reserved_kobo, 600_000)
        self.assertEqual(earnings.available_kobo, 1_000_000)

    def test_a_paid_payout_is_gone_rather_than_reserved(self):
        services.mark_paid(services.start_processing(self.request(600_000)))

        earnings = available_balance(self.provider)

        self.assertEqual(earnings.reserved_kobo, 0)
        self.assertEqual(earnings.paid_out_kobo, 600_000)
        self.assertEqual(earnings.available_kobo, 1_000_000)

    def test_a_failed_payout_returns_the_money_by_arithmetic(self):
        # Nothing credits anything back. A failed payout simply stops being
        # subtracted, which is why there is no compensating step to forget.
        services.mark_failed(self.request(600_000), reason="Bank rejected the transfer")

        earnings = available_balance(self.provider)

        self.assertEqual(earnings.reserved_kobo, 0)
        self.assertEqual(earnings.paid_out_kobo, 0)
        self.assertEqual(earnings.available_kobo, 1_600_000)

    def test_a_cancelled_payout_returns_the_money_too(self):
        payout = self.request(600_000)
        services.transition_payout(payout, PayoutStatus.CANCELLED, actor_type=ActorType.PROVIDER)

        self.assertEqual(available_balance(self.provider).available_kobo, 1_600_000)

    def test_withdrawing_everything_leaves_exactly_nothing(self):
        services.mark_paid(services.start_processing(self.request(1_600_000)))

        earnings = available_balance(self.provider)

        self.assertEqual(earnings.available_kobo, 0)
        self.assertGreaterEqual(earnings.available_kobo, 0)

    def test_earning_again_after_being_paid_adds_to_what_is_available(self):
        services.mark_paid(services.start_processing(self.request(1_600_000)))
        earn(self.setup, price_kobo=1_000_000)

        earnings = available_balance(self.provider)

        self.assertEqual(earnings.net_earned_kobo, 2_400_000)
        self.assertEqual(earnings.paid_out_kobo, 1_600_000)
        self.assertEqual(earnings.available_kobo, 800_000)

    def test_a_sequence_of_payouts_never_drives_the_balance_below_zero(self):
        for amount in (400_000, 400_000, 400_000, 400_000):
            services.mark_paid(services.start_processing(self.request(amount)))

        earnings = available_balance(self.provider)

        self.assertEqual(earnings.paid_out_kobo, 1_600_000)
        self.assertEqual(earnings.available_kobo, 0)
