import threading

from django.db import connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts import policy
from apps.bookings.dispatch import accept_offer
from apps.bookings.models import Booking, Offer
from apps.bookings.offers import OfferStatus
from apps.bookings.services import create_booking
from apps.bookings.state import BookingStatus
from apps.bookings.tests.factories import (
    VALID_CLEANING_DETAILS,
    make_address,
    make_customer,
    make_provider_offering,
)
from apps.catalog.tests.factories import make_service

OFFERS_URL = "/api/v1/provider/offers/"


class OfferApiSetup(APITestCase):
    def setUp(self):
        self.service = make_service(slug="standard-clean")
        self.customer = make_customer()
        self.address = make_address(self.customer)
        self.provider = make_provider_offering(self.service)
        self.booking = create_booking(
            customer=self.customer,
            service=self.service,
            provider=self.provider,
            address=self.address,
            details=VALID_CLEANING_DETAILS,
        )
        self.offer = self.booking.offers.get()
        self.client.force_authenticate(self.provider.user)

    def url(self, suffix: str = "") -> str:
        return f"{OFFERS_URL}{self.offer.id}/{suffix}"


class OfferListTests(OfferApiSetup):
    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.get(OFFERS_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")

    def test_a_provider_sees_their_own_pending_offers(self):
        response = self.client.get(OFFERS_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], str(self.offer.id))

    def test_a_provider_does_not_see_another_providers_offers(self):
        stranger = make_provider_offering(self.service)
        self.client.force_authenticate(stranger.user)

        response = self.client.get(OFFERS_URL)

        self.assertEqual(response.data["count"], 0)

    def test_the_inbox_hides_answered_offers_by_default(self):
        Offer.objects.filter(pk=self.offer.pk).update(
            status=OfferStatus.DECLINED, responded_at=timezone.now()
        )

        response = self.client.get(OFFERS_URL)

        self.assertEqual(response.data["count"], 0)

    def test_history_is_available_on_request(self):
        Offer.objects.filter(pk=self.offer.pk).update(
            status=OfferStatus.DECLINED, responded_at=timezone.now()
        )

        response = self.client.get(OFFERS_URL, {"status": "all"})

        self.assertEqual(response.data["count"], 1)

    def test_the_list_carries_what_a_provider_decides_on(self):
        row = self.client.get(OFFERS_URL).data["results"][0]

        self.assertEqual(row["service_name"], self.service.name)
        self.assertEqual(row["state"], "LAGOS")
        self.assertTrue(row["is_actionable"])

    def test_the_list_does_not_expose_the_customers_exact_address(self):
        # A provider browsing an inbox has no need for a landmark and directions
        # until they are deciding on that specific job.
        row = self.client.get(OFFERS_URL).data["results"][0]

        self.assertNotIn("landmark", row)
        self.assertNotIn("street_address", row)

    def test_an_account_without_a_provider_profile_is_told_so(self):
        self.client.force_authenticate(make_customer())

        response = self.client.get(OFFERS_URL)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "PROVIDER_PROFILE_NOT_FOUND")


