"""Provider identity verification.

The invariants worth holding are mostly negative: what a provider cannot do to
their own record, what a machine cannot do at all, and what a second copy of the
same vendor answer must not cause. Those are the tests that matter here; the happy
path is one of them.
"""

import contextlib

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.providers.identity.base import (
    CheckOutcome,
    IdentityCheckError,
    IdentityCheckRequest,
    IdentityCheckResult,
    IdentityMethod,
    get_identity_provider,
)
from apps.providers.identity.fake import (
    DECLINED,
    FAIL_FACE,
    FAIL_IDENTITY,
    FAIL_LIVENESS,
    PASS,
    UNAVAILABLE,
    FakeIdentityProvider,
)
from apps.providers.models import ProviderProfile, VerificationStatus
from apps.providers.services import (
    AlreadyApproved,
    AttemptNotReviewable,
    ContactNotVerified,
    IdentityProviderUnavailable,
    VerificationAlreadyOpen,
    apply_identity_result,
    approve,
    build_checklist,
    latest_attempt,
    reinstate,
    reject,
    resubmit,
    run_identity_check,
    start_verification,
    suspend,
)
from apps.providers.verification import (
    ALLOWED_AUDIT_KEYS,
    AttemptStatus,
    CheckStatus,
    IllegalAttemptTransition,
    ProviderVerification,
    sanitise_audit,
)

PASSWORD = "Lagos-Rider-2026"

CHECKLIST_URL = "/api/v1/provider/verification/checklist/"
STATUS_URL = "/api/v1/provider/verification/"
HISTORY_URL = "/api/v1/provider/verification/history/"
START_URL = "/api/v1/provider/verification/start/"
RESUBMIT_URL = "/api/v1/provider/verification/resubmit/"


def make_provider(email: str = "ada@example.com", *, contacts: bool = True) -> ProviderProfile:
    user = User.objects.create_user(email=email, password=PASSWORD)
    if contacts:
        user.email_verified_at = timezone.now()
        user.phone_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at", "phone_verified_at"])
    return ProviderProfile.objects.create(user=user, display_name="Ada Okafor")


def reviewer(email: str = "review@sync.ng") -> User:
    return User.objects.create_user(email=email, password=PASSWORD, is_staff=True)


def pass_identity(profile: ProviderProfile) -> ProviderVerification:
    return run_identity_check(profile, authorization_reference=PASS, consented=True)


# ---------------------------------------------------------------------------
# the adapter boundary
# ---------------------------------------------------------------------------


class IdentityAdapterTests(TestCase):
    def setUp(self):
        self.provider = FakeIdentityProvider()

    def request(self, reference: str) -> IdentityCheckRequest:
        return IdentityCheckRequest(
            provider_id="p-1",
            attempt_id="a-1",
            authorization_reference=reference,
            consent_notice_version="2026-08-v1",
        )

    def test_the_fake_refuses_anything_shaped_like_a_real_identifier(self):
        # The likeliest way real identity data reaches a development database is
        # somebody typing their own number in to see what happens.
        with self.assertRaises(IdentityCheckError):
            self.provider.check(self.request("12345678901"))

    def test_the_fake_refuses_an_unrecognised_reference(self):
        with self.assertRaises(IdentityCheckError):
            self.provider.check(self.request("whatever"))

    def test_a_clean_run_passes_all_three(self):
        result = self.provider.check(self.request(PASS))

        self.assertTrue(result.all_passed)
        self.assertEqual(result.method, IdentityMethod.NIN_AUTH)
        self.assertEqual(result.vendor, "FAKE")

    def test_each_failure_script_fails_its_own_check(self):
        for reference, field in (
            (FAIL_IDENTITY, "identity_outcome"),
            (FAIL_FACE, "face_match_outcome"),
            (FAIL_LIVENESS, "liveness_outcome"),
        ):
            with self.subTest(reference=reference):
                result = self.provider.check(self.request(reference))
                self.assertEqual(getattr(result, field), CheckOutcome.FAILED)
                self.assertFalse(result.all_passed)

    def test_an_outage_raises_rather_than_returning_a_failure(self):
        # An outage is not a fact about the person and must not be recorded as one.
        with self.assertRaises(IdentityCheckError):
            self.provider.check(self.request(UNAVAILABLE))

    def test_the_reference_is_stable_for_one_attempt(self):
        first = self.provider.check(self.request(PASS))
        second = self.provider.check(self.request(PASS))

        self.assertEqual(first.reference, second.reference)

    def test_a_result_cannot_carry_more_than_four_masked_characters(self):
        with self.assertRaises(ValueError):
            IdentityCheckResult(
                identity_outcome=CheckOutcome.PASSED,
                face_match_outcome=CheckOutcome.PASSED,
                liveness_outcome=CheckOutcome.PASSED,
                vendor="X",
                reference="R",
                method=IdentityMethod.NIN_AUTH,
                masked_identifier="12345678901",
            )

    def test_a_result_must_carry_a_reference(self):
        with self.assertRaises(ValueError):
            IdentityCheckResult(
                identity_outcome=CheckOutcome.PASSED,
                face_match_outcome=CheckOutcome.PASSED,
                liveness_outcome=CheckOutcome.PASSED,
                vendor="X",
                reference="",
                method=IdentityMethod.NIN_AUTH,
            )

    def test_the_configured_provider_is_the_fake_under_test(self):
        self.assertIsInstance(get_identity_provider(), FakeIdentityProvider)


