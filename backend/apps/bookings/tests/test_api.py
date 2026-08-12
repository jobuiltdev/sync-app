from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.bookings.state import BookingStatus
from apps.bookings.tests.factories import (
    PASSWORD,
    VALID_CLEANING_DETAILS,
    full_setup,
    make_address,
    make_customer,
    make_provider_offering,
)
from apps.catalog.tests.factories import make_service

URL = "/api/v1/customer/bookings/"
JOBS_URL = "/api/v1/provider/bookings/"


def payload(data: dict, **overrides) -> dict:
    body = {
        "service_slug": data["service"].slug,
        "provider_id": str(data["provider"].id),
        "address_id": str(data["address"].id),
        "details": VALID_CLEANING_DETAILS,
    }
    body.update(overrides)
    return body


class BookingCreationPolicyTests(APITestCase):
    def setUp(self):
        self.data = full_setup()

    def test_unauthenticated_creation_is_refused(self):
        response = self.client.post(URL, payload(self.data), format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")

    def test_a_verified_phone_can_book(self):
        self.client.force_authenticate(self.data["customer"])

        response = self.client.post(URL, payload(self.data), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], BookingStatus.ASSIGNED)

    def test_an_unverified_phone_cannot_book(self):
        self.data["customer"].phone_verified_at = None
        self.data["customer"].save(update_fields=["phone_verified_at"])
        self.client.force_authenticate(self.data["customer"])

        response = self.client.post(URL, payload(self.data), format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"]["code"], "PHONE_VERIFICATION_REQUIRED")

    def test_a_refused_booking_persists_nothing(self):
        self.data["customer"].phone_verified_at = None
        self.data["customer"].save(update_fields=["phone_verified_at"])
        self.client.force_authenticate(self.data["customer"])

        self.client.post(URL, payload(self.data), format="json")

        self.assertEqual(Booking.objects.count(), 0)

    def test_the_refusal_tells_the_app_where_to_send_the_user(self):
        self.data["customer"].phone_verified_at = None
        self.data["customer"].save(update_fields=["phone_verified_at"])
        self.client.force_authenticate(self.data["customer"])

        response = self.client.post(URL, payload(self.data), format="json")

        details = response.data["error"]["details"]
        self.assertEqual(details["unmet"], ["PHONE_VERIFIED"])
        self.assertIn("action", details["next_step"])

    def test_an_unverified_email_does_not_block_booking(self):
        self.assertIsNone(self.data["customer"].email_verified_at)
        self.client.force_authenticate(self.data["customer"])

        response = self.client.post(URL, payload(self.data), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_browsing_the_catalog_never_requires_verification(self):
        response = self.client.get("/api/v1/catalog/categories/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_managing_addresses_never_requires_verification(self):
        unverified = make_customer("new@example.com", phone_verified=False)
        self.client.force_authenticate(unverified)

        response = self.client.post(
            "/api/v1/customer/addresses/",
            {"street_address": "1 Road", "landmark": "By the mast", "state": "LAGOS"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class BookingCreationValidationTests(APITestCase):
    def setUp(self):
        self.data = full_setup()
        self.client.force_authenticate(self.data["customer"])

    def test_stores_the_submitted_request_payload(self):
        response = self.client.post(URL, payload(self.data), format="json")

        booking = Booking.objects.get(id=response.data["id"])
        self.assertEqual(booking.details["bedrooms"], 3)
        self.assertEqual(booking.details["property_type"], "APARTMENT")

    def test_records_the_spec_the_payload_was_validated_against(self):
        response = self.client.post(URL, payload(self.data), format="json")

        self.assertEqual(response.data["spec_key"], "cleaning")

    def test_rejects_a_payload_missing_a_required_field(self):
        details = {k: v for k, v in VALID_CLEANING_DETAILS.items() if k != "bedrooms"}

        response = self.client.post(URL, payload(self.data, details=details), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("details", response.data["error"]["details"]["fields"])

    def test_rejects_a_field_of_the_wrong_type(self):
        response = self.client.post(
            URL,
            payload(self.data, details={**VALID_CLEANING_DETAILS, "bedrooms": "three"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_an_invalid_choice(self):
        response = self.client.post(
            URL,
            payload(self.data, details={**VALID_CLEANING_DETAILS, "property_type": "CASTLE"}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_payload_valid_for_another_service_is_rejected(self):
        # The point of per-service specs: a laundry payload is not a cleaning
        # request, however well formed it is on its own terms.
        laundry_details = {"item_count": 12, "wash_type": "DRY_CLEAN", "express": False}

        response = self.client.post(URL, payload(self.data, details=laundry_details), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Booking.objects.count(), 0)

    def test_rejects_details_that_are_not_an_object(self):
        response = self.client.post(URL, payload(self.data, details="nonsense"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_an_unknown_service(self):
        response = self.client.post(
            URL, payload(self.data, service_slug="teleportation"), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_an_inactive_service(self):
        retired = make_service(slug="retired", is_active=False)

        response = self.client.post(
            URL, payload(self.data, service_slug=retired.slug), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejects_a_provider_who_does_not_offer_the_service(self):
        other_service = make_service(slug="deep-clean")
        stranger = make_provider_offering(other_service, email="stranger@example.com")

        response = self.client.post(
            URL, payload(self.data, provider_id=str(stranger.id)), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "PROVIDER_NOT_AVAILABLE")

    def test_accepts_a_scheduled_time(self):
        when = (timezone.now() + timezone.timedelta(days=2)).isoformat()

        response = self.client.post(URL, payload(self.data, scheduled_for=when), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(response.data["scheduled_for"])


class BookingAddressOwnershipTests(APITestCase):
    def setUp(self):
        self.data = full_setup()
        self.stranger = User.objects.create_user(email="chidi@example.com", password=PASSWORD)
        self.their_address = make_address(self.stranger)
        self.client.force_authenticate(self.data["customer"])

    def test_another_customers_address_cannot_be_used(self):
        response = self.client.post(
            URL, payload(self.data, address_id=str(self.their_address.id)), format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("address_id", response.data["error"]["details"]["fields"])

    def test_no_booking_is_created_from_a_rejected_address(self):
        self.client.post(
            URL, payload(self.data, address_id=str(self.their_address.id)), format="json"
        )

        self.assertEqual(Booking.objects.count(), 0)

    def test_the_snapshot_is_returned_with_the_booking(self):
        response = self.client.post(URL, payload(self.data), format="json")

        address = response.data["address"]
        self.assertEqual(address["landmark"], "Opposite Eko Hotel gate")
        self.assertEqual(address["state"], "LAGOS")


class BookingAccessTests(APITestCase):
    def setUp(self):
        self.data = full_setup()
        self.client.force_authenticate(self.data["customer"])
        self.booking_id = self.client.post(URL, payload(self.data), format="json").data["id"]

        self.stranger = make_customer("chidi@example.com")

    def test_a_customer_lists_only_their_own_bookings(self):
        self.client.force_authenticate(self.stranger)

        response = self.client.get(URL)

        self.assertEqual(response.data["count"], 0)

    def test_a_customer_sees_their_own_bookings(self):
        response = self.client.get(URL)

        self.assertEqual(response.data["count"], 1)

    def test_another_customers_booking_is_a_404_not_a_403(self):
        self.client.force_authenticate(self.stranger)

        response = self.client.get(f"{URL}{self.booking_id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_nonexistent_booking_is_a_404(self):
        response = self.client.get(f"{URL}00000000-0000-4000-8000-000000000000/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_listing_requires_authentication(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_the_detail_carries_the_history(self):
        response = self.client.get(f"{URL}{self.booking_id}/")

        self.assertEqual(len(response.data["events"]), 1)
        self.assertEqual(response.data["events"][0]["to_status"], BookingStatus.ASSIGNED)

    def test_the_detail_advertises_what_can_happen_next(self):
        response = self.client.get(f"{URL}{self.booking_id}/")

        self.assertIn(BookingStatus.EN_ROUTE, response.data["allowed_transitions"])

    def test_a_provider_sees_the_job_assigned_to_them(self):
        self.client.force_authenticate(self.data["provider"].user)

        response = self.client.get(JOBS_URL)

        self.assertEqual(response.data["count"], 1)

    def test_a_provider_does_not_see_another_providers_jobs(self):
        other = make_provider_offering(self.data["service"], email="other@example.com")
        self.client.force_authenticate(other.user)

        response = self.client.get(JOBS_URL)

        self.assertEqual(response.data["count"], 0)

    def test_an_account_with_no_provider_profile_is_told_so(self):
        self.client.force_authenticate(self.stranger)

        response = self.client.get(JOBS_URL)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "PROVIDER_PROFILE_NOT_FOUND")


class BookingActionTests(APITestCase):
    def setUp(self):
        self.data = full_setup()
        self.client.force_authenticate(self.data["customer"])
        self.booking_id = self.client.post(URL, payload(self.data), format="json").data["id"]
        self.provider_user = self.data["provider"].user

    def as_provider(self):
        self.client.force_authenticate(self.provider_user)

    def test_a_client_cannot_submit_an_arbitrary_status(self):
        # There is no endpoint that accepts a status. Every move is a named action.
        response = self.client.patch(
            f"{URL}{self.booking_id}/", {"status": BookingStatus.COMPLETED}, format="json"
        )

        self.assertIn(
            response.status_code,
            {status.HTTP_405_METHOD_NOT_ALLOWED, status.HTTP_404_NOT_FOUND},
        )
        self.assertEqual(Booking.objects.get(id=self.booking_id).status, BookingStatus.ASSIGNED)

    def test_a_customer_can_cancel(self):
        response = self.client.post(f"{URL}{self.booking_id}/cancel/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], BookingStatus.CANCELLED)

    def test_a_cancellation_reason_is_recorded_in_the_history(self):
        self.client.post(
            f"{URL}{self.booking_id}/cancel/", {"reason": "No longer needed"}, format="json"
        )

        booking = Booking.objects.get(id=self.booking_id)
        self.assertEqual(booking.events.latest("created_at").reason, "No longer needed")

    def test_a_customer_cannot_cancel_another_customers_booking(self):
        self.client.force_authenticate(make_customer("chidi@example.com"))

        response = self.client.post(f"{URL}{self.booking_id}/cancel/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Booking.objects.get(id=self.booking_id).status, BookingStatus.ASSIGNED)

    def test_a_customer_cannot_confirm_before_the_provider_finishes(self):
        response = self.client.post(f"{URL}{self.booking_id}/confirm/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"]["code"], "ILLEGAL_TRANSITION")

    def test_the_full_lifecycle_over_the_api(self):
        self.as_provider()
        self.client.post(f"{JOBS_URL}{self.booking_id}/en-route/", {}, format="json")
        self.client.post(f"{JOBS_URL}{self.booking_id}/start/", {}, format="json")
        self.client.post(f"{JOBS_URL}{self.booking_id}/finish/", {}, format="json")

        self.client.force_authenticate(self.data["customer"])
        response = self.client.post(f"{URL}{self.booking_id}/confirm/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], BookingStatus.COMPLETED)
        self.assertIsNotNone(response.data["completed_at"])

    def test_a_provider_cannot_act_on_another_providers_job(self):
        other = make_provider_offering(self.data["service"], email="other@example.com")
        self.client.force_authenticate(other.user)

        response = self.client.post(f"{JOBS_URL}{self.booking_id}/start/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_an_illegal_transition_leaves_the_booking_alone(self):
        self.as_provider()

        self.client.post(f"{JOBS_URL}{self.booking_id}/finish/", {}, format="json")

        self.assertEqual(Booking.objects.get(id=self.booking_id).status, BookingStatus.ASSIGNED)

    def test_an_illegal_transition_reports_what_was_allowed(self):
        self.as_provider()

        response = self.client.post(f"{JOBS_URL}{self.booking_id}/finish/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("allowed_transitions", response.data["error"]["details"])

    def test_actions_require_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.post(f"{URL}{self.booking_id}/cancel/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
