"""Settlements: when one is written, what it holds, and what cannot change it."""

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase, override_settings

from apps.bookings.services import create_booking, transition
from apps.bookings.state import ActorType, BookingStatus
from apps.bookings.tests.factories import (
    VALID_CLEANING_DETAILS,
    accept_first_offer,
    make_address,
    make_customer,
    make_provider_offering,
)
from apps.payments.errors import SettlementUnavailable
from apps.payments.services import create_settlement
from apps.payments.settlements import BookingSettlement, SettlementStatus
from apps.payments.tests.factories import (
    DEFAULT_PRICE_KOBO,
    complete_booking,
    earn,
    earning_setup,
    make_priced_service,
)


class SettlementCreationTests(TestCase):
    def setUp(self):
        self.setup = earning_setup()

    def book(self):
        booking = create_booking(
            customer=self.setup["customer"],
            service=self.setup["service"],
            address=self.setup["address"],
            details=VALID_CLEANING_DETAILS,
        )
        accept_first_offer(booking, self.setup["provider"])
        booking.refresh_from_db()
        return booking

    def test_completing_a_booking_creates_its_settlement(self):
        booking = self.book()

        self.assertFalse(BookingSettlement.objects.filter(booking=booking).exists())

        complete_booking(booking)

        settlement = BookingSettlement.objects.get(booking=booking)
        self.assertEqual(settlement.provider_id, self.setup["provider"].id)
        self.assertEqual(settlement.status, SettlementStatus.PAYABLE)

    def test_the_amounts_come_from_the_booking_total(self):
        booking = self.book()
        complete_booking(booking)

        settlement = BookingSettlement.objects.get(booking=booking)

        self.assertEqual(settlement.gross_amount_kobo, booking.total_kobo)
        self.assertEqual(settlement.gross_amount_kobo, DEFAULT_PRICE_KOBO)
        self.assertEqual(settlement.commission_amount_kobo, 400_000)
        self.assertEqual(settlement.provider_amount_kobo, 1_600_000)

    def test_the_rate_that_was_applied_is_recorded_on_the_row(self):
        booking = self.book()
        complete_booking(booking)

        self.assertEqual(BookingSettlement.objects.get(booking=booking).commission_rate_bps, 2_000)

    def test_the_currency_is_stored_rather_than_assumed(self):
        booking = self.book()
        complete_booking(booking)

        self.assertEqual(BookingSettlement.objects.get(booking=booking).currency, "NGN")

    def test_no_settlement_before_the_booking_is_finished(self):
        booking = self.book()

        for status in (BookingStatus.ASSIGNED, BookingStatus.IN_PROGRESS):
            with self.subTest(status=status):
                booking.status = status
                booking.save(update_fields=["status"])

                with self.assertRaises(SettlementUnavailable):
                    create_settlement(booking)

        self.assertEqual(BookingSettlement.objects.count(), 0)

    def test_a_cancelled_booking_never_earns_anything(self):
        booking = self.book()
        transition(
            booking,
            BookingStatus.CANCELLED,
            actor_type=ActorType.CUSTOMER,
            actor_id=booking.customer_id,
        )

        with self.assertRaises(SettlementUnavailable):
            create_settlement(booking)

        self.assertEqual(BookingSettlement.objects.count(), 0)

    def test_cancelling_a_booking_creates_nothing_by_itself(self):
        booking = self.book()
        transition(
            booking,
            BookingStatus.CANCELLED,
            actor_type=ActorType.CUSTOMER,
            actor_id=booking.customer_id,
        )

        self.assertEqual(BookingSettlement.objects.count(), 0)

    @override_settings(PLATFORM_COMMISSION={"RATE_BPS": 0})
    def test_a_zero_rate_gives_the_provider_the_whole_booking(self):
        booking = self.book()
        complete_booking(booking)

        settlement = BookingSettlement.objects.get(booking=booking)
        self.assertEqual(settlement.commission_amount_kobo, 0)
        self.assertEqual(settlement.provider_amount_kobo, DEFAULT_PRICE_KOBO)


class SettlementUniquenessTests(TestCase):
    def setUp(self):
        self.setup = earning_setup()
        self.settlement = earn(self.setup)
        self.booking = self.settlement.booking

    def test_calling_create_again_returns_the_same_row(self):
        again = create_settlement(self.booking)

        self.assertEqual(again.pk, self.settlement.pk)
        self.assertEqual(BookingSettlement.objects.count(), 1)

    def test_a_replayed_completion_does_not_settle_twice(self):
        # A retried confirm arrives at a booking that is already COMPLETED, so the
        # lifecycle refuses the move and the settlement is never reached.
        from apps.bookings.services import IllegalTransition

        with self.assertRaises(IllegalTransition):
            transition(
                self.booking,
                BookingStatus.COMPLETED,
                actor_type=ActorType.CUSTOMER,
                actor_id=self.booking.customer_id,
            )

        self.assertEqual(BookingSettlement.objects.filter(booking=self.booking).count(), 1)

    def test_the_database_refuses_a_second_settlement_for_one_booking(self):
        # The final protection, independent of anything the service layer checks.
        with self.assertRaises(IntegrityError), transaction.atomic():
            BookingSettlement.objects.create(
                booking=self.booking,
                provider=self.setup["provider"],
                gross_amount_kobo=1,
                commission_amount_kobo=0,
                provider_amount_kobo=1,
                commission_rate_bps=0,
            )


