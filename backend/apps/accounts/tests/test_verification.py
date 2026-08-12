from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts import verification
from apps.accounts.errors import (
    InvalidVerificationCode,
    PhoneAlreadyVerified,
    PhoneNotSet,
    VerificationChallengeNotFound,
    VerificationCooldown,
    VerificationExhausted,
    VerificationExpired,
)
from apps.accounts.models import User, VerificationChallenge
from apps.accounts.sms.locmem import LocMemSMSProvider
from config.settings import base as settings_base

PASSWORD = "Lagos-Rider-2026"
LOCMEM = "apps.accounts.sms.locmem.LocMemSMSProvider"
FAILING = "apps.accounts.sms.failing.FailingSMSProvider"


def make_user(phone: str | None = "08031234567", **extra) -> User:
    return User.objects.create_user(
        email=f"user{User.objects.count()}@example.com", password=PASSWORD, phone=phone, **extra
    )


@override_settings(SMS_BACKEND=LOCMEM)
class VerificationBase(TestCase):
    def setUp(self):
        LocMemSMSProvider.clear()
        self.user = make_user()

    def issue(self) -> tuple[VerificationChallenge, str]:
        """Requests a challenge and returns it with the code the provider received."""
        result = verification.request_phone_verification(self.user)
        sent = LocMemSMSProvider.last()
        assert sent is not None
        return result.challenge, sent.code


class CodeGenerationTests(TestCase):
    def test_generates_a_code_of_the_configured_length(self):
        self.assertEqual(len(verification.generate_code(6)), 6)

    def test_the_code_is_numeric(self):
        self.assertTrue(verification.generate_code(6).isdigit())

    def test_leading_zeros_are_preserved(self):
        # Built digit by digit rather than by formatting an integer, which would
        # drop a leading zero and quietly shrink the keyspace.
        codes = [verification.generate_code(6) for _ in range(400)]

        self.assertTrue(any(code.startswith("0") for code in codes))

    def test_codes_are_not_repeated_in_a_short_run(self):
        codes = {verification.generate_code(6) for _ in range(200)}

        self.assertGreater(len(codes), 190)


class ChallengeModelTests(VerificationBase):
    def test_a_challenge_is_created_for_the_users_normalised_phone(self):
        challenge, _ = self.issue()

        self.assertEqual(challenge.destination, "+2348031234567")
        self.assertEqual(challenge.user, self.user)

    def test_the_plaintext_code_is_never_persisted(self):
        challenge, code = self.issue()

        challenge.refresh_from_db()
        self.assertNotIn(code, challenge.code_hash)
        self.assertNotEqual(challenge.code_hash, code)

    @override_settings(PASSWORD_HASHERS=settings_base.PASSWORD_HASHERS)
    def test_the_hash_uses_the_projects_password_hasher(self):
        # Read against the production hashers, because the test settings swap in
        # MD5 for speed and would otherwise hide what is actually used.
        challenge, _ = self.issue()

        self.assertTrue(challenge.code_hash.startswith("argon2$"), challenge.code_hash[:20])

    def test_no_column_anywhere_holds_the_code(self):
        _, code = self.issue()

        row = VerificationChallenge.objects.values().get()
        self.assertNotIn(code, " ".join(str(v) for v in row.values()))

    def test_a_new_challenge_is_usable(self):
        challenge, _ = self.issue()

        self.assertTrue(challenge.is_usable)
        self.assertFalse(challenge.is_consumed)
        self.assertFalse(challenge.is_expired)
        self.assertFalse(challenge.is_exhausted)

    def test_expiry_follows_the_configured_ttl(self):
        challenge, _ = self.issue()

        expected = challenge.created_at + timedelta(seconds=verification.config()["TTL_SECONDS"])
        self.assertAlmostEqual(challenge.expires_at, expected, delta=timedelta(seconds=5))

    def test_attempts_start_at_zero(self):
        challenge, _ = self.issue()

        self.assertEqual(challenge.attempt_count, 0)
        self.assertEqual(challenge.attempts_remaining, challenge.max_attempts)

    def test_deleting_the_user_removes_their_challenges(self):
        self.issue()

        self.user.delete()

        self.assertEqual(VerificationChallenge.objects.count(), 0)


