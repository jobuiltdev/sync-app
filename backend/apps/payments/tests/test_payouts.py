"""Payout requests: what is refused, and who may move one where."""

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounts.errors import VerificationRequired
from apps.bookings.state import ActorType
from apps.payments import services
from apps.payments.destinations import PayoutDestination
from apps.payments.errors import (
    InsufficientBalance,
    InvalidPayoutAmount,
    InvalidPayoutDestination,
    PayoutAlreadyRequested,
    PayoutNotActionable,
    PayoutNotFound,
)
from apps.payments.payouts import PayoutRequest, PayoutStatus
from apps.payments.tests.factories import earn, earning_setup, make_destination


class PayoutRequestTests(TestCase):
    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)

    def request(self, amount_kobo=600_000, **kwargs):
        return services.request_payout(
            provider=self.provider,
            actor=self.provider.user,
            amount_kobo=amount_kobo,
            **kwargs,
        )

    def test_a_provider_can_ask_for_part_of_what_they_earned(self):
        payout = self.request(600_000)

        self.assertEqual(payout.status, PayoutStatus.REQUESTED)
        self.assertEqual(payout.amount_kobo, 600_000)
        self.assertEqual(payout.currency, "NGN")
        self.assertIsNone(payout.processed_at)
        self.assertEqual(payout.failure_reason, "")

    def test_a_provider_can_ask_for_all_of_it(self):
        self.assertEqual(self.request(1_600_000).amount_kobo, 1_600_000)

    def test_asking_for_more_than_is_available_is_refused(self):
        with self.assertRaises(InsufficientBalance) as caught:
            self.request(1_600_001)

        self.assertEqual(caught.exception.details["available_kobo"], 1_600_000)
        self.assertEqual(caught.exception.details["requested_kobo"], 1_600_001)
        self.assertEqual(PayoutRequest.objects.count(), 0)

    def test_asking_for_the_gross_rather_than_the_net_is_refused(self):
        # The commission was never theirs, so the figure they can withdraw is the
        # provider share and not what the customer paid.
        with self.assertRaises(InsufficientBalance):
            self.request(2_000_000)

    def test_zero_is_refused(self):
        with self.assertRaises(InvalidPayoutAmount):
            self.request(0)

    def test_a_negative_amount_is_refused(self):
        with self.assertRaises(InvalidPayoutAmount):
            self.request(-500_000)

        self.assertEqual(PayoutRequest.objects.count(), 0)

    def test_only_one_payout_at_a_time(self):
        self.request(600_000)

        with self.assertRaises(PayoutAlreadyRequested):
            self.request(100_000)

        self.assertEqual(PayoutRequest.objects.count(), 1)

    def test_a_second_payout_is_allowed_once_the_first_is_finished(self):
        services.mark_paid(services.start_processing(self.request(600_000)))

        self.assertEqual(self.request(400_000).status, PayoutStatus.REQUESTED)
        self.assertEqual(PayoutRequest.objects.count(), 2)

    def test_the_second_payout_is_measured_against_what_is_left(self):
        services.mark_paid(services.start_processing(self.request(1_000_000)))

        with self.assertRaises(InsufficientBalance):
            self.request(700_000)

    def test_nothing_is_written_when_a_request_is_refused(self):
        with self.assertRaises(InsufficientBalance):
            self.request(99_999_999)

        self.assertEqual(PayoutRequest.objects.count(), 0)


class PayoutDestinationRequirementTests(TestCase):
    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        earn(self.setup)

    def request(self, amount_kobo=600_000):
        return services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=amount_kobo
        )

    def test_a_provider_with_no_account_on_file_is_refused(self):
        with self.assertRaises(InvalidPayoutDestination):
            self.request()

        self.assertEqual(PayoutRequest.objects.count(), 0)

    def test_a_deactivated_destination_is_refused(self):
        destination = make_destination(self.provider)
        destination.is_active = False
        destination.save(update_fields=["is_active"])

        with self.assertRaises(InvalidPayoutDestination):
            self.request()

    def test_adding_an_account_unblocks_the_request(self):
        make_destination(self.provider)

        self.assertEqual(self.request().status, PayoutStatus.REQUESTED)

    def test_the_account_number_is_not_stored(self):
        make_destination(self.provider, account_number="0987654321")
        destination = PayoutDestination.objects.get(provider=self.provider)

        stored = " ".join(
            str(value) for value in destination.__dict__.values() if isinstance(value, str)
        )

        self.assertNotIn("0987654321", stored)
        self.assertEqual(destination.account_number_last4, "4321")

    def test_the_hash_recognises_the_same_account_without_revealing_it(self):
        destination = make_destination(self.provider, account_number="0987654321")

        self.assertTrue(destination.matches("0987654321"))
        self.assertFalse(destination.matches("0987654322"))

    def test_changing_the_account_drops_any_transfer_token_for_the_old_one(self):
        destination = make_destination(self.provider)
        destination.provider_reference = "RCP_oldaccount"
        destination.save(update_fields=["provider_reference"])

        updated = make_destination(self.provider, account_number="0000000001")

        self.assertEqual(updated.provider_reference, "")
        self.assertEqual(updated.account_number_last4, "0001")

    def test_updating_the_destination_does_not_create_a_second_one(self):
        make_destination(self.provider)
        make_destination(self.provider, account_number="0000000001")

        self.assertEqual(PayoutDestination.objects.filter(provider=self.provider).count(), 1)


