from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from apps.bookings.dispatch import (
    BookingNoLongerAvailable,
    NoEligibleProviders,
    OfferExpired,
    OfferNotActionable,
    OfferNotFound,
    accept_offer,
    decline_offer,
    eligible_providers,
)
from apps.bookings.models import Booking, Offer
from apps.bookings.offers import OfferKind, OfferStatus
from apps.bookings.services import ProviderUnavailable, create_booking
from apps.bookings.state import ActorType, BookingStatus
from apps.bookings.tests.factories import (
    VALID_CLEANING_DETAILS,
    make_address,
    make_customer,
    make_provider_offering,
)
from apps.catalog.tests.factories import make_service


def book(customer, service, address, provider=None) -> Booking:
    return create_booking(
        customer=customer,
        service=service,
        provider=provider,
        address=address,
        details=VALID_CLEANING_DETAILS,
    )


class OfferSetup(TestCase):
    def setUp(self):
        self.service = make_service(slug="standard-clean")
        self.customer = make_customer()
        self.address = make_address(self.customer)
        self.provider = make_provider_offering(self.service)


class EligibilityTests(OfferSetup):
    def test_an_approved_available_covering_provider_is_eligible(self):
        self.assertIn(self.provider, eligible_providers(self.service, "LAGOS"))

    def test_an_unapproved_provider_is_not_eligible(self):
        # Approval is what gates entry to a customer's home.
        pending = make_provider_offering(self.service, approved=False)

        self.assertNotIn(pending, eligible_providers(self.service, "LAGOS"))

    def test_a_provider_not_taking_work_is_not_eligible(self):
        paused = make_provider_offering(self.service, accepting=False)

        self.assertNotIn(paused, eligible_providers(self.service, "LAGOS"))

    def test_a_provider_who_does_not_cover_the_state_is_not_eligible(self):
        elsewhere = make_provider_offering(self.service, state="KANO")

        self.assertNotIn(elsewhere, eligible_providers(self.service, "LAGOS"))

    def test_a_provider_who_stopped_offering_the_service_is_not_eligible(self):
        self.provider.offered_services.update(is_active=False)

        self.assertNotIn(self.provider, eligible_providers(self.service, "LAGOS"))

    def test_a_provider_of_a_different_service_is_not_eligible(self):
        other = make_provider_offering(make_service(slug="deep-clean"))

        self.assertNotIn(other, eligible_providers(self.service, "LAGOS"))

    def test_a_provider_is_listed_once_even_with_several_areas(self):
        self.provider.service_areas.create(state="LAGOS", lga="Ikeja")

        self.assertEqual(eligible_providers(self.service, "LAGOS").count(), 1)


class DispatchTests(OfferSetup):
    def test_a_new_booking_opens_in_matching(self):
        booking = book(self.customer, self.service, self.address, self.provider)

        self.assertEqual(booking.status, BookingStatus.MATCHING)
        self.assertIsNone(booking.provider)

    def test_naming_a_provider_creates_one_direct_offer(self):
        booking = book(self.customer, self.service, self.address, self.provider)

        offer = booking.offers.get()
        self.assertEqual(offer.provider, self.provider)
        self.assertEqual(offer.kind, OfferKind.DIRECT)
        self.assertEqual(offer.status, OfferStatus.PENDING)

    def test_omitting_a_provider_offers_the_job_to_everyone_eligible(self):
        second = make_provider_offering(self.service)
        make_provider_offering(self.service, state="KANO")

        booking = book(self.customer, self.service, self.address)

        self.assertEqual(booking.offers.count(), 2)
        self.assertEqual(
            set(booking.offers.values_list("provider", flat=True)),
            {self.provider.pk, second.pk},
        )
        self.assertTrue(all(o.kind == OfferKind.BROADCAST for o in booking.offers.all()))

    def test_a_broadcast_with_nobody_eligible_creates_no_booking(self):
        self.provider.offered_services.update(is_active=False)

        with self.assertRaises(NoEligibleProviders):
            book(self.customer, self.service, self.address)

        self.assertEqual(Booking.objects.count(), 0)

    def test_an_ineligible_named_provider_is_refused(self):
        pending = make_provider_offering(self.service, approved=False)

        with self.assertRaises(ProviderUnavailable):
            book(self.customer, self.service, self.address, pending)

        self.assertEqual(Booking.objects.count(), 0)

    def test_offers_carry_an_expiry(self):
        booking = book(self.customer, self.service, self.address, self.provider)

        self.assertGreater(booking.offers.get().expires_at, timezone.now())


