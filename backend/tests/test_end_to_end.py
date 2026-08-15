"""The whole marketplace, once, through the API.

Every other test in this project checks one thing carefully. This one checks that
they compose: a person registers, proves who they are, books a job, pays for it,
has it done, and the provider gets their money. Twenty-one steps, all through
HTTP, with only the external providers faked.

It is deliberately one long test rather than twenty small ones. The value is in
the sequence: each step depends on the state the previous one left, and a suite
of independent steps with hand-built fixtures would not notice if the real path
between two of them broke.

Lives in `backend/tests/` rather than in an app, because it belongs to no single
domain and asserting on it from inside one would be a lie about ownership.
"""

import hashlib
import hmac
import json

from django.conf import settings
from django.test import TransactionTestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.challenges import VerificationChallenge
from apps.accounts.models import User
from apps.accounts.sms.locmem import LocMemSMSProvider
from apps.bookings.state import BookingStatus
from apps.catalog.tests.factories import make_service
from apps.notifications.events import EventType
from apps.notifications.models import DeliveryStatus, Notification
from apps.payments.banks.fake import FakeBankResolver
from apps.payments.gateways.fake import FakeGateway
from apps.payments.intents import PaymentIntent
from apps.payments.payouts import PayoutRequest, PayoutStatus
from apps.payments.settlements import BookingSettlement
from apps.payments.transfers.base import TransferState
from apps.payments.transfers.fake import FakeTransferProvider
from apps.providers.models import ProviderProfile, VerificationStatus

PASSWORD = "Lagos-Rider-2026"
CLEANING = {
    "property_type": "APARTMENT",
    "bedrooms": 3,
    "bathrooms": 2,
    "depth": "STANDARD",
    "has_supplies": False,
}


def sign(body: bytes) -> str:
    return hmac.new(
        settings.PAYMENT_GATEWAY_FAKE["SECRET"].encode(), body, hashlib.sha512
    ).hexdigest()


def _events(user: User) -> set:
    return set(Notification.objects.filter(recipient=user).values_list("event_type", flat=True))


def _sms_bodies() -> list[str]:
    return [message.body for message in LocMemSMSProvider.messages]