class OfferDetailTests(OfferApiSetup):
    def test_returns_the_detail_with_the_address_and_request(self):
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["landmark"], "Opposite Eko Hotel gate")
        self.assertEqual(response.data["details"]["bedrooms"], 3)

    def test_another_providers_offer_is_a_404_not_a_403(self):
        stranger = make_provider_offering(self.service)
        self.client.force_authenticate(stranger.user)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_customer_cannot_read_a_provider_offer(self):
        self.client.force_authenticate(self.customer)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_an_unknown_offer_is_a_404(self):
        response = self.client.get(f"{OFFERS_URL}00000000-0000-4000-8000-000000000000/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class OfferAcceptApiTests(OfferApiSetup):
    def test_accepting_assigns_the_booking(self):
        response = self.client.post(self.url("accept/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], BookingStatus.ASSIGNED)
        self.assertEqual(response.data["provider_name"], self.provider.display_name)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.post(self.url("accept/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_customer_cannot_accept_on_a_providers_behalf(self):
        self.client.force_authenticate(self.customer)

        response = self.client.post(self.url("accept/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.MATCHING)

    def test_another_provider_cannot_accept_it(self):
        stranger = make_provider_offering(self.service)
        self.client.force_authenticate(stranger.user)

        response = self.client.post(self.url("accept/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "OFFER_NOT_FOUND")

    def test_accepting_twice_is_refused(self):
        self.client.post(self.url("accept/"), {}, format="json")

        response = self.client.post(self.url("accept/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"]["code"], "OFFER_ALREADY_RESPONDED")

    def test_accepting_after_declining_is_refused(self):
        self.client.post(self.url("decline/"), {}, format="json")

        response = self.client.post(self.url("accept/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_an_expired_offer_is_refused(self):
        Offer.objects.filter(pk=self.offer.pk).update(
            expires_at=timezone.now() - timezone.timedelta(seconds=1)
        )

        response = self.client.post(self.url("accept/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        self.assertEqual(response.data["error"]["code"], "OFFER_EXPIRED")

    def test_a_cancelled_booking_is_refused(self):
        from apps.bookings.services import transition
        from apps.bookings.state import ActorType

        transition(self.booking, BookingStatus.CANCELLED, actor_type=ActorType.CUSTOMER)

        response = self.client.post(self.url("accept/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"]["code"], "BOOKING_NO_LONGER_AVAILABLE")

    def test_there_is_no_generic_write_on_an_offer(self):
        # Every change is an explicit action; no status can be submitted.
        response = self.client.patch(self.url(), {"status": "ACCEPTED"}, format="json")

        self.assertIn(
            response.status_code,
            {status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_404_NOT_FOUND},
        )
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, OfferStatus.PENDING)


class OfferDeclineApiTests(OfferApiSetup):
    def test_declining_marks_the_offer(self):
        response = self.client.post(self.url("decline/"), {"reason": "Too far"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OfferStatus.DECLINED)
        self.assertEqual(response.data["decline_reason"], "Too far")

    def test_declining_the_only_offer_expires_the_booking(self):
        self.client.post(self.url("decline/"), {}, format="json")

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.EXPIRED)

    def test_declining_twice_is_refused(self):
        self.client.post(self.url("decline/"), {}, format="json")

        response = self.client.post(self.url("decline/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_declining_after_accepting_is_refused(self):
        self.client.post(self.url("accept/"), {}, format="json")

        response = self.client.post(self.url("decline/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_another_provider_cannot_decline_it(self):
        stranger = make_provider_offering(self.service)
        self.client.force_authenticate(stranger.user)

        response = self.client.post(self.url("decline/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.offer.refresh_from_db()
        self.assertEqual(self.offer.status, OfferStatus.PENDING)


class AcceptCapabilityTests(OfferApiSetup):
    def test_a_fully_verified_provider_may_accept(self):
        response = self.client.post(self.url("accept/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_an_unverified_email_blocks_acceptance(self):
        # Accepting is held to a higher bar than booking: a provider is going into
        # someone's home.
        user = self.provider.user
        user.email_verified_at = None
        user.save()

        response = self.client.post(self.url("accept/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"]["code"], "EMAIL_VERIFICATION_REQUIRED")

    def test_an_unverified_phone_blocks_acceptance(self):
        user = self.provider.user
        user.phone_verified_at = None
        user.save()

        response = self.client.post(self.url("accept/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"]["code"], "PHONE_VERIFICATION_REQUIRED")

    def test_neither_verified_reports_both(self):
        user = self.provider.user
        user.phone_verified_at = None
        user.email_verified_at = None
        user.save()

        response = self.client.post(self.url("accept/"), {}, format="json")

        self.assertEqual(response.data["error"]["code"], "VERIFICATION_REQUIRED")
        self.assertEqual(
            set(response.data["error"]["details"]["unmet"]),
            {"PHONE_VERIFIED", "EMAIL_VERIFIED"},
        )

    def test_a_blocked_acceptance_changes_nothing(self):
        user = self.provider.user
        user.email_verified_at = None
        user.save()

        self.client.post(self.url("accept/"), {}, format="json")

        self.booking.refresh_from_db()
        self.offer.refresh_from_db()
        self.assertEqual(self.booking.status, BookingStatus.MATCHING)
        self.assertEqual(self.offer.status, OfferStatus.PENDING)
        self.assertIsNone(self.booking.provider)

    def test_declining_does_not_require_verification(self):
        # Turning work down is not entering anybody's home.
        user = self.provider.user
        user.email_verified_at = None
        user.save()

        response = self.client.post(self.url("decline/"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_the_policy_declares_both_requirements(self):
        self.assertEqual(
            set(policy.CAPABILITY_REQUIREMENTS[policy.Capability.ACCEPT_JOB]),
            {policy.Requirement.PHONE_VERIFIED, policy.Requirement.EMAIL_VERIFIED},
        )


class ConcurrentAcceptanceTests(TransactionTestCase):
    """Two providers going for the same job at the same instant.

    A TransactionTestCase because real threads need real committed transactions;
    the usual TestCase wraps everything in one that nobody else can see.
    """

    reset_sequences = True

    def setUp(self):
        self.service = make_service(slug="standard-clean")
        self.customer = make_customer()
        self.address = make_address(self.customer)
        self.first = make_provider_offering(self.service)
        self.second = make_provider_offering(self.service)
        self.booking = create_booking(
            customer=self.customer,
            service=self.service,
            address=self.address,
            details=VALID_CLEANING_DETAILS,
        )

    def test_exactly_one_provider_wins(self):
        results: dict[str, Exception | None] = {}
        barrier = threading.Barrier(2)

        def attempt(provider, key):
            try:
                barrier.wait(timeout=10)
                offer = Offer.objects.get(booking=self.booking, provider=provider)
                with transaction.atomic():
                    accept_offer(offer.id, provider, provider.user)
                results[key] = None
            except Exception as exc:
                results[key] = exc
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=attempt, args=(self.first, "first")),
            threading.Thread(target=attempt, args=(self.second, "second")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        winners = [key for key, error in results.items() if error is None]

        self.assertEqual(len(winners), 1, f"expected one winner, got {results}")

    def test_the_booking_ends_with_one_provider_and_one_accepted_offer(self):
        barrier = threading.Barrier(2)

        def attempt(provider):
            try:
                barrier.wait(timeout=10)
                offer = Offer.objects.get(booking=self.booking, provider=provider)
                accept_offer(offer.id, provider, provider.user)
            except Exception:
                pass
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=attempt, args=(self.first,)),
            threading.Thread(target=attempt, args=(self.second,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        booking = Booking.objects.get(pk=self.booking.pk)
        accepted = Offer.objects.filter(booking=booking, status=OfferStatus.ACCEPTED)

        self.assertEqual(booking.status, BookingStatus.ASSIGNED)
        self.assertEqual(accepted.count(), 1)
        self.assertIsNotNone(booking.provider)
        self.assertEqual(booking.provider_id, accepted.get().provider_id)

    def test_no_partial_state_survives_the_race(self):
        barrier = threading.Barrier(2)

        def attempt(provider):
            try:
                barrier.wait(timeout=10)
                offer = Offer.objects.get(booking=self.booking, provider=provider)
                accept_offer(offer.id, provider, provider.user)
            except Exception:
                pass
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=attempt, args=(self.first,)),
            threading.Thread(target=attempt, args=(self.second,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)

        booking = Booking.objects.get(pk=self.booking.pk)
        # No offer is left pending, and exactly one ASSIGNED event was written.
        self.assertEqual(
            Offer.objects.filter(booking=booking, status=OfferStatus.PENDING).count(), 0
        )
        self.assertEqual(booking.events.filter(to_status=BookingStatus.ASSIGNED).count(), 1)