class AuditSanitisingTests(TestCase):
    def test_unknown_keys_are_dropped(self):
        # This column is the one place a whole vendor payload could arrive.
        clean = sanitise_audit({"adapter": "fake", "nin": "12345678901", "selfie": "base64..."})

        self.assertEqual(set(clean), {"adapter"})

    def test_long_values_are_truncated(self):
        clean = sanitise_audit({"vendor_status": "x" * 500})

        self.assertLessEqual(len(clean["vendor_status"]), 120)

    def test_the_allowed_keys_carry_nothing_identifying(self):
        for key in ALLOWED_AUDIT_KEYS:
            self.assertNotIn("nin", key)
            self.assertNotIn("bvn", key)
            self.assertNotIn("image", key)


class VocabularyTests(TestCase):
    def test_the_stored_outcomes_mirror_the_vendor_facing_ones(self):
        # Two enums for one idea. If they drift, a vendor answer stops fitting the
        # column it is written to.
        self.assertEqual(sorted(choice.value for choice in CheckStatus), sorted(CheckOutcome.ALL))


# ---------------------------------------------------------------------------
# prerequisites and the checklist
# ---------------------------------------------------------------------------


class ChecklistTests(TestCase):
    def test_contacts_block_the_identity_check(self):
        profile = make_provider(contacts=False)

        checklist = build_checklist(profile)

        self.assertFalse(checklist.can_start_identity_check)
        self.assertEqual(checklist.blocked_reason, "CONTACT_NOT_VERIFIED")

    def test_one_contact_is_not_enough(self):
        profile = make_provider(contacts=False)
        profile.user.phone_verified_at = timezone.now()
        profile.user.save(update_fields=["phone_verified_at"])

        self.assertFalse(build_checklist(profile).can_start_identity_check)

    def test_both_contacts_unblock_it(self):
        profile = make_provider()

        checklist = build_checklist(profile)

        self.assertTrue(checklist.can_start_identity_check)
        self.assertEqual(checklist.blocked_reason, "")

    def test_the_checklist_reports_review_as_a_step_of_its_own(self):
        profile = make_provider()

        keys = [item.key for item in build_checklist(profile).items]

        self.assertEqual(keys, ["phone", "email", "identity", "biometrics", "review"])

    def test_awaiting_review_blocks_starting_again(self):
        profile = make_provider()
        pass_identity(profile)

        checklist = build_checklist(profile)

        self.assertFalse(checklist.can_start_identity_check)
        self.assertEqual(checklist.blocked_reason, "AWAITING_REVIEW")

    def test_the_checklist_is_only_complete_once_a_person_has_approved(self):
        profile = make_provider()
        attempt = pass_identity(profile)

        self.assertFalse(build_checklist(profile).complete)

        approve(attempt, reviewer=reviewer())
        profile.refresh_from_db()

        self.assertTrue(build_checklist(profile).complete)


class PrerequisiteTests(TestCase):
    def test_starting_without_contacts_is_refused(self):
        profile = make_provider(contacts=False)

        with self.assertRaises(ContactNotVerified):
            start_verification(profile)

    def test_running_a_check_without_contacts_is_refused(self):
        profile = make_provider(contacts=False)

        with self.assertRaises(ContactNotVerified):
            run_identity_check(profile, authorization_reference=PASS, consented=True)

    def test_a_check_without_consent_is_refused(self):
        profile = make_provider()

        with self.assertRaises(ContactNotVerified):
            run_identity_check(profile, authorization_reference=PASS, consented=False)

    def test_no_attempt_is_created_when_consent_is_withheld(self):
        profile = make_provider()

        with self.assertRaises(ContactNotVerified):
            run_identity_check(profile, authorization_reference=PASS, consented=False)

        self.assertEqual(profile.verification_attempts.count(), 0)


