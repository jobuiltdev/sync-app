"""The provider financial endpoints.

The security cases carry as much weight here as the happy path. A marketplace
whose API will confirm that a competitor's payout id exists, or how much they are
withdrawing, has a problem that no amount of correct arithmetic makes up for.
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.payments import services
from apps.payments.payouts import PayoutRequest, PayoutStatus
from apps.payments.tests.factories import earn, earning_setup, make_destination

EARNINGS = "/api/v1/provider/earnings/"
SETTLEMENTS = "/api/v1/provider/earnings/settlements/"
PAYOUTS = "/api/v1/provider/payouts/"
REQUEST_PAYOUT = "/api/v1/provider/payouts/request/"
DESTINATION = "/api/v1/provider/payout-destination/"


def error_code(response) -> str:
    return response.json()["error"]["code"]


class EarningsEndpointTests(APITestCase):
    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        self.client.force_authenticate(self.provider.user)

    def test_a_provider_who_has_earned_nothing_sees_zeroes_rather_than_an_error(self):
        response = self.client.get(EARNINGS)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["available_kobo"], 0)
        self.assertEqual(response.json()["settlement_count"], 0)

    def test_earnings_report_every_figure_behind_the_balance(self):
        earn(self.setup)

        body = self.client.get(EARNINGS).json()

        self.assertEqual(body["gross_earned_kobo"], 2_000_000)
        self.assertEqual(body["commission_kobo"], 400_000)
        self.assertEqual(body["net_earned_kobo"], 1_600_000)
        self.assertEqual(body["reserved_kobo"], 0)
        self.assertEqual(body["paid_out_kobo"], 0)
        self.assertEqual(body["available_kobo"], 1_600_000)
        self.assertEqual(body["currency"], "NGN")

    def test_money_is_returned_as_integer_kobo_and_never_a_formatted_string(self):
        earn(self.setup)

        body = self.client.get(EARNINGS).json()

        for key, value in body.items():
            if key.endswith("_kobo"):
                self.assertIsInstance(value, int, key)

    def test_the_settlement_list_shows_what_each_job_earned(self):
        earn(self.setup)

        body = self.client.get(SETTLEMENTS).json()

        self.assertEqual(body["count"], 1)
        row = body["results"][0]
        self.assertEqual(row["provider_amount_kobo"], 1_600_000)
        self.assertEqual(row["commission_rate_bps"], 2_000)
        self.assertTrue(row["booking_reference"].startswith("SY-"))

    def test_an_account_with_no_provider_profile_is_told_so(self):
        self.client.force_authenticate(self.setup["customer"])

        response = self.client.get(EARNINGS)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(error_code(response), "PROVIDER_PROFILE_NOT_FOUND")

    def test_earnings_are_not_public(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(EARNINGS).status_code, status.HTTP_401_UNAUTHORIZED)


class PayoutRequestEndpointTests(APITestCase):
    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)
        self.client.force_authenticate(self.provider.user)

    def test_a_payout_can_be_requested(self):
        response = self.client.post(REQUEST_PAYOUT, {"amount_kobo": 600_000}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = response.json()
        self.assertEqual(body["amount_kobo"], 600_000)
        self.assertEqual(body["status"], PayoutStatus.REQUESTED)
        self.assertTrue(body["is_cancellable"])

    def test_requesting_moves_the_money_out_of_available_and_into_reserved(self):
        self.client.post(REQUEST_PAYOUT, {"amount_kobo": 600_000}, format="json")

        body = self.client.get(EARNINGS).json()

        self.assertEqual(body["reserved_kobo"], 600_000)
        self.assertEqual(body["available_kobo"], 1_000_000)

    def test_asking_for_more_than_the_balance_is_refused(self):
        response = self.client.post(REQUEST_PAYOUT, {"amount_kobo": 9_000_000}, format="json")

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(error_code(response), "INSUFFICIENT_BALANCE")
        self.assertEqual(PayoutRequest.objects.count(), 0)

    def test_zero_is_refused_by_validation(self):
        response = self.client.post(REQUEST_PAYOUT, {"amount_kobo": 0}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(error_code(response), "VALIDATION_ERROR")

    def test_a_negative_amount_is_refused(self):
        response = self.client.post(REQUEST_PAYOUT, {"amount_kobo": -600_000}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(PayoutRequest.objects.count(), 0)

    def test_a_second_request_while_one_is_live_is_refused(self):
        self.client.post(REQUEST_PAYOUT, {"amount_kobo": 100_000}, format="json")

        response = self.client.post(REQUEST_PAYOUT, {"amount_kobo": 100_000}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(error_code(response), "PAYOUT_ALREADY_REQUESTED")
        self.assertEqual(PayoutRequest.objects.count(), 1)

    def test_the_same_idempotency_key_twice_creates_one_payout(self):
        first = self.client.post(
            REQUEST_PAYOUT,
            {"amount_kobo": 600_000},
            format="json",
            HTTP_IDEMPOTENCY_KEY="retry-me",
        )
        second = self.client.post(
            REQUEST_PAYOUT,
            {"amount_kobo": 600_000},
            format="json",
            HTTP_IDEMPOTENCY_KEY="retry-me",
        )

        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(PayoutRequest.objects.count(), 1)

    def test_a_retry_does_not_reserve_the_money_twice(self):
        for _ in range(3):
            self.client.post(
                REQUEST_PAYOUT,
                {"amount_kobo": 600_000},
                format="json",
                HTTP_IDEMPOTENCY_KEY="retry-me",
            )

        self.assertEqual(self.client.get(EARNINGS).json()["reserved_kobo"], 600_000)


class PayoutDestinationEndpointTests(APITestCase):
    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        earn(self.setup)
        self.client.force_authenticate(self.provider.user)

    def payload(self, **overrides):
        return {
            "bank_code": "058",
            "bank_name": "Guaranty Trust Bank",
            "account_name": "Adaeze Okonkwo",
            "account_number": "0123456789",
            **overrides,
        }

    def test_requesting_a_payout_without_an_account_says_what_to_fix(self):
        response = self.client.post(REQUEST_PAYOUT, {"amount_kobo": 100_000}, format="json")

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(error_code(response), "INVALID_PAYOUT_DESTINATION")

    def test_an_account_can_be_set(self):
        response = self.client.put(DESTINATION, self.payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["account_number_last4"], "6789")

    def test_the_account_number_never_comes_back(self):
        self.client.put(DESTINATION, self.payload(), format="json")

        body = self.client.get(DESTINATION).content.decode()

        self.assertNotIn("0123456789", body)
        self.assertIn("6789", body)

    def test_a_short_account_number_is_refused(self):
        response = self.client.put(DESTINATION, self.payload(account_number="123"), format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reading_before_setting_one_says_to_add_an_account(self):
        response = self.client.get(DESTINATION)

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(error_code(response), "INVALID_PAYOUT_DESTINATION")

    def test_setting_an_account_is_not_enough_on_its_own(self):
        # Ten digits somebody typed is not a confirmed account. From M6A a payout
        # needs the bank to have said the account exists.
        self.client.put(DESTINATION, self.payload(), format="json")

        response = self.client.post(REQUEST_PAYOUT, {"amount_kobo": 100_000}, format="json")

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(error_code(response), "PAYOUT_DESTINATION_NOT_VERIFIED")

    def test_confirming_the_account_unblocks_the_payout(self):
        from apps.payments.banks.fake import FakeBankResolver

        self.client.put(DESTINATION, self.payload(), format="json")
        FakeBankResolver.arrange(
            account_number="0123456789", bank_code="058", account_name="Adaeze Okonkwo"
        )
        self.client.post(f"{DESTINATION}verify/", {"account_number": "0123456789"}, format="json")

        response = self.client.post(REQUEST_PAYOUT, {"amount_kobo": 100_000}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class PayoutCapabilityEndpointTests(APITestCase):
    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)
        self.client.force_authenticate(self.provider.user)

    def test_an_unverified_provider_is_refused_with_the_flow_to_fix_it(self):
        user = self.provider.user
        user.email_verified_at = None
        user.save(update_fields=["email_verified_at"])

        response = self.client.post(REQUEST_PAYOUT, {"amount_kobo": 100_000}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(error_code(response), "EMAIL_VERIFICATION_REQUIRED")

        details = response.json()["error"]["details"]
        self.assertEqual(details["capability"], "REQUEST_PAYOUT")
        self.assertEqual(details["unmet"], ["EMAIL_VERIFIED"])
        self.assertIn("verification/request", details["next_step"]["action"])

    def test_a_refused_request_writes_nothing(self):
        user = self.provider.user
        user.phone_verified_at = None
        user.save(update_fields=["phone_verified_at"])

        self.client.post(REQUEST_PAYOUT, {"amount_kobo": 100_000}, format="json")

        self.assertEqual(PayoutRequest.objects.count(), 0)

    def test_reading_earnings_does_not_require_verification(self):
        # Seeing what you have earned is not the same as taking it out, and
        # blocking the view would leave a provider unable to see why they should
        # bother verifying.
        user = self.provider.user
        user.email_verified_at = None
        user.phone_verified_at = None
        user.save(update_fields=["email_verified_at", "phone_verified_at"])

        self.assertEqual(self.client.get(EARNINGS).status_code, status.HTTP_200_OK)


class PayoutIsolationTests(APITestCase):
    """One provider must not learn anything about another one's money."""

    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)
        self.payout = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=600_000
        )

        self.other = earning_setup(slug="rival-clean")
        make_destination(self.other["provider"])
        earn(self.other, price_kobo=5_000_000)

        self.client.force_authenticate(self.other["provider"].user)

    def detail(self) -> str:
        return f"{PAYOUTS}{self.payout.pk}/"

    def test_another_provider_payout_is_a_not_found_rather_than_a_forbidden(self):
        response = self.client.get(self.detail())

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_refusal_leaks_neither_the_amount_nor_the_owner(self):
        body = self.client.get(self.detail()).content.decode()

        self.assertNotIn("600000", body)
        self.assertNotIn(self.provider.display_name, body)
        self.assertNotIn(str(self.provider.pk), body)

    def test_another_provider_cannot_cancel_it(self):
        response = self.client.post(f"{self.detail()}cancel/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(error_code(response), "PAYOUT_NOT_FOUND")

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.REQUESTED)

    def test_the_payout_list_shows_only_your_own(self):
        body = self.client.get(PAYOUTS).json()

        self.assertEqual(body["count"], 0)

    def test_the_settlement_list_shows_only_your_own(self):
        body = self.client.get(SETTLEMENTS).json()

        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["provider_amount_kobo"], 4_000_000)

    def test_earnings_are_your_own_and_not_the_marketplace(self):
        self.assertEqual(self.client.get(EARNINGS).json()["available_kobo"], 4_000_000)