@override_settings(SMS_BACKEND=LOCMEM)
class RequestVerificationTests(VerificationBase):
    def test_sends_the_code_to_the_normalised_number(self):
        self.issue()

        self.assertEqual(LocMemSMSProvider.last().phone, "+2348031234567")

    def test_sends_exactly_one_message(self):
        self.issue()

        self.assertEqual(len(LocMemSMSProvider.sent), 1)

    def test_requesting_a_code_does_not_verify_anything(self):
        self.issue()

        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)

    def test_an_account_without_a_phone_is_refused(self):
        user = User.objects.create_user(email="nophone@example.com", password=PASSWORD)

        with self.assertRaises(PhoneNotSet):
            verification.request_phone_verification(user)

    def test_an_already_verified_phone_is_refused_rather_than_resent(self):
        self.user.phone_verified_at = timezone.now()
        self.user.save()

        with self.assertRaises(PhoneAlreadyVerified):
            verification.request_phone_verification(self.user)

        self.assertEqual(len(LocMemSMSProvider.sent), 0)

    def test_a_second_request_inside_the_cooldown_is_refused(self):
        self.issue()

        with self.assertRaises(VerificationCooldown):
            verification.request_phone_verification(self.user)

    def test_the_cooldown_refusal_says_how_long_to_wait(self):
        self.issue()

        with self.assertRaises(VerificationCooldown) as caught:
            verification.request_phone_verification(self.user)

        self.assertGreater(caught.exception.details["retry_after_seconds"], 0)

    def test_the_provider_is_not_called_when_the_cooldown_blocks_the_request(self):
        self.issue()

        with self.assertRaises(VerificationCooldown):
            verification.request_phone_verification(self.user)

        self.assertEqual(len(LocMemSMSProvider.sent), 1)

    def test_a_request_after_the_cooldown_is_allowed(self):
        challenge, _ = self.issue()
        VerificationChallenge.objects.filter(pk=challenge.pk).update(
            last_sent_at=timezone.now() - timedelta(seconds=120)
        )

        verification.request_phone_verification(self.user)

        self.assertEqual(len(LocMemSMSProvider.sent), 2)

    def test_a_new_challenge_supersedes_the_previous_one(self):
        # Only one code is ever live, so a code overheard earlier cannot be used
        # after a resend.
        first, first_code = self.issue()
        VerificationChallenge.objects.filter(pk=first.pk).update(
            last_sent_at=timezone.now() - timedelta(seconds=120)
        )

        verification.request_phone_verification(self.user)

        first.refresh_from_db()
        self.assertTrue(first.is_superseded)
        with self.assertRaises(VerificationChallengeNotFound):
            verification.confirm_phone_verification(self.user, first.id, first_code)

    def test_too_many_sends_in_the_window_are_refused(self):
        for _ in range(verification.config()["MAX_SENDS_PER_WINDOW"]):
            verification.request_phone_verification(self.user)
            VerificationChallenge.objects.filter(user=self.user).update(
                last_sent_at=timezone.now() - timedelta(seconds=120)
            )

        with self.assertRaises(VerificationCooldown):
            verification.request_phone_verification(self.user)

    @override_settings(SMS_BACKEND=FAILING)
    def test_a_provider_failure_leaves_no_challenge_behind(self):
        # A challenge left after a failed send would ask the customer for a code
        # that never arrived, and would burn their cooldown for nothing.
        from apps.accounts.sms.base import SMSDeliveryError

        with self.assertRaises(SMSDeliveryError):
            verification.request_phone_verification(self.user)

        self.assertEqual(VerificationChallenge.objects.count(), 0)

    @override_settings(SMS_BACKEND=FAILING)
    def test_a_provider_failure_never_verifies_the_phone(self):
        from apps.accounts.sms.base import SMSDeliveryError

        with self.assertRaises(SMSDeliveryError):
            verification.request_phone_verification(self.user)

        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)