class PayoutCapabilityTests(TestCase):
    """Both contact channels must be proven before any money is asked for."""

    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)

    def request(self):
        return services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=100_000
        )

    def test_an_unverified_phone_refuses_the_request(self):
        user = self.provider.user
        user.phone_verified_at = None
        user.save(update_fields=["phone_verified_at"])

        with self.assertRaises(VerificationRequired) as caught:
            self.request()

        self.assertEqual(caught.exception.details["unmet"], ["PHONE_VERIFIED"])
        self.assertEqual(PayoutRequest.objects.count(), 0)

    def test_an_unverified_email_refuses_the_request(self):
        user = self.provider.user
        user.email_verified_at = None
        user.save(update_fields=["email_verified_at"])

        with self.assertRaises(VerificationRequired) as caught:
            self.request()

        self.assertEqual(caught.exception.details["unmet"], ["EMAIL_VERIFIED"])

    def test_neither_verified_names_both(self):
        user = self.provider.user
        user.phone_verified_at = None
        user.email_verified_at = None
        user.save(update_fields=["phone_verified_at", "email_verified_at"])

        with self.assertRaises(VerificationRequired) as caught:
            self.request()

        self.assertEqual(
            sorted(caught.exception.details["unmet"]), ["EMAIL_VERIFIED", "PHONE_VERIFIED"]
        )

    def test_the_refusal_happens_before_anything_financial_is_read_or_written(self):
        user = self.provider.user
        user.phone_verified_at = None
        user.save(update_fields=["phone_verified_at"])

        with self.assertRaises(VerificationRequired):
            self.request()

        self.assertEqual(PayoutRequest.objects.count(), 0)
        self.assertEqual(services.available_balance(self.provider).reserved_kobo, 0)


class PayoutIdempotencyTests(TestCase):
    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)

    def request(self, amount_kobo=600_000, key=""):
        return services.request_payout(
            provider=self.provider,
            actor=self.provider.user,
            amount_kobo=amount_kobo,
            idempotency_key=key,
        )

    def test_the_same_key_twice_is_one_payout(self):
        first = self.request(key="abc-123")
        second = self.request(key="abc-123")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PayoutRequest.objects.count(), 1)

    def test_a_replay_does_not_reserve_the_money_twice(self):
        self.request(600_000, key="abc-123")
        self.request(600_000, key="abc-123")

        self.assertEqual(services.available_balance(self.provider).reserved_kobo, 600_000)

    def test_a_replay_returns_the_original_even_after_it_finished(self):
        first = self.request(600_000, key="abc-123")
        services.mark_paid(services.start_processing(first))

        replay = self.request(600_000, key="abc-123")

        self.assertEqual(replay.pk, first.pk)
        self.assertEqual(replay.status, PayoutStatus.PAID)
        self.assertEqual(PayoutRequest.objects.count(), 1)

    def test_a_different_key_is_a_different_payout(self):
        services.mark_paid(services.start_processing(self.request(600_000, key="first")))

        self.assertEqual(self.request(400_000, key="second").amount_kobo, 400_000)
        self.assertEqual(PayoutRequest.objects.count(), 2)

    def test_requests_without_a_key_are_not_collapsed_into_one(self):
        # Blank is the absence of a key, not a key everybody shares.
        services.mark_paid(services.start_processing(self.request(600_000)))
        self.request(400_000)

        self.assertEqual(PayoutRequest.objects.count(), 2)

    def test_the_database_refuses_a_duplicate_key_whatever_the_service_believed(self):
        self.request(600_000, key="abc-123")

        with self.assertRaises(IntegrityError), transaction.atomic():
            PayoutRequest.objects.create(
                provider=self.provider,
                amount_kobo=1,
                status=PayoutStatus.PAID,
                processed_at=timezone.now(),
                idempotency_key="abc-123",
            )