# ---------------------------------------------------------------------------
# the transitions
# ---------------------------------------------------------------------------


class IdentityCheckTests(TestCase):
    def setUp(self):
        self.profile = make_provider()

    def test_a_clean_check_reaches_review_and_stops_there(self):
        # The invariant the whole design rests on.
        attempt = pass_identity(self.profile)
        self.profile.refresh_from_db()

        self.assertEqual(attempt.status, AttemptStatus.UNDER_REVIEW)
        self.assertEqual(self.profile.verification_status, VerificationStatus.UNDER_REVIEW)
        self.assertNotEqual(self.profile.verification_status, VerificationStatus.APPROVED)

    def test_no_external_result_can_produce_an_approved_provider(self):
        for reference in (PASS, FAIL_FACE, FAIL_LIVENESS, FAIL_IDENTITY, DECLINED):
            with self.subTest(reference=reference):
                profile = make_provider(email=f"{reference}@example.com")
                # An outage on the way is fine; the point is what it cannot leave
                # behind.
                with contextlib.suppress(IdentityProviderUnavailable):
                    run_identity_check(profile, authorization_reference=reference, consented=True)
                profile.refresh_from_db()
                self.assertNotEqual(profile.verification_status, VerificationStatus.APPROVED)

    def test_a_failed_face_match_does_not_reach_review(self):
        attempt = run_identity_check(
            self.profile, authorization_reference=FAIL_FACE, consented=True
        )
        self.profile.refresh_from_db()

        self.assertEqual(attempt.status, AttemptStatus.CHECK_FAILED)
        self.assertEqual(attempt.face_match_status, CheckStatus.FAILED)
        self.assertEqual(self.profile.verification_status, VerificationStatus.PENDING)

    def test_a_failed_liveness_does_not_reach_review(self):
        attempt = run_identity_check(
            self.profile, authorization_reference=FAIL_LIVENESS, consented=True
        )

        self.assertEqual(attempt.status, AttemptStatus.CHECK_FAILED)
        self.assertEqual(attempt.liveness_status, CheckStatus.FAILED)

    def test_all_three_must_pass_to_reach_review(self):
        attempt = pass_identity(self.profile)

        self.assertTrue(attempt.all_checks_passed)
        self.assertEqual(attempt.failed_checks, [])

    def test_a_vendor_outage_leaves_the_attempt_retryable(self):
        with self.assertRaises(IdentityProviderUnavailable):
            run_identity_check(self.profile, authorization_reference=UNAVAILABLE, consented=True)

        attempt = latest_attempt(self.profile)
        self.assertEqual(attempt.status, AttemptStatus.CHECK_FAILED)
        # Nothing about the person was recorded.
        self.assertEqual(attempt.identity_check_status, CheckStatus.PENDING)
        self.assertEqual(attempt.identity_reference, "")

    def test_a_failed_check_can_be_retried_on_the_same_attempt(self):
        run_identity_check(self.profile, authorization_reference=FAIL_FACE, consented=True)

        attempt = pass_identity(self.profile)

        self.assertEqual(attempt.status, AttemptStatus.UNDER_REVIEW)
        self.assertEqual(self.profile.verification_attempts.count(), 1)

    def test_only_four_masked_characters_are_stored(self):
        attempt = pass_identity(self.profile)

        self.assertLessEqual(len(attempt.masked_identifier), 4)

    def test_the_consent_notice_version_is_recorded(self):
        attempt = pass_identity(self.profile)

        self.assertTrue(attempt.consent_notice_version)
        self.assertIsNotNone(attempt.consented_at)

    def test_starting_twice_returns_the_same_open_attempt(self):
        first = start_verification(self.profile)
        second = start_verification(self.profile)

        self.assertEqual(first.id, second.id)
        self.assertEqual(self.profile.verification_attempts.count(), 1)

    def test_starting_while_under_review_is_refused(self):
        pass_identity(self.profile)

        with self.assertRaises(VerificationAlreadyOpen):
            start_verification(self.profile)


