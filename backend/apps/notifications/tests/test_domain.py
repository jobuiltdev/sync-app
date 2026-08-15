"""The hooks: what the marketplace actually tells people, and to whom.

Every test here drives real domain services rather than calling `notify`. A test
that called the notification service directly would prove the notification service
works and say nothing about whether a booking ever triggers one, which is the part
that breaks.

The second half is the isolation. A notification is a side effect: it must never
be able to fail a booking, a payment or a payout, and those tests break the
notification layer on purpose to prove it.
"""

from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase, override_settings

from apps.bookings.dispatch import accept_offer
from apps.bookings.offers import Offer, OfferStatus
from apps.bookings.services import create_booking, transition
from apps.bookings.state import ActorType, BookingStatus
from apps.bookings.tasks import expire_stale_offers
from apps.bookings.tests.factories import (
    VALID_CLEANING_DETAILS,
    accept_first_offer,
    make_address,
    make_customer,
    make_provider_offering,
)
from apps.catalog.tests.factories import make_service
from apps.notifications.events import EventType
from apps.notifications.models import Notification
from apps.notifications.tests.factories import events_for, verify_channels
from apps.payments import services as payment_domain
from apps.payments.gateways.base import PaymentState
from apps.payments.payouts import PayoutStatus
from apps.payments.tests.factories import (
    DEFAULT_PRICE_KOBO,
    complete_booking,
    make_destination,
    pay_booking,
)


def notifications_of(event_type: str):
    return Notification.objects.filter(event_type=event_type)


class MarketplaceSetup(TestCase):
    """A customer and a provider who can both actually be reached."""

    def setUp(self):
        self.service = make_service(slug="standard-clean", base_price_kobo=DEFAULT_PRICE_KOBO)
        self.customer = verify_channels(make_customer())
        self.address = make_address(self.customer)
        self.provider = make_provider_offering(self.service)
        verify_channels(self.provider.user)

    def book(self):
        return create_booking(
            customer=self.customer,
            service=self.service,
            address=self.address,
            details=VALID_CLEANING_DETAILS,
        )


class BookingEventTests(MarketplaceSetup):
    def test_a_customer_is_told_their_booking_was_taken(self):
        booking = self.book()
        accept_first_offer(booking, self.provider)

        self.assertIn(EventType.BOOKING_CREATED, events_for(self.customer))
        self.assertIn(EventType.PROVIDER_ASSIGNED, events_for(self.customer))

    def test_the_lifecycle_is_reported_as_it_happens(self):
        booking = self.book()
        accept_first_offer(booking, self.provider)
        booking.refresh_from_db()
        pay_booking(booking)
        complete_booking(booking)

        told = events_for(self.customer)

        self.assertIn(EventType.BOOKING_IN_PROGRESS, told)
        self.assertIn(EventType.BOOKING_AWAITING_CONFIRMATION, told)
        self.assertIn(EventType.BOOKING_COMPLETED, told)

    def test_a_status_is_reported_once_however_often_it_is_announced(self):
        """Two workers, a retried request, a replayed webhook: one message.

        The lifecycle already refuses a repeated transition, so the announcement
        is driven directly here. The guarantee has to hold on its own rather than
        by relying on the guard above it.
        """
        from apps.notifications import service as notifications

        booking = self.book()
        accept_first_offer(booking, self.provider)
        booking.refresh_from_db()

        transition(
            booking,
            BookingStatus.EN_ROUTE,
            actor_type=ActorType.PROVIDER,
            actor_id=self.provider.pk,
        )
        notifications.booking_status_changed(booking, BookingStatus.EN_ROUTE)

        self.assertEqual(notifications_of(EventType.BOOKING_EN_ROUTE).count(), 1)

    def test_an_internal_status_is_reported_to_nobody(self):
        """MATCHING and EXPIRED are bookkeeping, not news."""
        booking = self.book()
        before = Notification.objects.count()

        transition(
            booking,
            BookingStatus.EXPIRED,
            actor_type=ActorType.SYSTEM,
            reason="nobody took it",
        )

        self.assertEqual(Notification.objects.count(), before)

    def test_a_cancelled_job_tells_the_provider_not_the_customer(self):
        """The customer cancelled it. Telling them so reads as inattention."""
        booking = self.book()
        accept_first_offer(booking, self.provider)
        booking.refresh_from_db()

        transition(
            booking,
            BookingStatus.CANCELLED,
            actor_type=ActorType.CUSTOMER,
            actor_id=self.customer.pk,
        )

        self.assertIn(EventType.JOB_CANCELLED, events_for(self.provider.user))
        self.assertNotIn(EventType.JOB_CANCELLED, events_for(self.customer))

    def test_a_booking_cancelled_before_anybody_took_it_tells_nobody(self):
        booking = self.book()

        transition(
            booking,
            BookingStatus.CANCELLED,
            actor_type=ActorType.CUSTOMER,
            actor_id=self.customer.pk,
        )

        self.assertEqual(notifications_of(EventType.JOB_CANCELLED).count(), 0)