class PayoutLifecycleTests(TestCase):
    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)
        self.payout = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=600_000
        )

    def test_the_happy_path_runs_requested_to_processing_to_paid(self):
        services.start_processing(self.payout)
        self.assertEqual(self.payout.status, PayoutStatus.PROCESSING)

        services.mark_paid(self.payout)
        self.assertEqual(self.payout.status, PayoutStatus.PAID)
        self.assertIsNotNone(self.payout.processed_at)

    def test_a_failure_records_why(self):
        services.mark_failed(self.payout, reason="Account number rejected")

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.FAILED)
        self.assertEqual(self.payout.failure_reason, "Account number rejected")
        self.assertIsNotNone(self.payout.processed_at)

    def test_a_provider_may_cancel_their_own_request(self):
        cancelled = services.cancel_payout(self.payout.pk, self.provider)

        self.assertEqual(cancelled.status, PayoutStatus.CANCELLED)
        self.assertIsNotNone(cancelled.processed_at)

    def test_a_provider_may_not_mark_their_own_payout_as_paid(self):
        with self.assertRaises(PayoutNotActionable):
            services.transition_payout(
                self.payout, PayoutStatus.PAID, actor_type=ActorType.PROVIDER
            )

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.REQUESTED)

    def test_a_provider_may_not_start_processing_their_own_payout(self):
        with self.assertRaises(PayoutNotActionable):
            services.transition_payout(
                self.payout, PayoutStatus.PROCESSING, actor_type=ActorType.PROVIDER
            )

    def test_a_customer_may_not_touch_a_payout_at_all(self):
        for target in PayoutStatus.values:
            with self.subTest(target=target), self.assertRaises(PayoutNotActionable):
                services.transition_payout(self.payout, target, actor_type=ActorType.CUSTOMER)

    def test_requested_cannot_jump_straight_to_paid(self):
        with self.assertRaises(PayoutNotActionable):
            services.transition_payout(self.payout, PayoutStatus.PAID, actor_type=ActorType.SYSTEM)

    def test_a_paid_payout_is_final(self):
        services.mark_paid(services.start_processing(self.payout))

        for target in PayoutStatus.values:
            with self.subTest(target=target), self.assertRaises(PayoutNotActionable):
                services.transition_payout(self.payout, target, actor_type=ActorType.ADMIN)

    def test_a_cancelled_payout_cannot_be_revived(self):
        services.cancel_payout(self.payout.pk, self.provider)
        self.payout.refresh_from_db()

        with self.assertRaises(PayoutNotActionable):
            services.start_processing(self.payout)

    def test_a_payout_being_processed_can_no_longer_be_cancelled_by_its_owner(self):
        services.start_processing(self.payout)

        with self.assertRaises(PayoutNotActionable):
            services.cancel_payout(self.payout.pk, self.provider)

    def test_cancelling_somebody_else_payout_is_a_not_found(self):
        other = earning_setup(slug="stranger-clean")["provider"]

        with self.assertRaises(PayoutNotFound):
            services.cancel_payout(self.payout.pk, other)

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, PayoutStatus.REQUESTED)

    def test_an_unknown_payout_id_is_a_not_found(self):
        with self.assertRaises(PayoutNotFound):
            services.cancel_payout("00000000-0000-4000-8000-000000000000", self.provider)

    def test_a_malformed_payout_id_is_a_not_found_rather_than_a_crash(self):
        with self.assertRaises(PayoutNotFound):
            services.cancel_payout("not-a-uuid", self.provider)


class PayoutConstraintTests(TestCase):
    """What the database refuses on a payout row, whatever wrote it."""

    def setUp(self):
        self.setup = earning_setup()
        self.provider = self.setup["provider"]

    def test_a_zero_amount_row_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PayoutRequest.objects.create(provider=self.provider, amount_kobo=0)

    def test_a_negative_amount_row_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PayoutRequest.objects.create(provider=self.provider, amount_kobo=-1)

    def test_two_in_flight_payouts_for_one_provider_are_refused(self):
        PayoutRequest.objects.create(provider=self.provider, amount_kobo=1)

        with self.assertRaises(IntegrityError), transaction.atomic():
            PayoutRequest.objects.create(provider=self.provider, amount_kobo=1)

    def test_a_resolved_payout_must_say_when(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PayoutRequest.objects.create(
                provider=self.provider, amount_kobo=1, status=PayoutStatus.PAID
            )

    def test_an_unresolved_payout_cannot_claim_to_have_been(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PayoutRequest.objects.create(
                provider=self.provider,
                amount_kobo=1,
                status=PayoutStatus.REQUESTED,
                processed_at=timezone.now(),
            )

    def test_only_a_failure_may_carry_a_reason(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PayoutRequest.objects.create(
                provider=self.provider,
                amount_kobo=1,
                status=PayoutStatus.PAID,
                processed_at=timezone.now(),
                failure_reason="It went fine, actually",
            )
