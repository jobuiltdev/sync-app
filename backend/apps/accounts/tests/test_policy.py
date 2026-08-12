from django.test import TestCase
from django.utils import timezone

from apps.accounts import policy
from apps.accounts.errors import VerificationRequired
from apps.accounts.models import User

PASSWORD = "Lagos-Rider-2026"


def make_user(*, phone: bool = False, email: bool = False) -> User:
    user = User.objects.create_user(email="ada@example.com", password=PASSWORD)
    if phone:
        user.phone_verified_at = timezone.now()
    if email:
        user.email_verified_at = timezone.now()
    user.save()
    return user


class PolicyCheckTests(TestCase):
    """The policy is exercised directly, without going near a booking.

    That is the point of it living in accounts: M4 and M5 will add capabilities and
    must be able to ask the same question without importing the booking domain.
    """

    def test_a_verified_phone_grants_booking(self):
        result = policy.check(make_user(phone=True), policy.Capability.CREATE_BOOKING)

        self.assertTrue(result.allowed)
        self.assertEqual(result.unmet, [])

    def test_an_unverified_phone_withholds_booking(self):
        result = policy.check(make_user(), policy.Capability.CREATE_BOOKING)

        self.assertFalse(result.allowed)
        self.assertEqual(result.unmet, [policy.Requirement.PHONE_VERIFIED])

    def test_email_verification_alone_does_not_grant_booking(self):
        result = policy.check(make_user(email=True), policy.Capability.CREATE_BOOKING)

        self.assertFalse(result.allowed)

    def test_email_verification_is_not_required_for_booking(self):
        # Deliberate: a provider on the way needs to phone the customer. An email
        # address does nothing for that, and demanding both costs conversion at the
        # moment the customer is ready to commit.
        result = policy.check(make_user(phone=True), policy.Capability.CREATE_BOOKING)

        self.assertTrue(result.allowed)
        self.assertNotIn(policy.Requirement.EMAIL_VERIFIED, result.unmet)

    def test_the_result_reports_what_is_already_satisfied(self):
        result = policy.check(make_user(phone=True), policy.Capability.CREATE_BOOKING)

        self.assertEqual(result.satisfied, [policy.Requirement.PHONE_VERIFIED])

    def test_check_never_mutates_the_user(self):
        user = make_user()

        policy.check(user, policy.Capability.CREATE_BOOKING)

        user.refresh_from_db()
        self.assertIsNone(user.phone_verified_at)

    def test_details_name_the_capability_and_the_next_step(self):
        result = policy.check(make_user(), policy.Capability.CREATE_BOOKING)

        details = result.as_details()
        self.assertEqual(details["capability"], policy.Capability.CREATE_BOOKING)
        self.assertEqual(details["unmet"], [policy.Requirement.PHONE_VERIFIED])
        self.assertIn("verification/request", details["next_step"]["action"])

    def test_a_satisfied_result_carries_no_next_step(self):
        result = policy.check(make_user(phone=True), policy.Capability.CREATE_BOOKING)

        self.assertNotIn("next_step", result.as_details())


class PolicyEnforceTests(TestCase):
    def test_enforce_is_silent_when_the_capability_is_held(self):
        policy.enforce(make_user(phone=True), policy.Capability.CREATE_BOOKING)

    def test_enforce_raises_with_the_specific_code(self):
        with self.assertRaises(VerificationRequired) as caught:
            policy.enforce(make_user(), policy.Capability.CREATE_BOOKING)

        self.assertEqual(caught.exception.details["unmet"], [policy.Requirement.PHONE_VERIFIED])

    def test_the_error_is_a_403_not_a_401(self):
        # 401 would tell the app to sign the user out. They are signed in fine;
        # they simply have not proven a phone number yet.
        with self.assertRaises(VerificationRequired) as caught:
            policy.enforce(make_user(), policy.Capability.CREATE_BOOKING)

        self.assertEqual(caught.exception.status_code, 403)


class PolicyTableTests(TestCase):
    def test_every_capability_has_a_requirement_list(self):
        self.assertEqual(set(policy.CAPABILITY_REQUIREMENTS), set(policy.Capability.values))

    def test_every_requirement_referenced_is_a_known_requirement(self):
        for requirements in policy.CAPABILITY_REQUIREMENTS.values():
            for requirement in requirements:
                self.assertIn(requirement, policy.Requirement.values)

    def test_every_requirement_can_be_evaluated(self):
        user = make_user()
        for requirement in policy.Requirement.values:
            policy._is_satisfied(user, requirement)

    def test_an_unknown_requirement_is_a_loud_failure(self):
        with self.assertRaises(ValueError):
            policy._is_satisfied(make_user(), "TELEPORTATION_VERIFIED")
