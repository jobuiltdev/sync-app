"""Where payment meets settlement.

M5 settled a booking on completion alone, because no payment existed to wait for.
M6A adds the money, and a provider earning from a booking the customer never
funded would be a debt the marketplace has no way to cover. So a settlement now
needs both, and whichever of the two happens second is what writes it.
"""

from django.test import TestCase

from apps.bookings.services import create_booking
from apps.bookings.state import BookingStatus
from apps.bookings.tests.factories import VALID_CLEANING_DETAILS, accept_first_offer
from apps.payments import payment_services, services
from apps.payments.errors import SettlementUnavailable
from apps.payments.gateways.base import PaymentState
from apps.payments.gateways.fake import FakeGateway
from apps.payments.settlements import BookingSettlement
from apps.payments.tests.factories import (
    DEFAULT_PRICE_KOBO,
    complete_booking,
    earning_setup,
    pay_booking,
)


class SettlementRequiresPaymentTests(TestCase):
    def setUp(self):
        FakeGateway.clear()
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        self.booking = self.book()

    def book(self):
        booking = create_booking(
            customer=self.setup["customer"],
            service=self.setup["service"],
            address=self.setup["address"],
            details=VALID_CLEANING_DETAILS,
        )
        accept_first_offer(booking, self.provider)
        booking.refresh_from_db()
        return booking

    # --- payment then completion ------------------------------------------

    def test_paying_first_then_completing_settles(self):
        pay_booking(self.booking)
        complete_booking(self.booking)

        settlement = BookingSettlement.objects.get(booking=self.booking)
        self.assertEqual(settlement.gross_amount_kobo, DEFAULT_PRICE_KOBO)

    def test_paying_alone_settles_nothing(self):
        pay_booking(self.booking)

        self.assertEqual(BookingSettlement.objects.count(), 0)
        self.assertEqual(services.available_balance(self.provider).available_kobo, 0)

    # --- completion then payment ------------------------------------------

    def test_completing_an_unpaid_booking_earns_the_provider_nothing(self):
        complete_booking(self.booking)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.COMPLETED)
        self.assertEqual(BookingSettlement.objects.count(), 0)
        self.assertEqual(services.available_balance(self.provider).available_kobo, 0)

    def test_paying_after_completion_settles_at_that_moment(self):
        complete_booking(self.booking)
        self.assertEqual(BookingSettlement.objects.count(), 0)

        pay_booking(self.booking)

        settlement = BookingSettlement.objects.get(booking=self.booking)
        self.assertEqual(settlement.provider_amount_kobo, 1_600_000)
        self.assertEqual(services.available_balance(self.provider).available_kobo, 1_600_000)

    def test_a_failed_payment_after_completion_still_settles_nothing(self):
        complete_booking(self.booking)
        pay_booking(self.booking, state=PaymentState.FAILED)

        self.assertEqual(BookingSettlement.objects.count(), 0)

    def test_a_pending_payment_after_completion_settles_nothing_yet(self):
        complete_booking(self.booking)
        intent = payment_services.initialize_payment(
            booking=self.booking, customer=self.setup["customer"]
        )
        FakeGateway.arrange(
            intent.reference, state=PaymentState.PENDING, amount_kobo=intent.amount_kobo
        )
        payment_services.verify_payment(intent.pk, self.setup["customer"])

        self.assertEqual(BookingSettlement.objects.count(), 0)

    def test_a_retried_payment_that_succeeds_settles(self):
        complete_booking(self.booking)
        pay_booking(self.booking, state=PaymentState.FAILED)
        self.assertEqual(BookingSettlement.objects.count(), 0)

        pay_booking(self.booking)

        self.assertEqual(BookingSettlement.objects.count(), 1)

    # --- the strict form says why ------------------------------------------

    def test_asking_to_settle_an_unpaid_booking_says_it_is_waiting_on_money(self):
        complete_booking(self.booking)

        with self.assertRaises(SettlementUnavailable) as caught:
            services.create_settlement(self.booking)

        self.assertEqual(caught.exception.detail.code, "SETTLEMENT_AWAITING_PAYMENT")

    def test_the_forgiving_form_returns_nothing_rather_than_raising(self):
        complete_booking(self.booking)

        self.assertIsNone(services.settle_if_ready(self.booking))

    def test_a_paid_but_unfinished_booking_is_not_settleable_either(self):
        pay_booking(self.booking)

        with self.assertRaises(SettlementUnavailable):
            services.create_settlement(self.booking)

    # --- duplication --------------------------------------------------------

    def test_neither_order_produces_two_settlements(self):
        pay_booking(self.booking)
        complete_booking(self.booking)

        # Both hooks fire again, and neither writes a second row.
        services.settle_if_ready(self.booking)
        services.settle_if_ready(self.booking)

        self.assertEqual(BookingSettlement.objects.filter(booking=self.booking).count(), 1)

    def test_a_duplicate_payment_event_does_not_double_the_earnings(self):
        complete_booking(self.booking)
        intent = pay_booking(self.booking)

        # The provider tells us again, as providers do.
        payment_services.verify_payment(intent.pk, self.setup["customer"])
        payment_services.verify_payment(intent.pk, self.setup["customer"])

        self.assertEqual(BookingSettlement.objects.count(), 1)
        self.assertEqual(services.available_balance(self.provider).net_earned_kobo, 1_600_000)

    def test_the_financial_invariant_still_holds_after_all_of_this(self):
        pay_booking(self.booking)
        complete_booking(self.booking)

        settlement = BookingSettlement.objects.get(booking=self.booking)

        self.assertEqual(
            settlement.provider_amount_kobo,
            settlement.gross_amount_kobo - settlement.commission_amount_kobo,
        )

    def test_the_settlement_amount_comes_from_the_booking_not_the_payment(self):
        # They agree, and they are still read from different places: a payment for
        # a different sum is refused rather than becoming the settled amount.
        pay_booking(self.booking)
        complete_booking(self.booking)

        settlement = BookingSettlement.objects.get(booking=self.booking)
        self.assertEqual(settlement.gross_amount_kobo, self.booking.total_kobo)
