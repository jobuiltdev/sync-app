"""The customer payment endpoints, and who may see what.

The rule these exist to hold: a client cannot assert that a payment succeeded.
Not by sending a status, not by patching a record, not by any route at all.
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.bookings.services import create_booking
from apps.bookings.state import BookingStatus
from apps.bookings.tests.factories import VALID_CLEANING_DETAILS, accept_first_offer
from apps.payments.gateways.fake import FakeGateway
from apps.payments.intents import PaymentIntent, PaymentStatus
from apps.payments.tests.factories import DEFAULT_PRICE_KOBO, earning_setup

PAYMENTS = "/api/v1/customer/payments/"
BANKS = "/api/v1/provider/banks/"
DESTINATION = "/api/v1/provider/payout-destination/"


def error_code(response) -> str:
    return response.json()["error"]["code"]


class PaymentAPITestCase(APITestCase):
    def setUp(self):
        FakeGateway.clear()
        self.setup = earning_setup()
        self.customer = self.setup["customer"]
        self.booking = self.book()
        self.client.force_authenticate(self.customer)

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

    def pay_url(self, booking=None) -> str:
        return f"/api/v1/customer/bookings/{(booking or self.booking).pk}/pay/"

    def start(self, **headers):
        return self.client.post(self.pay_url(), {}, format="json", **headers)


class PaymentInitializationAPITests(PaymentAPITestCase):
    def test_a_customer_can_start_paying_for_their_booking(self):
        response = self.start()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertEqual(body["amount_kobo"], DEFAULT_PRICE_KOBO)
        self.assertEqual(body["status"], PaymentStatus.INITIALIZED)
        self.assertTrue(body["authorization_url"])

    def test_the_response_carries_no_provider_credential(self):
        body = self.client.post(self.pay_url(), {}, format="json").content.decode()

        for secret in ("secret", "sk_test", "sk_live", "api_key", "apiKey"):
            self.assertNotIn(secret, body)

    def test_money_is_returned_as_integer_kobo(self):
        body = self.start().json()

        self.assertIsInstance(body["amount_kobo"], int)
        self.assertEqual(body["currency"], "NGN")

    def test_the_same_idempotency_key_starts_one_payment(self):
        first = self.start(HTTP_IDEMPOTENCY_KEY="tap-once")
        second = self.start(HTTP_IDEMPOTENCY_KEY="tap-once")

        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(PaymentIntent.objects.count(), 1)
        self.assertEqual(len(FakeGateway.initialized), 1)

    def test_paying_for_somebody_else_booking_is_a_not_found(self):
        stranger = earning_setup(slug="stranger-clean")["customer"]
        self.client.force_authenticate(stranger)

        response = self.client.post(self.pay_url(), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(PaymentIntent.objects.count(), 0)

    def test_a_cancelled_booking_cannot_be_paid_for(self):
        from apps.bookings.services import transition
        from apps.bookings.state import ActorType

        transition(
            self.booking,
            BookingStatus.CANCELLED,
            actor_type=ActorType.CUSTOMER,
            actor_id=self.customer.id,
        )

        response = self.start()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(error_code(response), "BOOKING_NOT_PAYABLE")

    def test_paying_is_not_public(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.start().status_code, status.HTTP_401_UNAUTHORIZED)


class PaymentVerificationAPITests(PaymentAPITestCase):
    def setUp(self):
        super().setUp()
        self.intent = PaymentIntent.objects.get(pk=self.start().json()["id"])

    def verify_url(self, intent=None) -> str:
        return f"{PAYMENTS}{(intent or self.intent).pk}/verify/"

    def test_verification_reports_what_the_provider_says(self):
        FakeGateway.arrange(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO, currency="NGN")

        response = self.client.post(self.verify_url(), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], PaymentStatus.SUCCESSFUL)

    def test_a_client_claiming_success_changes_nothing(self):
        # The point of the whole endpoint. The body is not read at all.
        response = self.client.post(
            self.verify_url(), {"status": "success", "amount_kobo": 1}, format="json"
        )

        self.assertEqual(response.json()["status"], PaymentStatus.INITIALIZED)
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentStatus.INITIALIZED)

    def test_a_client_cannot_patch_a_payment_to_successful(self):
        response = self.client.patch(
            f"{PAYMENTS}{self.intent.pk}/", {"status": "SUCCESSFUL"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentStatus.INITIALIZED)

    def test_a_client_cannot_put_a_payment_to_successful(self):
        response = self.client.put(
            f"{PAYMENTS}{self.intent.pk}/", {"status": "SUCCESSFUL"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_an_amount_mismatch_is_refused(self):
        FakeGateway.arrange(self.intent.reference, amount_kobo=100, currency="NGN")

        response = self.client.post(self.verify_url(), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(error_code(response), "PAYMENT_AMOUNT_MISMATCH")

    def test_the_mismatch_refusal_does_not_disclose_the_other_amount(self):
        FakeGateway.arrange(self.intent.reference, amount_kobo=777, currency="NGN")

        body = self.client.post(self.verify_url(), {}, format="json").content.decode()

        self.assertNotIn("777", body)

    def test_a_currency_mismatch_is_refused(self):
        FakeGateway.arrange(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO, currency="USD")

        response = self.client.post(self.verify_url(), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_verifying_twice_is_safe(self):
        FakeGateway.arrange(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO, currency="NGN")

        first = self.client.post(self.verify_url(), {}, format="json")
        second = self.client.post(self.verify_url(), {}, format="json")

        self.assertEqual(first.json()["status"], PaymentStatus.SUCCESSFUL)
        self.assertEqual(second.json()["status"], PaymentStatus.SUCCESSFUL)
        self.assertEqual(PaymentIntent.objects.count(), 1)


class PaymentIsolationTests(PaymentAPITestCase):
    """One customer must learn nothing about another one's payments."""

    def setUp(self):
        super().setUp()
        self.intent = PaymentIntent.objects.get(pk=self.start().json()["id"])
        self.stranger = earning_setup(slug="stranger-clean")["customer"]
        self.client.force_authenticate(self.stranger)

    def test_another_customer_payment_is_a_not_found_rather_than_a_forbidden(self):
        response = self.client.get(f"{PAYMENTS}{self.intent.pk}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_refusal_leaks_neither_the_amount_nor_the_reference(self):
        body = self.client.get(f"{PAYMENTS}{self.intent.pk}/").content.decode()

        self.assertNotIn(str(DEFAULT_PRICE_KOBO), body)
        self.assertNotIn(self.intent.reference, body)

    def test_another_customer_cannot_verify_it(self):
        FakeGateway.arrange(self.intent.reference, amount_kobo=DEFAULT_PRICE_KOBO, currency="NGN")

        response = self.client.post(f"{PAYMENTS}{self.intent.pk}/verify/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.intent.refresh_from_db()
        self.assertEqual(self.intent.status, PaymentStatus.INITIALIZED)

    def test_the_payment_list_shows_only_your_own(self):
        self.assertEqual(self.client.get(PAYMENTS).json()["count"], 0)

    def test_your_own_payments_are_listed(self):
        self.client.force_authenticate(self.customer)

        self.assertEqual(self.client.get(PAYMENTS).json()["count"], 1)


class BankEndpointTests(APITestCase):
    def setUp(self):
        from apps.payments.banks.fake import FakeBankResolver

        FakeBankResolver.clear()
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        self.client.force_authenticate(self.provider.user)

    def payload(self, **overrides):
        return {
            "bank_code": "058",
            "bank_name": "Guaranty Trust Bank",
            "account_name": "Adaeze Okonkwo",
            "account_number": "0123456789",
            **overrides,
        }

    def test_a_provider_can_list_banks(self):
        response = self.client.get(BANKS)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("058", [bank["code"] for bank in response.json()])

    def test_a_customer_without_a_provider_profile_cannot(self):
        self.client.force_authenticate(self.setup["customer"])

        response = self.client.get(BANKS)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(error_code(response), "PROVIDER_PROFILE_NOT_FOUND")

    def test_verifying_an_account_records_the_name_the_bank_returned(self):
        from apps.payments.banks.fake import FakeBankResolver

        self.client.put(DESTINATION, self.payload(), format="json")
        FakeBankResolver.arrange(
            account_number="0123456789", bank_code="058", account_name="ADAEZE N OKONKWO"
        )

        response = self.client.post(
            f"{DESTINATION}verify/", {"account_number": "0123456789"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["verification_status"], "VERIFIED")
        self.assertEqual(response.json()["resolved_account_name"], "ADAEZE N OKONKWO")

    def test_the_account_number_still_never_comes_back(self):
        from apps.payments.banks.fake import FakeBankResolver

        self.client.put(DESTINATION, self.payload(), format="json")
        FakeBankResolver.arrange(
            account_number="0123456789", bank_code="058", account_name="Adaeze Okonkwo"
        )

        body = self.client.post(
            f"{DESTINATION}verify/", {"account_number": "0123456789"}, format="json"
        ).content.decode()

        self.assertNotIn("0123456789", body)
        self.assertIn("6789", body)

    def test_an_account_the_bank_rejects_is_refused(self):
        self.client.put(DESTINATION, self.payload(), format="json")

        response = self.client.post(
            f"{DESTINATION}verify/", {"account_number": "0123456789"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(error_code(response), "BANK_ACCOUNT_NOT_RESOLVED")

    def test_another_provider_cannot_verify_your_destination(self):
        from apps.payments.banks.fake import FakeBankResolver

        self.client.put(DESTINATION, self.payload(), format="json")
        FakeBankResolver.arrange(
            account_number="0123456789", bank_code="058", account_name="Adaeze Okonkwo"
        )

        other = earning_setup(slug="rival-clean")["provider"]
        self.client.force_authenticate(other.user)

        response = self.client.post(
            f"{DESTINATION}verify/", {"account_number": "0123456789"}, format="json"
        )

        # Their own destination does not exist, so there is nothing to verify.
        # They never touch anybody else's.
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(error_code(response), "INVALID_PAYOUT_DESTINATION")

    def test_verification_is_not_public(self):
        self.client.force_authenticate(None)

        response = self.client.post(
            f"{DESTINATION}verify/", {"account_number": "0123456789"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class NoCredentialsInResponsesTests(TestCase):
    """Nothing a client can fetch contains a provider secret."""

    def test_the_openapi_schema_carries_no_key(self):
        from django.test import Client

        from apps.accounts.models import User

        admin = User.objects.create_superuser(email="admin@example.com", password="Lagos-2026-xyz")
        client = Client()
        client.force_login(admin)

        schema = client.get("/api/v1/schema/").content.decode()

        for secret in ("sk_test", "sk_live", "TERMII_API_KEY", "RESEND_API_KEY"):
            self.assertNotIn(secret, schema)
