from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User, VerificationChallenge
from apps.accounts.sms.base import SMSDeliveryError
from apps.accounts.sms.locmem import LocMemSMSProvider

PASSWORD = "Lagos-Rider-2026"
LOCMEM = "apps.accounts.sms.locmem.LocMemSMSProvider"
FAILING = "apps.accounts.sms.failing.FailingSMSProvider"

PHONE_URL = "/api/v1/auth/phone/"
REQUEST_URL = "/api/v1/auth/phone/verification/request/"
CONFIRM_URL = "/api/v1/auth/phone/verification/confirm/"
ME_URL = "/api/v1/auth/me/"


@override_settings(SMS_BACKEND=LOCMEM)
class VerificationApiBase(APITestCase):
    def setUp(self):
        LocMemSMSProvider.clear()
        self.user = User.objects.create_user(
            email="ada@example.com", password=PASSWORD, phone="08031234567"
        )
        self.client.force_authenticate(self.user)

    def request_code(self):
        response = self.client.post(REQUEST_URL, {}, format="json")
        sent = LocMemSMSProvider.last()
        return response, (sent.code if sent else None)


class RequestEndpointTests(VerificationApiBase):
    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.post(REQUEST_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")

    def test_issues_a_challenge(self):
        response, _ = self.request_code()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("challenge_id", response.data)
        self.assertEqual(response.data["destination"], "+2348031234567")

    def test_the_code_never_appears_in_the_response(self):
        response, code = self.request_code()

        self.assertNotIn(code, str(response.data))
        self.assertNotIn("code", response.data)
        self.assertNotIn("code_hash", response.data)

    def test_sends_through_the_provider_abstraction(self):
        self.request_code()

        self.assertEqual(len(LocMemSMSProvider.sent), 1)
        self.assertEqual(LocMemSMSProvider.last().phone, "+2348031234567")

    def test_reports_the_expiry_and_attempts_the_client_needs(self):
        response, _ = self.request_code()

        self.assertIn("expires_at", response.data)
        self.assertEqual(response.data["attempts_remaining"], 5)

    def test_an_account_without_a_phone_is_refused(self):
        self.client.force_authenticate(
            User.objects.create_user(email="nophone@example.com", password=PASSWORD)
        )

        response = self.client.post(REQUEST_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "PHONE_NOT_SET")

    def test_an_already_verified_phone_is_refused_without_sending(self):
        self.user.phone_verified_at = timezone.now()
        self.user.save()

        response = self.client.post(REQUEST_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"]["code"], "PHONE_ALREADY_VERIFIED")
        self.assertEqual(len(LocMemSMSProvider.sent), 0)

    def test_the_cooldown_is_enforced(self):
        self.request_code()

        response = self.client.post(REQUEST_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data["error"]["code"], "PHONE_VERIFICATION_COOLDOWN")
        self.assertGreater(response.data["error"]["details"]["retry_after_seconds"], 0)

    def test_the_provider_is_not_called_during_cooldown(self):
        self.request_code()
        self.client.post(REQUEST_URL, {}, format="json")

        self.assertEqual(len(LocMemSMSProvider.sent), 1)

    @override_settings(SMS_BACKEND=FAILING)
    def test_a_provider_failure_leaves_nothing_behind(self):
        # The delivery error is not caught by the API, so it surfaces as a 500
        # rather than pretending a code was sent. What matters is that the
        # transaction rolled back and nothing was left implying one was.
        with self.assertRaises(SMSDeliveryError):
            self.client.post(REQUEST_URL, {}, format="json")

        self.assertEqual(VerificationChallenge.objects.count(), 0)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)


class ConfirmEndpointTests(VerificationApiBase):
    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.post(
            CONFIRM_URL,
            {"challenge_id": "00000000-0000-4000-8000-000000000000", "code": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_the_correct_code_verifies_the_phone(self):
        issued, code = self.request_code()

        response = self.client.post(
            CONFIRM_URL,
            {"challenge_id": issued.data["challenge_id"], "code": code},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_phone_verified"])
        self.assertIsNotNone(response.data["phone_verified_at"])

    def test_me_reflects_the_new_state(self):
        issued, code = self.request_code()
        self.client.post(
            CONFIRM_URL, {"challenge_id": issued.data["challenge_id"], "code": code}, format="json"
        )

        response = self.client.get(ME_URL)

        self.assertTrue(response.data["is_phone_verified"])

    def test_a_wrong_code_is_refused_and_counts_down(self):
        issued, _ = self.request_code()

        response = self.client.post(
            CONFIRM_URL,
            {"challenge_id": issued.data["challenge_id"], "code": "000000"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INVALID_PHONE_VERIFICATION_CODE")
        self.assertEqual(response.data["error"]["details"]["attempts_remaining"], 4)

    def test_a_wrong_code_does_not_verify(self):
        issued, _ = self.request_code()

        self.client.post(
            CONFIRM_URL,
            {"challenge_id": issued.data["challenge_id"], "code": "000000"},
            format="json",
        )

        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)

    def test_attempts_are_exhausted_after_the_cap(self):
        issued, _ = self.request_code()
        payload = {"challenge_id": issued.data["challenge_id"], "code": "000000"}

        for _ in range(4):
            self.client.post(CONFIRM_URL, payload, format="json")

        response = self.client.post(CONFIRM_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data["error"]["code"], "PHONE_VERIFICATION_EXHAUSTED")

    def test_an_expired_challenge_is_refused(self):
        issued, code = self.request_code()
        VerificationChallenge.objects.filter(pk=issued.data["challenge_id"]).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        response = self.client.post(
            CONFIRM_URL, {"challenge_id": issued.data["challenge_id"], "code": code}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_410_GONE)
        self.assertEqual(response.data["error"]["code"], "PHONE_VERIFICATION_EXPIRED")

    def test_a_consumed_challenge_cannot_be_reused(self):
        issued, code = self.request_code()
        payload = {"challenge_id": issued.data["challenge_id"], "code": code}
        self.client.post(CONFIRM_URL, payload, format="json")

        response = self.client.post(CONFIRM_URL, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "VERIFICATION_CHALLENGE_NOT_FOUND")

    def test_another_users_challenge_cannot_be_used(self):
        issued, code = self.request_code()
        stranger = User.objects.create_user(
            email="chidi@example.com", password=PASSWORD, phone="08039998877"
        )
        self.client.force_authenticate(stranger)

        response = self.client.post(
            CONFIRM_URL, {"challenge_id": issued.data["challenge_id"], "code": code}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        stranger.refresh_from_db()
        self.assertIsNone(stranger.phone_verified_at)

    def test_the_request_body_cannot_declare_the_phone_verified(self):
        # There is no field anywhere that sets this. Only a correct code does.
        issued, _ = self.request_code()

        self.client.post(
            CONFIRM_URL,
            {
                "challenge_id": issued.data["challenge_id"],
                "code": "000000",
                "phone_verified": True,
                "phone_verified_at": timezone.now().isoformat(),
            },
            format="json",
        )

        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)

    def test_a_missing_code_is_a_validation_error(self):
        issued, _ = self.request_code()

        response = self.client.post(
            CONFIRM_URL, {"challenge_id": issued.data["challenge_id"]}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")


class PhoneUpdateEndpointTests(VerificationApiBase):
    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.put(PHONE_URL, {"phone": "08039998877"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_sets_a_phone_on_an_account_without_one(self):
        user = User.objects.create_user(email="nophone@example.com", password=PASSWORD)
        self.client.force_authenticate(user)

        response = self.client.put(PHONE_URL, {"phone": "0803 999 8877"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phone"], "+2348039998877")

    def test_changing_the_phone_clears_verification(self):
        issued, code = self.request_code()
        self.client.post(
            CONFIRM_URL, {"challenge_id": issued.data["challenge_id"], "code": code}, format="json"
        )

        response = self.client.put(PHONE_URL, {"phone": "08039998877"}, format="json")

        self.assertFalse(response.data["is_phone_verified"])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)

    def test_an_invalid_number_is_refused(self):
        response = self.client.put(PHONE_URL, {"phone": "0800000"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data["error"]["details"]["fields"])

    def test_a_number_belonging_to_another_account_is_refused(self):
        User.objects.create_user(email="chidi@example.com", password=PASSWORD, phone="08039998877")

        response = self.client.put(PHONE_URL, {"phone": "08039998877"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data["error"]["details"]["fields"])


@override_settings(SMS_BACKEND=LOCMEM)
class BookingGateRegressionTests(APITestCase):
    """The whole point of this work: the M3 gate must now be passable.

    Exercised through the real API, so it proves the policy and the verification
    flow agree rather than testing each in isolation.
    """

    def setUp(self):
        from apps.bookings.tests.factories import (
            VALID_CLEANING_DETAILS,
            make_address,
            make_provider_offering,
        )
        from apps.catalog.tests.factories import make_service

        LocMemSMSProvider.clear()
        self.details = VALID_CLEANING_DETAILS
        self.user = User.objects.create_user(
            email="ada@example.com", password=PASSWORD, phone="08031234567"
        )
        self.service = make_service(slug="standard-clean")
        self.provider = make_provider_offering(self.service, email="prov@example.com")
        self.address = make_address(self.user)
        self.client.force_authenticate(self.user)

    def book(self):
        return self.client.post(
            "/api/v1/customer/bookings/",
            {
                "service_slug": self.service.slug,
                "provider_id": str(self.provider.id),
                "address_id": str(self.address.id),
                "details": self.details,
            },
            format="json",
        )

    def verify_phone(self):
        issued = self.client.post(REQUEST_URL, {}, format="json")
        code = LocMemSMSProvider.last().code
        return self.client.post(
            CONFIRM_URL, {"challenge_id": issued.data["challenge_id"], "code": code}, format="json"
        )

    def test_an_unverified_customer_still_cannot_book(self):
        response = self.book()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"]["code"], "PHONE_VERIFICATION_REQUIRED")

    def test_verifying_the_phone_makes_booking_possible(self):
        self.assertEqual(self.book().status_code, status.HTTP_403_FORBIDDEN)

        self.verify_phone()

        self.assertEqual(self.book().status_code, status.HTTP_201_CREATED)

    def test_a_failed_verification_does_not_open_the_gate(self):
        issued = self.client.post(REQUEST_URL, {}, format="json")
        self.client.post(
            CONFIRM_URL,
            {"challenge_id": issued.data["challenge_id"], "code": "000000"},
            format="json",
        )

        self.assertEqual(self.book().status_code, status.HTTP_403_FORBIDDEN)

    def test_changing_the_phone_closes_the_gate_again(self):
        self.verify_phone()
        self.assertEqual(self.book().status_code, status.HTTP_201_CREATED)

        self.client.put(PHONE_URL, {"phone": "08039998877"}, format="json")

        self.assertEqual(self.book().status_code, status.HTTP_403_FORBIDDEN)