class PayoutStatusIsNotClientWritableTests(APITestCase):
    """The rule the whole lifecycle exists for, checked at the HTTP boundary."""

    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)
        self.payout = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=600_000
        )
        self.client.force_authenticate(self.provider.user)

    def detail(self) -> str:
        return f"{PAYOUTS}{self.payout.pk}/"

    def test_a_provider_cannot_patch_their_payout_to_paid(self):
        response = self.client.patch(self.detail(), {"status": "PAID"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.REQUESTED)

    def test_a_provider_cannot_put_their_payout_to_paid(self):
        response = self.client.put(self.detail(), {"status": "PAID"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.REQUESTED)

    def test_sending_a_status_when_requesting_a_payout_is_ignored(self):
        services.cancel_payout(self.payout.pk, self.provider)

        response = self.client.post(
            REQUEST_PAYOUT, {"amount_kobo": 100_000, "status": "PAID"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["status"], PayoutStatus.REQUESTED)

    def test_there_is_no_endpoint_that_marks_a_payout_paid(self):
        for path in ("pay/", "paid/", "process/", "complete/"):
            with self.subTest(path=path):
                response = self.client.post(f"{self.detail()}{path}", {}, format="json")

                self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_provider_may_cancel_their_own_payout(self):
        response = self.client.post(f"{self.detail()}cancel/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], PayoutStatus.CANCELLED)

    def test_cancelling_returns_the_money_to_the_balance(self):
        self.client.post(f"{self.detail()}cancel/", {}, format="json")

        self.assertEqual(self.client.get(EARNINGS).json()["available_kobo"], 1_600_000)

    def test_cancelling_one_already_being_processed_is_refused(self):
        services.start_processing(self.payout)

        response = self.client.post(f"{self.detail()}cancel/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(error_code(response), "PAYOUT_NOT_ACTIONABLE")

    def test_the_detail_response_says_what_may_happen_next(self):
        body = self.client.get(self.detail()).json()

        self.assertTrue(body["is_cancellable"])
        self.assertEqual(body["allowed_transitions"], ["CANCELLED", "FAILED", "PROCESSING"])

    def test_a_processed_payout_is_no_longer_cancellable_in_the_response(self):
        services.mark_paid(services.start_processing(self.payout))

        body = self.client.get(self.detail()).json()

        self.assertFalse(body["is_cancellable"])
        self.assertEqual(body["allowed_transitions"], [])