class ReplayTests(TestCase):
    """A vendor answer that arrives twice is one check, not two."""

    def setUp(self):
        self.profile = make_provider()

    def test_the_same_reference_applied_twice_changes_nothing(self):
        attempt = pass_identity(self.profile)
        checked_at = attempt.identity_checked_at

        result = FakeIdentityProvider().check(
            IdentityCheckRequest(
                provider_id=str(self.profile.id),
                attempt_id=str(attempt.id),
                authorization_reference=PASS,
                consent_notice_version="2026-08-v1",
            )
        )
        again = apply_identity_result(attempt, result)

        self.assertEqual(again.identity_checked_at, checked_at)
        self.assertEqual(again.status, AttemptStatus.UNDER_REVIEW)

    def test_a_late_result_cannot_reopen_a_decided_attempt(self):
        attempt = pass_identity(self.profile)
        approve(attempt, reviewer=reviewer())
        attempt.refresh_from_db()

        late = IdentityCheckResult(
            identity_outcome=CheckOutcome.FAILED,
            face_match_outcome=CheckOutcome.FAILED,
            liveness_outcome=CheckOutcome.FAILED,
            vendor="FAKE",
            reference="SOMETHING-ELSE",
            method=IdentityMethod.NIN_AUTH,
        )
        unchanged = apply_identity_result(attempt, late)

        self.assertEqual(unchanged.status, AttemptStatus.APPROVED)
        self.assertEqual(unchanged.identity_check_status, CheckStatus.PASSED)

    def test_a_terminal_attempt_refuses_every_transition(self):
        attempt = pass_identity(self.profile)
        approve(attempt, reviewer=reviewer())
        attempt.refresh_from_db()

        for target in AttemptStatus.values:
            with self.subTest(target=target), self.assertRaises(IllegalAttemptTransition):
                attempt.transition(target)


# ---------------------------------------------------------------------------
# review, resubmission and suspension
# ---------------------------------------------------------------------------


class ReviewTests(TestCase):
    def setUp(self):
        self.profile = make_provider()
        self.reviewer = reviewer()

    def test_approval_is_the_only_route_to_an_approved_provider(self):
        attempt = pass_identity(self.profile)

        approve(attempt, reviewer=self.reviewer)
        self.profile.refresh_from_db()

        self.assertEqual(self.profile.verification_status, VerificationStatus.APPROVED)

    def test_approval_records_who_decided(self):
        attempt = pass_identity(self.profile)

        approved = approve(attempt, reviewer=self.reviewer, note="Checked.")

        self.assertEqual(approved.reviewed_by, self.reviewer)
        self.assertIsNotNone(approved.reviewed_at)

    def test_an_attempt_that_never_reached_review_cannot_be_approved(self):
        attempt = run_identity_check(
            self.profile, authorization_reference=FAIL_FACE, consented=True
        )

        with self.assertRaises(AttemptNotReviewable):
            approve(attempt, reviewer=self.reviewer)

    def test_rejection_needs_a_reason(self):
        attempt = pass_identity(self.profile)

        with self.assertRaises(AttemptNotReviewable):
            reject(attempt, reviewer=self.reviewer, note="   ")

    def test_rejection_moves_the_profile_and_keeps_the_note(self):
        attempt = pass_identity(self.profile)

        rejected = reject(attempt, reviewer=self.reviewer, note="Name does not match.")
        self.profile.refresh_from_db()

        self.assertEqual(rejected.status, AttemptStatus.REJECTED)
        self.assertEqual(self.profile.verification_status, VerificationStatus.REJECTED)
        self.assertEqual(rejected.review_note, "Name does not match.")

    def test_approving_twice_is_refused(self):
        attempt = pass_identity(self.profile)
        approve(attempt, reviewer=self.reviewer)

        with self.assertRaises(AttemptNotReviewable):
            approve(attempt, reviewer=self.reviewer)


class ResubmissionTests(TestCase):
    def setUp(self):
        self.profile = make_provider()
        self.reviewer = reviewer()

    def test_resubmission_creates_a_new_row(self):
        first = pass_identity(self.profile)
        reject(first, reviewer=self.reviewer, note="Try again.")

        second = resubmit(self.profile)

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(self.profile.verification_attempts.count(), 2)

    def test_the_rejected_attempt_survives_untouched(self):
        first = pass_identity(self.profile)
        reject(first, reviewer=self.reviewer, note="Name does not match.")
        first.refresh_from_db()

        resubmit(self.profile)
        run_identity_check(self.profile, authorization_reference=PASS, consented=True)
        first.refresh_from_db()

        self.assertEqual(first.status, AttemptStatus.REJECTED)
        self.assertEqual(first.review_note, "Name does not match.")
        self.assertEqual(first.reviewed_by, self.reviewer)

    def test_resubmitting_while_one_is_open_is_refused(self):
        pass_identity(self.profile)

        with self.assertRaises(VerificationAlreadyOpen):
            resubmit(self.profile)

    def test_an_approved_provider_cannot_resubmit(self):
        attempt = pass_identity(self.profile)
        approve(attempt, reviewer=self.reviewer)
        self.profile.refresh_from_db()

        with self.assertRaises(AlreadyApproved):
            resubmit(self.profile)