class SettlementImmutabilityTests(TestCase):
    """A settled amount is history, and history does not move."""

    def setUp(self):
        self.setup = earning_setup()
        self.settlement = earn(self.setup)

    def test_raising_the_catalog_price_afterwards_changes_nothing(self):
        service = self.setup["service"]
        service.base_price_kobo = DEFAULT_PRICE_KOBO * 10
        service.save(update_fields=["base_price_kobo"])

        self.settlement.refresh_from_db()
        self.assertEqual(self.settlement.gross_amount_kobo, DEFAULT_PRICE_KOBO)
        self.assertEqual(self.settlement.provider_amount_kobo, 1_600_000)

    def test_a_provider_price_override_afterwards_changes_nothing(self):
        offering = self.setup["provider"].offered_services.get()
        offering.price_override_kobo = 1
        offering.save(update_fields=["price_override_kobo"])

        self.settlement.refresh_from_db()
        self.assertEqual(self.settlement.gross_amount_kobo, DEFAULT_PRICE_KOBO)

    @override_settings(PLATFORM_COMMISSION={"RATE_BPS": 9_000})
    def test_changing_the_commission_rate_afterwards_changes_nothing(self):
        self.settlement.refresh_from_db()

        self.assertEqual(self.settlement.commission_rate_bps, 2_000)
        self.assertEqual(self.settlement.commission_amount_kobo, 400_000)

    @override_settings(PLATFORM_COMMISSION={"RATE_BPS": 5_000})
    def test_a_later_booking_uses_the_new_rate_while_the_old_one_keeps_its_own(self):
        second = earn(earning_setup(slug="deep-clean"))

        self.settlement.refresh_from_db()
        self.assertEqual(self.settlement.commission_rate_bps, 2_000)
        self.assertEqual(second.commission_rate_bps, 5_000)

    def test_the_booking_behind_a_settlement_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.settlement.booking.delete()


class SettlementConstraintTests(TestCase):
    """What the database refuses, regardless of what wrote it."""

    def setUp(self):
        self.setup = earning_setup(slug="constraint-clean")
        service = make_priced_service(slug="constraint-clean")
        booking = create_booking(
            customer=self.setup["customer"],
            service=service,
            address=self.setup["address"],
            details=VALID_CLEANING_DETAILS,
        )
        accept_first_offer(booking, self.setup["provider"])
        booking.refresh_from_db()
        self.booking = complete_booking(booking)
        BookingSettlement.objects.all().delete()

    def build(self, **overrides):
        defaults = {
            "booking": self.booking,
            "provider": self.setup["provider"],
            "gross_amount_kobo": 1_000_000,
            "commission_amount_kobo": 200_000,
            "provider_amount_kobo": 800_000,
            "commission_rate_bps": 2_000,
        }
        return BookingSettlement.objects.create(**{**defaults, **overrides})

    def test_the_fixture_itself_is_valid(self):
        self.assertIsNotNone(self.build().pk)

    def test_amounts_that_do_not_balance_are_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.build(provider_amount_kobo=900_000)

    def test_a_negative_gross_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.build(gross_amount_kobo=-1, commission_amount_kobo=0, provider_amount_kobo=-1)

    def test_a_negative_commission_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.build(commission_amount_kobo=-1, provider_amount_kobo=1_000_001)

    def test_a_negative_provider_amount_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.build(commission_amount_kobo=1_000_001, provider_amount_kobo=-1)

    def test_commission_larger_than_the_booking_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.build(
                gross_amount_kobo=1_000_000,
                commission_amount_kobo=1_000_001,
                provider_amount_kobo=-1,
            )

    def test_a_rate_above_the_whole_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.build(commission_rate_bps=10_001)


class BookingPriceSnapshotTests(TestCase):
    """The gross amount's source: the booking, fixed when it was requested."""

    def test_a_broadcast_booking_takes_the_catalog_price(self):
        setup = earning_setup(price_kobo=750_000, slug="snapshot-clean")

        booking = create_booking(
            customer=setup["customer"],
            service=setup["service"],
            address=setup["address"],
            details=VALID_CLEANING_DETAILS,
        )

        self.assertEqual(booking.total_kobo, 750_000)

    def test_naming_a_provider_takes_that_provider_price(self):
        service = make_priced_service(500_000, slug="override-clean")
        customer = make_customer()
        address = make_address(customer)
        provider = make_provider_offering(service)
        offering = provider.offered_services.get()
        offering.price_override_kobo = 900_000
        offering.save(update_fields=["price_override_kobo"])

        booking = create_booking(
            customer=customer,
            service=service,
            address=address,
            provider=provider,
            details=VALID_CLEANING_DETAILS,
        )

        self.assertEqual(booking.total_kobo, 900_000)

    def test_the_price_does_not_move_when_the_catalog_does(self):
        setup = earning_setup(price_kobo=750_000, slug="frozen-clean")
        booking = create_booking(
            customer=setup["customer"],
            service=setup["service"],
            address=setup["address"],
            details=VALID_CLEANING_DETAILS,
        )

        setup["service"].base_price_kobo = 9_999_999
        setup["service"].save(update_fields=["base_price_kobo"])
        booking.refresh_from_db()

        self.assertEqual(booking.total_kobo, 750_000)
