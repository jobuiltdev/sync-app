from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.accounts.models import User
from apps.catalog.tests.factories import make_service
from apps.providers.models import (
    ALLOWED_TRANSITIONS,
    IllegalTransition,
    ProviderProfile,
    ProviderService,
    ProviderServiceArea,
    VerificationStatus,
    can_transition,
)

PASSWORD = "Lagos-Rider-2026"


def make_provider(email: str = "provider@example.com", **overrides) -> ProviderProfile:
    user = User.objects.create_user(email=email, password=PASSWORD)
    defaults = {"user": user, "display_name": "Ada's Cleaning"}
    return ProviderProfile.objects.create(**{**defaults, **overrides})


class ProviderProfileTests(TestCase):
    def test_creating_a_profile_is_what_makes_an_account_a_provider(self):
        provider = make_provider()

        self.assertEqual(provider.user.provider_profile, provider)

    def test_a_user_may_have_only_one_provider_profile(self):
        provider = make_provider()

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderProfile.objects.create(user=provider.user, display_name="Second")

    def test_new_providers_start_pending_and_not_taking_work(self):
        provider = make_provider()

        self.assertEqual(provider.verification_status, VerificationStatus.PENDING)
        self.assertFalse(provider.is_accepting_jobs)
        self.assertFalse(provider.is_approved)

    def test_display_name_cannot_be_empty(self):
        user = User.objects.create_user(email="x@example.com", password=PASSWORD)

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderProfile.objects.create(user=user, display_name="")

    def test_deleting_the_user_removes_the_provider_profile(self):
        provider = make_provider()
        user = provider.user

        user.delete()

        self.assertFalse(ProviderProfile.objects.filter(pk=provider.pk).exists())


class VerificationLifecycleTests(TestCase):
    def test_the_happy_path_runs_to_approved(self):
        provider = make_provider()

        provider.transition_verification(VerificationStatus.UNDER_REVIEW)
        provider.transition_verification(VerificationStatus.APPROVED)

        provider.refresh_from_db()
        self.assertEqual(provider.verification_status, VerificationStatus.APPROVED)
        self.assertTrue(provider.is_approved)

    def test_a_rejected_provider_can_resubmit(self):
        provider = make_provider()
        provider.transition_verification(VerificationStatus.UNDER_REVIEW)
        provider.transition_verification(VerificationStatus.REJECTED)

        provider.transition_verification(VerificationStatus.UNDER_REVIEW)

        self.assertEqual(provider.verification_status, VerificationStatus.UNDER_REVIEW)

    def test_an_approved_provider_can_be_suspended_and_reinstated(self):
        provider = make_provider()
        provider.transition_verification(VerificationStatus.UNDER_REVIEW)
        provider.transition_verification(VerificationStatus.APPROVED)

        provider.transition_verification(VerificationStatus.SUSPENDED)
        provider.transition_verification(VerificationStatus.APPROVED)

        self.assertTrue(provider.is_approved)

    def test_a_pending_provider_cannot_jump_straight_to_approved(self):
        # The whole purpose of the lifecycle: approval must pass through review.
        provider = make_provider()

        with self.assertRaises(IllegalTransition):
            provider.transition_verification(VerificationStatus.APPROVED)

    def test_a_refused_transition_is_not_persisted(self):
        provider = make_provider()

        with self.assertRaises(IllegalTransition):
            provider.transition_verification(VerificationStatus.APPROVED)

        provider.refresh_from_db()
        self.assertEqual(provider.verification_status, VerificationStatus.PENDING)

    def test_a_suspended_provider_cannot_be_moved_back_into_review(self):
        provider = make_provider()
        provider.transition_verification(VerificationStatus.UNDER_REVIEW)
        provider.transition_verification(VerificationStatus.APPROVED)
        provider.transition_verification(VerificationStatus.SUSPENDED)

        with self.assertRaises(IllegalTransition):
            provider.transition_verification(VerificationStatus.UNDER_REVIEW)

    def test_a_status_cannot_transition_to_itself(self):
        provider = make_provider()

        with self.assertRaises(IllegalTransition):
            provider.transition_verification(VerificationStatus.PENDING)

    def test_the_error_names_what_would_have_been_allowed(self):
        provider = make_provider()

        with self.assertRaises(ValidationError) as caught:
            provider.transition_verification(VerificationStatus.APPROVED)

        self.assertIn("UNDER_REVIEW", str(caught.exception))

    def test_every_status_appears_in_the_transition_table(self):
        # A status missing from the table would be a dead end reachable only by a
        # direct database write.
        self.assertEqual(set(ALLOWED_TRANSITIONS), set(VerificationStatus.values))

    def test_no_transition_targets_an_unknown_status(self):
        for targets in ALLOWED_TRANSITIONS.values():
            self.assertTrue(targets <= set(VerificationStatus.values))

    def test_can_transition_reports_without_mutating(self):
        self.assertTrue(can_transition(VerificationStatus.PENDING, VerificationStatus.UNDER_REVIEW))
        self.assertFalse(can_transition(VerificationStatus.PENDING, VerificationStatus.APPROVED))