class SuspensionTests(TestCase):
    def setUp(self):
        self.profile = make_provider()
        self.reviewer = reviewer()
        attempt = pass_identity(self.profile)
        approve(attempt, reviewer=self.reviewer)
        self.profile.refresh_from_db()

    def test_suspension_also_switches_them_off(self):
        self.profile.is_accepting_jobs = True
        self.profile.save(update_fields=["is_accepting_jobs"])

        suspend(self.profile, reviewer=self.reviewer)
        self.profile.refresh_from_db()

        self.assertEqual(self.profile.verification_status, VerificationStatus.SUSPENDED)
        self.assertFalse(self.profile.is_accepting_jobs)

    def test_reinstating_leaves_them_switched_off(self):
        suspend(self.profile, reviewer=self.reviewer)
        self.profile.refresh_from_db()

        reinstate(self.profile, reviewer=self.reviewer)
        self.profile.refresh_from_db()

        self.assertEqual(self.profile.verification_status, VerificationStatus.APPROVED)
        self.assertFalse(self.profile.is_accepting_jobs)

    def test_a_pending_provider_cannot_be_suspended(self):
        other = make_provider(email="new@example.com")

        with self.assertRaises(ValidationError):
            suspend(other, reviewer=self.reviewer)


# ---------------------------------------------------------------------------
# the API
# ---------------------------------------------------------------------------


