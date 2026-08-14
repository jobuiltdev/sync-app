"""The commission split, on its own.

No database, no booking, no provider. If this arithmetic is wrong then every
settlement ever written is wrong, so it is worth testing where nothing else can
obscure the failure.
"""

from decimal import Decimal

from django.test import SimpleTestCase

from apps.payments.money import BASIS_POINTS, split_commission


class SplitTests(SimpleTestCase):
    def test_a_normal_rate_divides_the_total(self):
        split = split_commission(2_000_000, 2_000)

        self.assertEqual(split.gross_kobo, 2_000_000)
        self.assertEqual(split.commission_kobo, 400_000)
        self.assertEqual(split.provider_kobo, 1_600_000)

    def test_zero_commission_gives_the_provider_everything(self):
        split = split_commission(2_000_000, 0)

        self.assertEqual(split.commission_kobo, 0)
        self.assertEqual(split.provider_kobo, 2_000_000)

    def test_a_full_rate_leaves_the_provider_nothing_rather_than_a_debt(self):
        split = split_commission(2_000_000, BASIS_POINTS)

        self.assertEqual(split.commission_kobo, 2_000_000)
        self.assertEqual(split.provider_kobo, 0)

    def test_a_free_booking_settles_at_zero_rather_than_failing(self):
        split = split_commission(0, 2_000)

        self.assertEqual((split.gross_kobo, split.commission_kobo, split.provider_kobo), (0, 0, 0))

    def test_the_invariant_holds_across_the_range(self):
        for gross in (0, 1, 7, 99, 12_345, 999_999, 2_000_000, 10**12):
            for rate in (0, 1, 250, 1_500, 2_000, 3_333, 9_999, BASIS_POINTS):
                split = split_commission(gross, rate)

                self.assertEqual(
                    split.provider_kobo,
                    split.gross_kobo - split.commission_kobo,
                    f"broken at {gross} kobo at {rate} bps",
                )
                self.assertGreaterEqual(split.commission_kobo, 0)
                self.assertGreaterEqual(split.provider_kobo, 0)
                self.assertLessEqual(split.commission_kobo, split.gross_kobo)

    def test_rounding_never_favours_the_platform(self):
        # 1 kobo at 33.33 percent is a third of a kobo. Nobody can be paid that,
        # and the side that loses the fraction is deliberately not the provider.
        split = split_commission(1, 3_333)

        self.assertEqual(split.commission_kobo, 0)
        self.assertEqual(split.provider_kobo, 1)

    def test_everything_it_returns_is_an_integer(self):
        split = split_commission(333_333, 1_777)

        for amount in (split.gross_kobo, split.commission_kobo, split.provider_kobo):
            self.assertIsInstance(amount, int)
            self.assertNotIsInstance(amount, float)

    def test_the_result_matches_exact_decimal_arithmetic(self):
        # The property that makes integer kobo safe: the answer is the same one
        # arbitrary-precision decimal maths gives, which is not true of a float.
        for gross, rate in ((999_999, 1_777), (123_456_789, 725), (10**15 + 7, 3_333)):
            expected = int(Decimal(gross) * Decimal(rate) / Decimal(BASIS_POINTS))

            self.assertEqual(split_commission(gross, rate).commission_kobo, expected)

    def test_a_negative_total_is_refused(self):
        with self.assertRaises(ValueError):
            split_commission(-1, 2_000)

    def test_a_rate_above_the_whole_booking_is_refused(self):
        # Otherwise a misconfigured rate would quietly produce a provider debt.
        with self.assertRaises(ValueError):
            split_commission(2_000_000, BASIS_POINTS + 1)

    def test_a_negative_rate_is_refused(self):
        with self.assertRaises(ValueError):
            split_commission(2_000_000, -1)