class OfferEventTests(MarketplaceSetup):
    def test_every_offered_provider_is_told(self):
        second = make_provider_offering(self.service)
        verify_channels(second.user)

        self.book()

        self.assertIn(EventType.OFFER_RECEIVED, events_for(self.provider.user))
        self.assertIn(EventType.OFFER_RECEIVED, events_for(second.user))

    def test_an_offer_never_carries_the_street_address(self):
        """A provider deciding whether to take a job needs roughly where it is.

        The address is theirs once they have accepted and not before, and a
        broadcast offer goes to everybody in the state.
        """
        with (
            patch("apps.notifications.tasks.deliver_notification.delay") as delay,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.book()

        payloads = str([call.args[1] for call in delay.call_args_list])

        self.assertIn("Victoria Island", payloads)
        self.assertNotIn("Adeola Odeku", payloads)
        self.assertNotIn("Blue gate", payloads)

    def test_the_winner_and_the_losers_are_told_different_things(self):
        second = make_provider_offering(self.service)
        verify_channels(second.user)

        booking = self.book()
        offer = Offer.objects.filter(booking=booking, provider=self.provider).get()
        accept_offer(offer.pk, self.provider, self.provider.user)

        self.assertIn(EventType.OFFER_ACCEPTED, events_for(self.provider.user))
        self.assertIn(EventType.OFFER_SUPERSEDED, events_for(second.user))
        self.assertNotIn(EventType.OFFER_ACCEPTED, events_for(second.user))

    def test_a_lapsed_offer_is_reported_as_expired(self):
        booking = self.book()
        Offer.objects.filter(booking=booking).update(
            expires_at=booking.created_at.replace(year=2020)
        )

        expire_stale_offers()

        self.assertIn(EventType.OFFER_EXPIRED, events_for(self.provider.user))


class PaymentEventTests(MarketplaceSetup):
    def setUp(self):
        super().setUp()
        self.booking = self.book()
        accept_first_offer(self.booking, self.provider)
        self.booking.refresh_from_db()

    def test_a_successful_payment_is_confirmed_to_the_customer(self):
        pay_booking(self.booking)

        self.assertIn(EventType.PAYMENT_SUCCEEDED, events_for(self.customer))

    def test_a_failed_payment_is_reported_to_the_customer(self):
        pay_booking(self.booking, state=PaymentState.FAILED)

        self.assertIn(EventType.PAYMENT_FAILED, events_for(self.customer))

    def test_a_payment_that_did_not_move_tells_nobody(self):
        """A late webhook about a payment that already succeeded is not news."""
        pay_booking(self.booking)
        before = Notification.objects.count()

        pay_booking(self.booking)

        self.assertEqual(Notification.objects.count(), before)


class EarningsEventTests(MarketplaceSetup):
    def test_a_provider_is_told_when_money_becomes_available(self):
        booking = self.book()
        accept_first_offer(booking, self.provider)
        booking.refresh_from_db()
        pay_booking(booking)
        complete_booking(booking)

        self.assertIn(EventType.EARNINGS_AVAILABLE, events_for(self.provider.user))

    def test_the_amount_told_is_their_share_and_not_the_total(self):
        booking = self.book()
        accept_first_offer(booking, self.provider)
        booking.refresh_from_db()
        pay_booking(booking)

        with (
            patch("apps.notifications.tasks.deliver_notification.delay") as delay,
            self.captureOnCommitCallbacks(execute=True),
        ):
            complete_booking(booking)

        earnings = [
            call.args[1]
            for call in delay.call_args_list
            if "amount_kobo" in call.args[1] and call.args[1].get("reference")
        ]
        settlement = payment_domain.create_settlement(booking)

        self.assertTrue(
            any(payload["amount_kobo"] == settlement.provider_amount_kobo for payload in earnings)
        )
        self.assertNotEqual(settlement.provider_amount_kobo, settlement.gross_amount_kobo)


class PayoutEventTests(MarketplaceSetup):
    def setUp(self):
        super().setUp()
        booking = self.book()
        accept_first_offer(booking, self.provider)
        booking.refresh_from_db()
        pay_booking(booking)
        complete_booking(booking)
        make_destination(self.provider)

    def request(self):
        return payment_domain.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=100_000
        )

    def test_a_request_is_acknowledged(self):
        self.request()

        self.assertIn(EventType.PAYOUT_REQUESTED, events_for(self.provider.user))

    def test_a_replayed_request_is_acknowledged_once(self):
        payment_domain.request_payout(
            provider=self.provider,
            actor=self.provider.user,
            amount_kobo=100_000,
            idempotency_key="same-key",
        )
        payment_domain.request_payout(
            provider=self.provider,
            actor=self.provider.user,
            amount_kobo=100_000,
            idempotency_key="same-key",
        )

        self.assertEqual(notifications_of(EventType.PAYOUT_REQUESTED).count(), 1)

    def test_every_payout_outcome_is_reported(self):
        payout = self.request()

        payment_domain.transition_payout(
            payout, PayoutStatus.PROCESSING, actor_type=ActorType.SYSTEM
        )
        payment_domain.transition_payout(payout, PayoutStatus.PAID, actor_type=ActorType.SYSTEM)

        told = events_for(self.provider.user)

        self.assertIn(EventType.PAYOUT_PROCESSING, told)
        self.assertIn(EventType.PAYOUT_PAID, told)

    def test_a_failure_is_reported(self):
        payout = self.request()

        payment_domain.transition_payout(
            payout,
            PayoutStatus.FAILED,
            actor_type=ActorType.SYSTEM,
            reason="ACCOUNT DORMANT",
        )

        self.assertIn(EventType.PAYOUT_FAILED, events_for(self.provider.user))

    def test_cancelling_your_own_payout_tells_you_nothing(self):
        payout = self.request()
        before = Notification.objects.count()

        payment_domain.transition_payout(
            payout, PayoutStatus.CANCELLED, actor_type=ActorType.PROVIDER
        )

        self.assertEqual(Notification.objects.count(), before)