@override_settings(SMS_BACKEND=LOCMEM)
class ConfirmVerificationTests(VerificationBase):
    def test_the_correct_code_verifies_the_phone(self):
        challenge, code = self.issue()

        verification.confirm_phone_verification(self.user, challenge.id, code)

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.phone_verified_at)
        self.assertTrue(self.user.is_phone_verified)

    def test_a_successful_verification_consumes_the_challenge(self):
        challenge, code = self.issue()

        verification.confirm_phone_verification(self.user, challenge.id, code)

        challenge.refresh_from_db()
        self.assertTrue(challenge.is_consumed)
        self.assertFalse(challenge.is_usable)

    def test_the_same_code_cannot_be_used_twice(self):
        challenge, code = self.issue()
        verification.confirm_phone_verification(self.user, challenge.id, code)

        with self.assertRaises(VerificationChallengeNotFound):
            verification.confirm_phone_verification(self.user, challenge.id, code)

    def test_a_wrong_code_is_refused(self):
        challenge, code = self.issue()
        wrong = "000000" if code != "000000" else "111111"

        with self.assertRaises(InvalidVerificationCode):
            verification.confirm_phone_verification(self.user, challenge.id, wrong)

    def test_a_wrong_code_does_not_verify_the_phone(self):
        challenge, _ = self.issue()

        with self.assertRaises(InvalidVerificationCode):
            verification.confirm_phone_verification(self.user, challenge.id, "000000")

        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)

    def test_a_wrong_code_increments_the_attempt_count(self):
        challenge, _ = self.issue()

        with self.assertRaises(InvalidVerificationCode):
            verification.confirm_phone_verification(self.user, challenge.id, "000000")

        challenge.refresh_from_db()
        self.assertEqual(challenge.attempt_count, 1)

    def test_resubmitting_the_same_wrong_code_keeps_counting(self):
        # Otherwise an attacker retries one guess forever at no cost.
        challenge, _ = self.issue()

        for _ in range(3):
            with self.assertRaises(InvalidVerificationCode):
                verification.confirm_phone_verification(self.user, challenge.id, "000000")

        challenge.refresh_from_db()
        self.assertEqual(challenge.attempt_count, 3)

    def test_the_refusal_reports_attempts_remaining(self):
        challenge, _ = self.issue()

        with self.assertRaises(InvalidVerificationCode) as caught:
            verification.confirm_phone_verification(self.user, challenge.id, "000000")

        self.assertEqual(caught.exception.details["attempts_remaining"], challenge.max_attempts - 1)

    def test_a_challenge_is_exhausted_after_the_attempt_cap(self):
        challenge, _ = self.issue()

        for _ in range(challenge.max_attempts - 1):
            with self.assertRaises(InvalidVerificationCode):
                verification.confirm_phone_verification(self.user, challenge.id, "000000")

        with self.assertRaises(VerificationExhausted):
            verification.confirm_phone_verification(self.user, challenge.id, "000000")

    def test_an_exhausted_challenge_refuses_even_the_correct_code(self):
        challenge, code = self.issue()
        VerificationChallenge.objects.filter(pk=challenge.pk).update(
            attempt_count=challenge.max_attempts
        )

        with self.assertRaises(VerificationExhausted):
            verification.confirm_phone_verification(self.user, challenge.id, code)

        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)

    def test_an_expired_challenge_refuses_the_correct_code(self):
        challenge, code = self.issue()
        VerificationChallenge.objects.filter(pk=challenge.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )

        with self.assertRaises(VerificationExpired):
            verification.confirm_phone_verification(self.user, challenge.id, code)

        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)

    def test_another_users_challenge_cannot_be_used(self):
        challenge, code = self.issue()
        stranger = make_user(phone="08039998877")

        with self.assertRaises(VerificationChallengeNotFound):
            verification.confirm_phone_verification(stranger, challenge.id, code)

        stranger.refresh_from_db()
        self.assertIsNone(stranger.phone_verified_at)

    def test_an_unknown_challenge_id_is_refused(self):
        with self.assertRaises(VerificationChallengeNotFound):
            verification.confirm_phone_verification(
                self.user, "00000000-0000-4000-8000-000000000000", "123456"
            )

    def test_a_malformed_challenge_id_is_refused_rather_than_crashing(self):
        with self.assertRaises(VerificationChallengeNotFound):
            verification.confirm_phone_verification(self.user, "not-a-uuid", "123456")


@override_settings(SMS_BACKEND=LOCMEM)
class PhoneChangeTests(VerificationBase):
    def verify(self) -> None:
        challenge, code = self.issue()
        verification.confirm_phone_verification(self.user, challenge.id, code)
        self.user.refresh_from_db()

    def test_changing_the_phone_clears_verification(self):
        self.verify()
        self.assertTrue(self.user.is_phone_verified)

        verification.set_phone(self.user, "08039998877")

        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)

    def test_the_new_number_is_normalised(self):
        verification.set_phone(self.user, "0803 999 8877")

        self.user.refresh_from_db()
        self.assertEqual(self.user.phone, "+2348039998877")

    def test_setting_the_same_number_again_keeps_verification(self):
        self.verify()

        verification.set_phone(self.user, "+2348031234567")

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_phone_verified)

    def test_a_challenge_for_the_old_number_cannot_verify_the_new_one(self):
        # The crux of the phone change rule: a code sent to the previous number
        # proves nothing about the number now being claimed.
        challenge, code = self.issue()

        verification.set_phone(self.user, "08039998877")

        with self.assertRaises(VerificationChallengeNotFound):
            verification.confirm_phone_verification(self.user, challenge.id, code)

        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)

    def test_changing_the_phone_supersedes_live_challenges(self):
        challenge, _ = self.issue()

        verification.set_phone(self.user, "08039998877")

        challenge.refresh_from_db()
        self.assertTrue(challenge.is_superseded)

    def test_a_direct_model_save_also_clears_verification(self):
        # The invariant is enforced on the model, so the admin and the shell cannot
        # leave a new number wearing the old one's verification.
        self.verify()

        self.user.phone = "+2348039998877"
        self.user.save()

        self.user.refresh_from_db()
        self.assertIsNone(self.user.phone_verified_at)

    def test_saving_without_changing_the_phone_leaves_verification_alone(self):
        self.verify()

        self.user.first_name = "Ada"
        self.user.save()

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_phone_verified)

    def test_the_new_number_can_be_verified_again(self):
        self.verify()
        verification.set_phone(self.user, "08039998877")
        self.user.refresh_from_db()

        challenge, code = self.issue()
        verification.confirm_phone_verification(self.user, challenge.id, code)

        self.user.refresh_from_db()
        self.assertTrue(self.user.is_phone_verified)
        self.assertEqual(self.user.phone, "+2348039998877")