class OfferModelTests(OfferSetup):
    def setUp(self):
        super().setUp()
        self.booking = book(self.customer, self.service, self.address, self.provider)
        self.offer = self.booking.offers.get()

    def test_a_provider_is_offered_a_booking_only_once(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Offer.objects.create(
                booking=self.booking,
                provider=self.provider,
                kind=OfferKind.BROADCAST,
                expires_at=timezone.now() + timedelta(minutes=10),
            )

    def test_only_one_offer_per_booking_may_be_accepted(self):
        # The invariant that makes the race safe, enforced by the database.
        second = make_provider_offering(self.service)
        other = Offer.objects.create(
            booking=self.booking,
            provider=second,
            kind=OfferKind.BROADCAST,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        Offer.objects.filter(pk=self.offer.pk).update(
            status=OfferStatus.ACCEPTED, responded_at=timezone.now()
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Offer.objects.filter(pk=other.pk).update(
                status=OfferStatus.ACCEPTED, responded_at=timezone.now()
            )

    def test_a_responded_offer_must_carry_a_timestamp(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Offer.objects.filter(pk=self.offer.pk).update(status=OfferStatus.DECLINED)

    def test_a_pending_offer_must_not_carry_a_timestamp(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Offer.objects.filter(pk=self.offer.pk).update(responded_at=timezone.now())

    def test_a_new_offer_is_pending_and_actionable(self):
        self.assertTrue(self.offer.is_pending)
        self.assertTrue(self.offer.is_actionable)
        self.assertFalse(self.offer.is_terminal)

    def test_an_expired_offer_is_not_actionable(self):
        Offer.objects.filter(pk=self.offer.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        self.offer.refresh_from_db()

        self.assertTrue(self.offer.is_expired)
        self.assertFalse(self.offer.is_actionable)

    def test_terminal_statuses_report_as_terminal(self):
        for status in [
            OfferStatus.ACCEPTED,
            OfferStatus.DECLINED,
            OfferStatus.EXPIRED,
            OfferStatus.SUPERSEDED,
        ]:
            self.offer.status = status
            self.assertTrue(self.offer.is_terminal, status)

    def test_a_provider_with_offers_cannot_be_deleted(self):
        # The offer is part of how the booking got filled and must survive.
        with self.assertRaises(ProtectedError):
            self.provider.delete()

    def test_deleting_the_booking_removes_its_offers(self):
        self.booking.events.all().delete()
        self.booking.delete()

        self.assertEqual(Offer.objects.count(), 0)


class AcceptTests(OfferSetup):
    def setUp(self):
        super().setUp()
        self.booking = book(self.customer, self.service, self.address, self.provider)
        self.offer = self.booking.offers.get()

    def accept(self, provider=None):
        provider = provider or self.provider
        return accept_offer(self.booking.offers.get(provider=provider).id, provider, provider.user)

    def test_accepting_assigns_the_booking(self):
        booking = self.accept()

        self.assertEqual(booking.status, BookingStatus.ASSIGNED)
        self.assertEqual(booking.provider, self.provider)

    def test_accepting_marks_the_offer_accepted(self):
        self.accept()

        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, OfferStatus.ACCEPTED)
        self.assertIsNotNone(self.offer.responded_at)

    def test_accepting_writes_a_status_event(self):
        self.accept()

        event = self.booking.events.latest("created_at")
        self.assertEqual(event.from_status, BookingStatus.MATCHING)
        self.assertEqual(event.to_status, BookingStatus.ASSIGNED)
        self.assertEqual(event.actor_type, ActorType.SYSTEM)
        self.assertEqual(event.metadata["provider_id"], str(self.provider.pk))

    def test_the_same_offer_cannot_be_accepted_twice(self):
        self.accept()

        with self.assertRaises(OfferNotActionable):
            self.accept()

    def test_accepting_after_declining_is_refused(self):
        decline_offer(self.offer.id, self.provider, self.provider.user)

        with self.assertRaises(OfferNotActionable):
            self.accept()

    def test_an_expired_offer_cannot_be_accepted(self):
        Offer.objects.filter(pk=self.offer.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        with self.assertRaises(OfferExpired):
            self.accept()

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.MATCHING)

    def test_an_expired_offer_is_durably_marked_expired(self):
        # The marking must survive the refusal, not be rolled back with it.
        Offer.objects.filter(pk=self.offer.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        with self.assertRaises(OfferExpired):
            self.accept()

        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, OfferStatus.EXPIRED)

    def test_another_providers_offer_cannot_be_accepted(self):
        stranger = make_provider_offering(self.service)

        with self.assertRaises(OfferNotFound):
            accept_offer(self.offer.id, stranger, stranger.user)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.MATCHING)

    def test_an_unknown_offer_id_is_refused(self):
        with self.assertRaises(OfferNotFound):
            accept_offer("00000000-0000-4000-8000-000000000000", self.provider, self.provider.user)

    def test_a_malformed_offer_id_is_refused_rather_than_crashing(self):
        with self.assertRaises(OfferNotFound):
            accept_offer("not-a-uuid", self.provider, self.provider.user)

    def test_a_cancelled_booking_cannot_be_accepted(self):
        from apps.bookings.services import transition

        transition(self.booking, BookingStatus.CANCELLED, actor_type=ActorType.CUSTOMER)

        with self.assertRaises(BookingNoLongerAvailable):
            self.accept()

    def test_losing_a_race_supersedes_the_losing_offer(self):
        second = make_provider_offering(self.service)
        Offer.objects.create(
            booking=self.booking,
            provider=second,
            kind=OfferKind.BROADCAST,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        self.accept()

        with self.assertRaises(BookingNoLongerAvailable):
            self.accept(second)

        losing = self.booking.offers.get(provider=second)
        self.assertEqual(losing.status, OfferStatus.SUPERSEDED)


class BroadcastResolutionTests(OfferSetup):
    def setUp(self):
        super().setUp()
        self.second = make_provider_offering(self.service)
        self.third = make_provider_offering(self.service)
        self.booking = book(self.customer, self.service, self.address)

    def test_every_eligible_provider_is_offered_the_job(self):
        self.assertEqual(self.booking.offers.count(), 3)

    def test_acceptance_supersedes_the_others_rather_than_declining_them(self):
        # They did nothing wrong, so their acceptance rate should not record a
        # decline for a job somebody else was quicker on.
        accept_offer(
            self.booking.offers.get(provider=self.provider).id, self.provider, self.provider.user
        )

        others = self.booking.offers.exclude(provider=self.provider)
        self.assertEqual({o.status for o in others}, {OfferStatus.SUPERSEDED})

    def test_exactly_one_offer_ends_accepted(self):
        accept_offer(
            self.booking.offers.get(provider=self.provider).id, self.provider, self.provider.user
        )

        self.assertEqual(self.booking.offers.filter(status=OfferStatus.ACCEPTED).count(), 1)


class DeclineTests(OfferSetup):
    def setUp(self):
        super().setUp()
        self.second = make_provider_offering(self.service)
        self.booking = book(self.customer, self.service, self.address)

    def offer_for(self, provider):
        return self.booking.offers.get(provider=provider)

    def test_declining_marks_only_that_offer(self):
        decline_offer(self.offer_for(self.provider).id, self.provider, self.provider.user)

        self.assertEqual(self.offer_for(self.provider).status, OfferStatus.DECLINED)
        self.assertEqual(self.offer_for(self.second).status, OfferStatus.PENDING)

    def test_declining_does_not_cancel_the_booking(self):
        decline_offer(self.offer_for(self.provider).id, self.provider, self.provider.user)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.MATCHING)

    def test_a_reason_is_recorded(self):
        decline_offer(
            self.offer_for(self.provider).id, self.provider, self.provider.user, reason="Too far"
        )

        self.assertEqual(self.offer_for(self.provider).decline_reason, "Too far")

    def test_the_same_offer_cannot_be_declined_twice(self):
        decline_offer(self.offer_for(self.provider).id, self.provider, self.provider.user)

        with self.assertRaises(OfferNotActionable):
            decline_offer(self.offer_for(self.provider).id, self.provider, self.provider.user)

    def test_declining_after_accepting_is_refused(self):
        accept_offer(self.offer_for(self.provider).id, self.provider, self.provider.user)

        with self.assertRaises(OfferNotActionable):
            decline_offer(self.offer_for(self.provider).id, self.provider, self.provider.user)

    def test_another_providers_offer_cannot_be_declined(self):
        stranger = make_provider_offering(self.service)

        with self.assertRaises(OfferNotFound):
            decline_offer(self.offer_for(self.provider).id, stranger, stranger.user)

        self.assertEqual(self.offer_for(self.provider).status, OfferStatus.PENDING)

    def test_the_last_decline_expires_the_booking(self):
        # The architecture's answer for a request nobody took.
        decline_offer(self.offer_for(self.provider).id, self.provider, self.provider.user)
        decline_offer(self.offer_for(self.second).id, self.second, self.second.user)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.EXPIRED)

    def test_expiring_writes_a_status_event(self):
        decline_offer(self.offer_for(self.provider).id, self.provider, self.provider.user)
        decline_offer(self.offer_for(self.second).id, self.second, self.second.user)

        event = self.booking.events.latest("created_at")
        self.assertEqual(event.to_status, BookingStatus.EXPIRED)
        self.assertEqual(event.actor_type, ActorType.SYSTEM)

    def test_an_expired_booking_cannot_then_be_accepted(self):
        decline_offer(self.offer_for(self.provider).id, self.provider, self.provider.user)
        decline_offer(self.offer_for(self.second).id, self.second, self.second.user)

        third = make_provider_offering(self.service)
        Offer.objects.create(
            booking=self.booking,
            provider=third,
            kind=OfferKind.BROADCAST,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        with self.assertRaises(BookingNoLongerAvailable):
            accept_offer(self.booking.offers.get(provider=third).id, third, third.user)


class LifecycleContinuityTests(OfferSetup):
    """The M3 lifecycle must still run once a provider has taken the job."""

    def test_the_full_journey_from_matching_to_completed(self):
        from apps.bookings.services import transition

        booking = book(self.customer, self.service, self.address, self.provider)
        booking = accept_offer(booking.offers.get().id, self.provider, self.provider.user)

        transition(booking, BookingStatus.EN_ROUTE, actor_type=ActorType.PROVIDER)
        transition(booking, BookingStatus.IN_PROGRESS, actor_type=ActorType.PROVIDER)
        transition(booking, BookingStatus.AWAITING_CONFIRMATION, actor_type=ActorType.PROVIDER)
        transition(booking, BookingStatus.COMPLETED, actor_type=ActorType.CUSTOMER)

        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.COMPLETED)
        self.assertIsNotNone(booking.completed_at)

    def test_the_history_records_every_step(self):
        from apps.bookings.services import transition

        booking = book(self.customer, self.service, self.address, self.provider)
        booking = accept_offer(booking.offers.get().id, self.provider, self.provider.user)
        transition(booking, BookingStatus.IN_PROGRESS, actor_type=ActorType.PROVIDER)

        self.assertEqual(
            [e.to_status for e in booking.events.all()],
            [BookingStatus.MATCHING, BookingStatus.ASSIGNED, BookingStatus.IN_PROGRESS],
        )

    def test_a_customer_may_cancel_while_still_matching(self):
        from apps.bookings.services import transition

        booking = book(self.customer, self.service, self.address, self.provider)

        transition(booking, BookingStatus.CANCELLED, actor_type=ActorType.CUSTOMER)

        self.assertEqual(booking.status, BookingStatus.CANCELLED)