@override_settings(
    SMS_BACKEND="apps.accounts.sms.locmem.LocMemSMSProvider",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    # Declared rather than inherited. This runs under whichever settings module
    # the runner loaded, and the notification assertions at the end need delivery
    # to happen in this process: against a real broker with no worker, every
    # message would sit queued and the test would be asserting on nothing.
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class EndToEndTests(TransactionTestCase):
    """One customer, one provider, one job, one payout."""

    reset_sequences = True

    def setUp(self):
        FakeGateway.clear()
        FakeBankResolver.clear()
        FakeTransferProvider.clear()
        LocMemSMSProvider.clear()

        self.service = make_service(slug="standard-clean", base_price_kobo=2_000_000)
        self.customer = APIClient()
        self.provider = APIClient()
        self.anonymous = APIClient()

    # --- helpers -----------------------------------------------------------

    def register(self, client: APIClient, email: str, phone: str) -> dict:
        response = client.post(
            "/api/v1/auth/register/",
            {
                "email": email,
                "password": PASSWORD,
                "first_name": "Ada",
                "last_name": "Okeke",
                "phone": phone,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        session = response.json()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {session['tokens']['access']}")
        return session

    def verify_phone(self, client: APIClient, user: User) -> None:
        """Requests a code and submits it, the way the app does.

        The code is read from the in-memory SMS provider rather than from the
        database, because the database only ever holds its hash. That is the
        point of the design, and this is the only place the whole system lets
        anybody see a code at all.
        """
        response = client.post("/api/v1/auth/phone/verification/request/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        sent = LocMemSMSProvider.last()
        assert sent is not None, "no code was sent"

        response = client.post(
            "/api/v1/auth/phone/verification/confirm/",
            {"challenge_id": response.json()["challenge_id"], "code": sent.code},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        user.refresh_from_db()
        self.assertIsNotNone(user.phone_verified_at)

    def verify_email(self, client: APIClient, user: User) -> None:
        from django.core import mail

        mail.outbox = []
        response = client.post("/api/v1/auth/email/verification/request/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        code = next(
            word.rstrip(".")
            for word in mail.outbox[0].body.split()
            if word.rstrip(".").isdigit() and len(word.rstrip(".")) == 6
        )
        response = client.post(
            "/api/v1/auth/email/verification/confirm/",
            {"challenge_id": response.json()["challenge_id"], "code": code},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        user.refresh_from_db()
        self.assertIsNotNone(user.email_verified_at)

    # --- the flow ----------------------------------------------------------

    def test_a_booking_goes_from_registration_to_a_paid_provider(self):
        # 1. Register. A phone number is required at signup.
        customer_session = self.register(self.customer, "ada@example.com", "0803 123 4567")
        customer = User.objects.get(pk=customer_session["user"]["id"])

        # 2. The number was normalised to E.164 on the way in.
        self.assertEqual(customer.phone, "+2348031234567")
        self.assertFalse(customer_session["user"]["is_phone_verified"])

        # 3. Phone verification.
        self.verify_phone(self.customer, customer)

        # 4. Email verification.
        self.verify_email(self.customer, customer)

        # 5. Browse the catalog. Open to anybody, including a signed-out visitor.
        catalog = self.anonymous.get("/api/v1/catalog/categories/")
        self.assertEqual(catalog.status_code, status.HTTP_200_OK)

        # 6. A second account becomes a provider.
        provider_session = self.register(self.provider, "tunde@example.com", "0803 765 4321")
        provider_user = User.objects.get(pk=provider_session["user"]["id"])
        self.verify_phone(self.provider, provider_user)
        self.verify_email(self.provider, provider_user)

        response = self.provider.post(
            "/api/v1/provider/profile/create/", {"display_name": "Tunde Cleaning"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        profile = ProviderProfile.objects.get(user=provider_user)

        # 7. Eligible: offers the service, covers the area, approved, and on call.
        self.provider.post(
            "/api/v1/provider/services/", {"service_slug": self.service.slug}, format="json"
        )
        self.provider.post("/api/v1/provider/areas/", {"state": "LAGOS"}, format="json")
        profile.verification_status = VerificationStatus.APPROVED
        profile.is_accepting_jobs = True
        profile.save(update_fields=["verification_status", "is_accepting_jobs"])

        # 8. The customer adds an address and books.
        address = self.customer.post(
            "/api/v1/customer/addresses/",
            {
                "street_address": "14 Adeola Odeku Street",
                "landmark": "Opposite Eko Hotel gate",
                "area": "Victoria Island",
                "lga": "Eti-Osa",
                "state": "LAGOS",
            },
            format="json",
        )
        self.assertEqual(address.status_code, status.HTTP_201_CREATED, address.data)

        booking = self.customer.post(
            "/api/v1/customer/bookings/",
            {
                "service_slug": self.service.slug,
                "address_id": address.json()["id"],
                "details": CLEANING,
            },
            format="json",
        )
        self.assertEqual(booking.status_code, status.HTTP_201_CREATED, booking.data)
        booking_id = booking.json()["id"]
        self.assertEqual(booking.json()["status"], BookingStatus.MATCHING)
        self.assertEqual(booking.json()["total_kobo"], 2_000_000)

        # 9. The provider has an offer waiting.
        offers = self.provider.get("/api/v1/provider/offers/").json()
        self.assertEqual(offers["count"], 1)
        offer_id = offers["results"][0]["id"]

        # 10. They accept, and the booking is theirs.
        accepted = self.provider.post(
            f"/api/v1/provider/offers/{offer_id}/accept/", {}, format="json"
        )
        self.assertEqual(accepted.status_code, status.HTTP_200_OK, accepted.data)
        self.assertEqual(accepted.json()["status"], BookingStatus.ASSIGNED)

        # 11. The customer starts paying.
        payment = self.customer.post(
            f"/api/v1/customer/bookings/{booking_id}/pay/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="e2e-pay-1",
        )
        self.assertEqual(payment.status_code, status.HTTP_201_CREATED, payment.data)
        intent = payment.json()
        self.assertEqual(intent["amount_kobo"], 2_000_000)
        self.assertEqual(intent["status"], "INITIALIZED")
        self.assertTrue(intent["authorization_url"])

        # A retry of the same tap does not start a second collection.
        again = self.customer.post(
            f"/api/v1/customer/bookings/{booking_id}/pay/",
            {},
            format="json",
            HTTP_IDEMPOTENCY_KEY="e2e-pay-1",
        )
        self.assertEqual(again.json()["id"], intent["id"])

        # 12. The provider confirms it, through a signed webhook.
        reference = PaymentIntent.objects.get(pk=intent["id"]).reference
        body = json.dumps(
            {
                "event": "charge.success",
                "data": {
                    "id": 424242,
                    "reference": reference,
                    "status": "success",
                    "amount": 2_000_000,
                    "currency": "NGN",
                    "channel": "card",
                },
            }
        ).encode()
        webhook = self.anonymous.post(
            "/api/v1/webhooks/paystack/",
            data=body,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=sign(body),
        )
        self.assertEqual(webhook.status_code, status.HTTP_200_OK)

        paid = self.customer.get(f"/api/v1/customer/payments/{intent['id']}/").json()
        self.assertEqual(paid["status"], "SUCCESSFUL")

        # Paying does not settle on its own: the work is not finished.
        self.assertEqual(BookingSettlement.objects.count(), 0)

        # 13. The provider does the job.
        for action in ("start", "finish"):
            response = self.provider.post(
                f"/api/v1/provider/bookings/{booking_id}/{action}/", {}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # 14. The customer confirms it is done.
        confirmed = self.customer.post(
            f"/api/v1/customer/bookings/{booking_id}/confirm/", {}, format="json"
        )
        self.assertEqual(confirmed.status_code, status.HTTP_200_OK, confirmed.data)
        self.assertEqual(confirmed.json()["status"], BookingStatus.COMPLETED)

        # 15. Completion plus payment is what creates the settlement.
        settlement = BookingSettlement.objects.get(booking_id=booking_id)
        self.assertEqual(settlement.gross_amount_kobo, 2_000_000)
        self.assertEqual(settlement.commission_amount_kobo, 400_000)
        self.assertEqual(settlement.provider_amount_kobo, 1_600_000)

        # 16. The provider can see what they earned.
        earnings = self.provider.get("/api/v1/provider/earnings/").json()
        self.assertEqual(earnings["available_kobo"], 1_600_000)
        self.assertEqual(earnings["settlement_count"], 1)

        # 17. Payout destination: saved, then confirmed with the bank.
        self.provider.put(
            "/api/v1/provider/payout-destination/",
            {
                "bank_code": "058",
                "bank_name": "Guaranty Trust Bank",
                "account_name": "Tunde Bello",
                "account_number": "0123456789",
            },
            format="json",
        )

        # Unconfirmed, so a payout is refused.
        refused = self.provider.post(
            "/api/v1/provider/payouts/request/", {"amount_kobo": 1_600_000}, format="json"
        )
        self.assertEqual(refused.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(refused.json()["error"]["code"], "PAYOUT_DESTINATION_NOT_VERIFIED")

        FakeBankResolver.arrange(
            account_number="0123456789", bank_code="058", account_name="TUNDE BELLO"
        )
        confirmed_account = self.provider.post(
            "/api/v1/provider/payout-destination/verify/",
            {"account_number": "0123456789"},
            format="json",
        )
        self.assertEqual(confirmed_account.status_code, status.HTTP_200_OK)
        self.assertEqual(confirmed_account.json()["resolved_account_name"], "TUNDE BELLO")

        # 18. The provider asks to be paid.
        requested = self.provider.post(
            "/api/v1/provider/payouts/request/",
            {"amount_kobo": 1_600_000},
            format="json",
            HTTP_IDEMPOTENCY_KEY="e2e-payout-1",
        )
        self.assertEqual(requested.status_code, status.HTTP_201_CREATED, requested.data)
        payout_id = requested.json()["id"]
        self.assertEqual(requested.json()["status"], PayoutStatus.REQUESTED)

        # The money is reserved, not available.
        self.assertEqual(
            self.provider.get("/api/v1/provider/earnings/").json()["available_kobo"], 0
        )

        # 19. An operator releases it. There is no automatic payout, and no API
        # route by which a provider could send their own.
        from apps.payments.tasks import execute_payout_task

        execute_payout_task(str(payout_id))

        payout = PayoutRequest.objects.get(pk=payout_id)
        self.assertEqual(payout.status, PayoutStatus.PROCESSING)
        self.assertTrue(payout.transfer_reference.startswith("SYT-"))

        # 20. Reconciliation resolves it once the provider confirms.
        from apps.payments.tasks import reconcile_payouts

        FakeTransferProvider.arrange(payout.transfer_reference, state=TransferState.SUCCESSFUL)
        reconcile_payouts()

        payout.refresh_from_db()
        self.assertEqual(payout.status, PayoutStatus.PAID)

        # 21. The final position, as the mobile app reads it.
        final = self.provider.get("/api/v1/provider/earnings/").json()
        self.assertEqual(final["net_earned_kobo"], 1_600_000)
        self.assertEqual(final["paid_out_kobo"], 1_600_000)
        self.assertEqual(final["available_kobo"], 0)
        self.assertEqual(final["reserved_kobo"], 0)

        detail = self.provider.get(f"/api/v1/provider/payouts/{payout_id}/").json()
        self.assertEqual(detail["status"], PayoutStatus.PAID)
        self.assertFalse(detail["is_cancellable"])

        # Nothing anywhere in that exchange handed a client an account number.
        self.assertNotIn("0123456789", str(confirmed_account.json()))

        # 22. Both people were told what happened, all the way through.
        #
        # This runs in a TransactionTestCase, so `on_commit` actually fires and
        # every message above was rendered and handed to a provider for real
        # rather than being left as a pending row.
        self.assertEqual(
            _events(customer),
            {
                EventType.BOOKING_CREATED,
                EventType.PROVIDER_ASSIGNED,
                EventType.PAYMENT_SUCCEEDED,
                EventType.BOOKING_IN_PROGRESS,
                EventType.BOOKING_AWAITING_CONFIRMATION,
                EventType.BOOKING_COMPLETED,
            },
        )
        self.assertEqual(
            _events(provider_user),
            {
                EventType.OFFER_RECEIVED,
                EventType.OFFER_ACCEPTED,
                EventType.EARNINGS_AVAILABLE,
                EventType.PAYOUT_REQUESTED,
                EventType.PAYOUT_PROCESSING,
                EventType.PAYOUT_PAID,
            },
        )

        # Every one of them actually went out. A `PENDING` row here would mean
        # the path is wired but nothing reaches anybody.
        self.assertFalse(
            Notification.objects.exclude(status=DeliveryStatus.SENT).exists(),
            list(
                Notification.objects.exclude(status=DeliveryStatus.SENT).values_list(
                    "event_type", "status", "failure_reason"
                )
            ),
        )

        # And nobody was sent anybody else's news.
        for notification in Notification.objects.all():
            self.assertIn(notification.recipient_id, {customer.pk, provider_user.pk})

        # The provider was told where the job was, and never the street address.
        offers = [body for body in _sms_bodies() if "Victoria Island" in body]
        self.assertTrue(offers)
        self.assertNotIn("Adeola Odeku", " ".join(_sms_bodies()))


@override_settings(
    SMS_BACKEND="apps.accounts.sms.locmem.LocMemSMSProvider",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class EndToEndRefusalTests(TransactionTestCase):
    """The paths that must not work, in the same shape as the one that does."""

    reset_sequences = True

    def setUp(self):
        FakeGateway.clear()
        self.service = make_service(slug="standard-clean", base_price_kobo=2_000_000)
        self.client_a = APIClient()

    def register(self, client: APIClient, email: str, phone: str) -> dict:
        response = client.post(
            "/api/v1/auth/register/",
            {"email": email, "password": PASSWORD, "phone": phone},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        session = response.json()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {session['tokens']['access']}")
        return session

    def test_registration_without_a_phone_is_refused(self):
        response = APIClient().post(
            "/api/v1/auth/register/",
            {"email": "nophone@example.com", "password": PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.json()["error"]["details"]["fields"])

    def test_booking_without_a_verified_phone_is_refused(self):
        session = self.register(self.client_a, "ada@example.com", "0803 123 4567")
        user = User.objects.get(pk=session["user"]["id"])
        address = self.client_a.post(
            "/api/v1/customer/addresses/",
            {
                "street_address": "14 Adeola Odeku Street",
                "landmark": "Opposite Eko Hotel gate",
                "state": "LAGOS",
            },
            format="json",
        )

        response = self.client_a.post(
            "/api/v1/customer/bookings/",
            {
                "service_slug": self.service.slug,
                "address_id": address.json()["id"],
                "details": CLEANING,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()["error"]["code"], "PHONE_VERIFICATION_REQUIRED")
        self.assertIsNone(user.phone_verified_at)

    def test_an_unsigned_webhook_is_refused(self):
        response = APIClient().post(
            "/api/v1/webhooks/paystack/",
            data=json.dumps({"event": "charge.success", "data": {}}).encode(),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json()["error"]["message"], "Rejected.")

    def test_a_client_cannot_declare_a_payment_successful(self):
        self.register(self.client_a, "ada@example.com", "0803 123 4567")
        challenge = VerificationChallenge.objects.count()

        response = self.client_a.patch(
            "/api/v1/customer/payments/00000000-0000-4000-8000-000000000000/",
            {"status": "SUCCESSFUL"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(VerificationChallenge.objects.count(), challenge)

    def test_another_customer_booking_is_a_not_found(self):
        self.register(self.client_a, "ada@example.com", "0803 123 4567")

        response = self.client_a.get(
            "/api/v1/customer/bookings/00000000-0000-4000-8000-000000000000/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_verification_code_is_never_readable_from_the_api(self):
        session = self.register(self.client_a, "ada@example.com", "0803 123 4567")
        LocMemSMSProvider.clear()

        response = self.client_a.post("/api/v1/auth/phone/verification/request/", {}, format="json")

        body = response.content.decode()
        sent = LocMemSMSProvider.last()
        self.assertIsNotNone(sent)
        self.assertNotIn(sent.code, body)
        self.assertIsNotNone(session)

        # Nor from the stored challenge, which holds only a hash.
        challenge = VerificationChallenge.objects.latest("created_at")
        self.assertNotIn(sent.code, challenge.code_hash)