class ProviderServiceTests(TestCase):
    def setUp(self):
        self.provider = make_provider()
        self.service = make_service()

    def test_a_provider_offers_a_service(self):
        offered = ProviderService.objects.create(provider=self.provider, service=self.service)

        self.assertEqual(list(self.provider.offered_services.all()), [offered])

    def test_a_provider_cannot_offer_the_same_service_twice(self):
        ProviderService.objects.create(provider=self.provider, service=self.service)

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderService.objects.create(provider=self.provider, service=self.service)

    def test_falls_back_to_the_catalog_price_when_there_is_no_override(self):
        offered = ProviderService.objects.create(provider=self.provider, service=self.service)

        self.assertEqual(offered.effective_price_kobo, self.service.base_price_kobo)

    def test_an_override_of_zero_is_respected_rather_than_treated_as_unset(self):
        # Null and zero mean different things: no override, versus free.
        offered = ProviderService.objects.create(
            provider=self.provider, service=self.service, price_override_kobo=0
        )

        self.assertEqual(offered.effective_price_kobo, 0)

    def test_an_override_cannot_be_negative(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderService.objects.create(
                provider=self.provider, service=self.service, price_override_kobo=-1
            )

    def test_a_service_offered_by_providers_cannot_be_deleted(self):
        ProviderService.objects.create(provider=self.provider, service=self.service)

        with self.assertRaises(ProtectedError):
            self.service.delete()

    def test_deleting_the_provider_removes_their_offers(self):
        ProviderService.objects.create(provider=self.provider, service=self.service)

        self.provider.delete()

        self.assertEqual(ProviderService.objects.count(), 0)


class ProviderServiceAreaTests(TestCase):
    def setUp(self):
        self.provider = make_provider()

    def test_a_provider_covers_an_area(self):
        area = ProviderServiceArea.objects.create(
            provider=self.provider, state="LAGOS", lga="Ikeja"
        )

        self.assertEqual(str(area), "Lagos / Ikeja")

    def test_a_blank_lga_means_the_whole_state(self):
        area = ProviderServiceArea.objects.create(provider=self.provider, state="LAGOS")

        self.assertEqual(str(area), "Lagos")

    def test_the_same_area_cannot_be_added_twice(self):
        ProviderServiceArea.objects.create(provider=self.provider, state="LAGOS", lga="Ikeja")

        with self.assertRaises(IntegrityError), transaction.atomic():
            ProviderServiceArea.objects.create(provider=self.provider, state="LAGOS", lga="Ikeja")

    def test_a_whole_state_and_an_lga_within_it_are_distinct_rows(self):
        ProviderServiceArea.objects.create(provider=self.provider, state="LAGOS")
        ProviderServiceArea.objects.create(provider=self.provider, state="LAGOS", lga="Ikeja")

        self.assertEqual(self.provider.service_areas.count(), 2)