@override_settings(
    SMS_BACKEND="apps.accounts.sms.failing.FailingSMSProvider",
    # Declared, not inherited. The last test here needs delivery to actually run
    # in this process against that failing provider; queued to a broker with no
    # worker it would assert on nothing.
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class DomainIsolationTests(MarketplaceSetup):
    """The rule the whole design exists to hold.

    A notification is a side effect. Every one of these breaks the notification
    layer in a different way and asserts that the money and the lifecycle are
    entirely unaffected.
    """

    def test_a_booking_survives_the_notification_layer_failing(self):
        with patch(
            "apps.notifications.service._notify",
            side_effect=DatabaseError("the notifications table is gone"),
        ):
            booking = self.book()

        self.assertEqual(booking.status, BookingStatus.MATCHING)
        self.assertEqual(Notification.objects.count(), 0)

    def test_offers_are_still_dispatched_when_nobody_can_be_told(self):
        with patch(
            "apps.notifications.service._notify", side_effect=RuntimeError("messaging is down")
        ):
            booking = self.book()

        self.assertEqual(
            Offer.objects.filter(booking=booking, status=OfferStatus.PENDING).count(), 1
        )

    def test_a_job_is_still_accepted_when_the_message_cannot_be_recorded(self):
        booking = self.book()

        with patch(
            "apps.notifications.service._notify", side_effect=RuntimeError("messaging is down")
        ):
            accept_first_offer(booking, self.provider)

        booking.refresh_from_db()

        self.assertEqual(booking.status, BookingStatus.ASSIGNED)
        self.assertEqual(booking.provider_id, self.provider.pk)

    def test_a_settlement_is_still_written_when_the_message_cannot_be_recorded(self):
        booking = self.book()
        accept_first_offer(booking, self.provider)
        booking.refresh_from_db()
        pay_booking(booking)

        with patch(
            "apps.notifications.service._notify", side_effect=RuntimeError("messaging is down")
        ):
            complete_booking(booking)

        settlement = payment_domain.create_settlement(booking)

        self.assertEqual(settlement.gross_amount_kobo, DEFAULT_PRICE_KOBO)

    def test_an_sms_provider_that_always_fails_does_not_reach_the_domain(self):
        """The whole delivery path runs, against a provider that refuses.

        Nothing about that may surface in the booking, which is the arrangement
        that makes calling `notify` from inside domain code safe.
        """
        with self.captureOnCommitCallbacks(execute=True):
            booking = self.book()

        self.assertEqual(booking.status, BookingStatus.MATCHING)


class VendorIsolationTests(TestCase):
    """No vendor may be reachable from lifecycle code.

    The architectural constraint, asserted rather than reviewed. A future edit
    that reaches for Termii inside a booking service fails here.
    """

    DOMAIN_MODULES = [
        "apps/bookings/services.py",
        "apps/bookings/dispatch.py",
        "apps/bookings/tasks.py",
        "apps/payments/services.py",
        "apps/payments/payment_services.py",
        "apps/payments/execution.py",
    ]

    FORBIDDEN = ["termii", "resend", "send_mail", "EmailMessage", "send_sms", "get_sms_provider"]

    def test_no_domain_module_touches_a_vendor(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]

        for name in self.DOMAIN_MODULES:
            source = (root / name).read_text(encoding="utf-8")
            for forbidden in self.FORBIDDEN:
                with self.subTest(module=name, forbidden=forbidden):
                    self.assertNotIn(forbidden, source)