class VerificationApiTests(APITestCase):
    def setUp(self):
        self.profile = make_provider()
        self.client.force_authenticate(self.profile.user)

    def test_every_endpoint_requires_authentication(self):
        self.client.force_authenticate(None)

        for url in (CHECKLIST_URL, STATUS_URL, HISTORY_URL):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)
        for url in (START_URL, RESUBMIT_URL):
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.post(url, {}, format="json").status_code,
                    status.HTTP_401_UNAUTHORIZED,
                )

    def test_an_account_without_a_provider_profile_gets_a_clear_404(self):
        outsider = User.objects.create_user(email="nobody@example.com", password=PASSWORD)
        self.client.force_authenticate(outsider)

        response = self.client.get(CHECKLIST_URL)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_checklist_is_server_computed(self):
        response = self.client.get(CHECKLIST_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(
            [item["key"] for item in body["items"]],
            ["phone", "email", "identity", "biometrics", "review"],
        )
        self.assertTrue(body["can_start_identity_check"])

    def test_starting_runs_the_check_and_returns_the_attempt(self):
        response = self.client.post(
            START_URL, {"authorization_reference": PASS, "consent": True}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["status"], AttemptStatus.UNDER_REVIEW)

    def test_the_api_never_returns_an_approved_provider_from_a_check(self):
        self.client.post(
            START_URL, {"authorization_reference": PASS, "consent": True}, format="json"
        )
        self.profile.refresh_from_db()

        self.assertEqual(self.profile.verification_status, VerificationStatus.UNDER_REVIEW)

    def test_a_real_looking_identifier_is_rejected_before_any_adapter_sees_it(self):
        response = self.client.post(
            START_URL,
            {"authorization_reference": "my nin is 12345678901", "consent": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.profile.verification_attempts.count(), 0)

    def test_consent_is_required(self):
        response = self.client.post(
            START_URL, {"authorization_reference": PASS, "consent": False}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_contacts_must_be_verified_first(self):
        unverified = make_provider(email="raw@example.com", contacts=False)
        self.client.force_authenticate(unverified.user)

        response = self.client.post(
            START_URL, {"authorization_reference": PASS, "consent": True}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["error"]["code"], "CONTACT_NOT_VERIFIED")

    def test_status_is_404_before_anything_has_been_started(self):
        response = self.client.get(STATUS_URL)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_history_lists_every_attempt(self):
        first = pass_identity(self.profile)
        reject(first, reviewer=reviewer(), note="Try again.")
        resubmit(self.profile)

        response = self.client.get(HISTORY_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 2)

    def test_a_provider_only_ever_sees_their_own_attempts(self):
        pass_identity(self.profile)
        other = make_provider(email="other@example.com")
        pass_identity(other)

        self.client.force_authenticate(other.user)
        body = self.client.get(HISTORY_URL).json()

        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["id"], str(latest_attempt(other).id))


class ProviderCannotSelfApproveTests(APITestCase):
    """The whole point of the authorization design, stated as tests."""

    def setUp(self):
        self.profile = make_provider()
        self.client.force_authenticate(self.profile.user)

    def test_posting_a_status_to_the_start_endpoint_is_ignored(self):
        self.client.post(
            START_URL,
            {
                "authorization_reference": PASS,
                "consent": True,
                "status": AttemptStatus.APPROVED,
                "identity_check_status": CheckStatus.PASSED,
            },
            format="json",
        )
        self.profile.refresh_from_db()

        self.assertEqual(self.profile.verification_status, VerificationStatus.UNDER_REVIEW)
        self.assertEqual(latest_attempt(self.profile).status, AttemptStatus.UNDER_REVIEW)

    def test_posting_review_fields_is_ignored(self):
        self.client.post(
            START_URL,
            {
                "authorization_reference": PASS,
                "consent": True,
                "reviewed_by": str(self.profile.user.id),
                "review_note": "I approve myself.",
                "rejection_code": "",
            },
            format="json",
        )

        attempt = latest_attempt(self.profile)
        self.assertIsNone(attempt.reviewed_by)
        self.assertEqual(attempt.review_note, "")

    def test_the_profile_endpoint_still_refuses_a_verification_status(self):
        self.client.patch(
            "/api/v1/provider/profile/",
            {"verification_status": VerificationStatus.APPROVED},
            format="json",
        )
        self.profile.refresh_from_db()

        self.assertEqual(self.profile.verification_status, VerificationStatus.PENDING)

    def test_no_provider_endpoint_exposes_a_write_for_an_outcome(self):
        from apps.providers.verification_serializers import ProviderVerificationSerializer

        serializer = ProviderVerificationSerializer()

        self.assertEqual(
            [name for name, field in serializer.fields.items() if not field.read_only], []
        )


class SafeSerializationTests(APITestCase):
    def setUp(self):
        self.profile = make_provider()
        self.client.force_authenticate(self.profile.user)
        self.attempt = pass_identity(self.profile)

    def test_the_payload_carries_no_identifier_token_or_image(self):
        body = self.client.get(STATUS_URL).json()

        for forbidden in (
            "nin",
            "bvn",
            "selfie",
            "portrait",
            "image",
            "photo",
            "token",
            "authorization",
            "raw",
            "payload",
            "biometric",
        ):
            with self.subTest(field=forbidden):
                self.assertNotIn(forbidden, " ".join(body).lower())

    def test_the_masked_identifier_is_four_characters_at_most(self):
        body = self.client.get(STATUS_URL).json()

        self.assertLessEqual(len(body["masked_identifier"]), 4)

    def test_the_reviewer_is_not_named_to_the_provider(self):
        reject(self.attempt, reviewer=reviewer(), note="No.")

        body = self.client.get(STATUS_URL).json()

        self.assertNotIn("reviewed_by", body)
        self.assertTrue(body["reviewed"])


# ---------------------------------------------------------------------------
# production refusal
# ---------------------------------------------------------------------------


class ProductionRefusesTheFakeTests(TestCase):
    def test_production_refuses_to_boot_with_the_fake_identity_provider(self):
        from apps.common.checks import check_providers_are_real

        with override_settings(
            IS_PRODUCTION=True,
            IDENTITY_PROVIDER="apps.providers.identity.fake.FakeIdentityProvider",
        ):
            problems = check_providers_are_real(None)

        identity = [problem for problem in problems if "IDENTITY_PROVIDER" in str(problem.msg)]
        self.assertTrue(identity)
        self.assertTrue(all(problem.is_serious() for problem in identity))

    def test_a_real_looking_identity_provider_passes(self):
        from apps.common.checks import check_providers_are_real

        with override_settings(
            IS_PRODUCTION=True,
            IDENTITY_PROVIDER="apps.providers.identity.prembly.PremblyIdentityProvider",
        ):
            problems = check_providers_are_real(None)

        self.assertFalse([p for p in problems if "IDENTITY_PROVIDER" in str(p.msg)])

    def test_the_check_is_inert_outside_production(self):
        from apps.common.checks import check_providers_are_real

        self.assertEqual(check_providers_are_real(None), [])
