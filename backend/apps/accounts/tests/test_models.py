from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from apps.accounts.models import User
from config.settings import base as settings_base

PASSWORD = "Lagos-Rider-2026"


class UserCreationTests(TestCase):
    def test_creates_a_user_with_the_expected_defaults(self):
        user = User.objects.create_user(email="ada@example.com", password=PASSWORD)

        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertIsNone(user.phone)
        self.assertIsNotNone(user.id)

    def test_new_accounts_start_unverified(self):
        user = User.objects.create_user(email="ada@example.com", password=PASSWORD)

        self.assertIsNone(user.email_verified_at)
        self.assertIsNone(user.phone_verified_at)
        self.assertFalse(user.is_email_verified)
        self.assertFalse(user.is_phone_verified)

    def test_normalises_email_and_phone_on_creation(self):
        user = User.objects.create_user(
            email="  Ada@Example.COM ", password=PASSWORD, phone="0803 123 4567"
        )

        self.assertEqual(user.email, "ada@example.com")
        self.assertEqual(user.phone, "+2348031234567")

    def test_rejects_creation_without_an_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password=PASSWORD)

    def test_creates_a_superuser(self):
        user = User.objects.create_superuser(email="ops@sync.ng", password=PASSWORD)

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_refuses_a_superuser_that_is_not_staff(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(email="ops@sync.ng", password=PASSWORD, is_staff=False)

    def test_full_name_joins_the_parts_and_tolerates_missing_ones(self):
        both = User(first_name="Ada", last_name="Okeke")
        first_only = User(first_name="Ada")
        neither = User()

        self.assertEqual(both.full_name, "Ada Okeke")
        self.assertEqual(first_only.full_name, "Ada")
        self.assertEqual(neither.full_name, "")

    def test_string_representation_is_the_email(self):
        user = User.objects.create_user(email="ada@example.com", password=PASSWORD)

        self.assertEqual(str(user), "ada@example.com")


class PasswordTests(TestCase):
    def test_password_is_hashed_not_stored(self):
        user = User.objects.create_user(email="ada@example.com", password=PASSWORD)

        self.assertNotEqual(user.password, PASSWORD)
        self.assertNotIn(PASSWORD, user.password)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.check_password("something-else-entirely"))

    def test_argon2_is_the_configured_hasher(self):
        # Read from base directly, because the test settings deliberately swap in
        # MD5 to keep the suite fast and would otherwise hide what production uses.
        self.assertTrue(
            settings_base.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher"),
            settings_base.PASSWORD_HASHERS[0],
        )

    @override_settings(PASSWORD_HASHERS=settings_base.PASSWORD_HASHERS)
    def test_argon2_actually_hashes_a_password(self):
        user = User.objects.create_user(email="ada@example.com", password=PASSWORD)

        self.assertTrue(user.password.startswith("argon2$"), user.password[:24])
        self.assertTrue(user.check_password(PASSWORD))

    def test_two_users_with_the_same_password_get_different_hashes(self):
        one = User.objects.create_user(email="one@example.com", password=PASSWORD)
        two = User.objects.create_user(email="two@example.com", password=PASSWORD)

        self.assertNotEqual(one.password, two.password)

    def test_a_user_created_without_a_password_cannot_log_in_with_one(self):
        user = User.objects.create_user(email="google@example.com")

        self.assertFalse(user.has_usable_password())


class IdentityConstraintTests(TestCase):
    def test_duplicate_email_is_rejected_by_the_database(self):
        User.objects.create_user(email="ada@example.com", password=PASSWORD)

        with self.assertRaises(IntegrityError), transaction.atomic():
            User(email="ada@example.com").save()

    def test_duplicate_email_differing_only_in_case_is_rejected(self):
        User.objects.create_user(email="ada@example.com", password=PASSWORD)

        # Caught by full_clean inside the manager, so it surfaces as a validation
        # error rather than reaching the database as an IntegrityError.
        with self.assertRaises(DjangoValidationError):
            User.objects.create_user(email="ADA@example.com", password=PASSWORD)

    def test_duplicate_phone_is_rejected_by_the_database(self):
        User.objects.create_user(email="one@example.com", password=PASSWORD, phone="08031234567")

        with self.assertRaises(IntegrityError), transaction.atomic():
            User(email="two@example.com", phone="+2348031234567").save()

    def test_duplicate_phone_written_in_a_different_format_is_rejected(self):
        User.objects.create_user(email="one@example.com", password=PASSWORD, phone="08031234567")

        with self.assertRaises(DjangoValidationError):
            User.objects.create_user(
                email="two@example.com", password=PASSWORD, phone="+234 803 123 4567"
            )

    def test_many_users_may_have_no_phone(self):
        User.objects.create_user(email="one@example.com", password=PASSWORD)
        User.objects.create_user(email="two@example.com", password=PASSWORD)

        self.assertEqual(User.objects.filter(phone__isnull=True).count(), 2)

    def test_empty_string_phone_is_rejected_by_the_check_constraint(self):
        # The reason phone is NULL rather than "" when absent: Postgres permits many
        # NULLs under a unique index but only one empty string.
        with self.assertRaises(IntegrityError), transaction.atomic():
            User(email="ada@example.com", phone="").save()

    def test_empty_email_is_rejected_by_the_check_constraint(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            User(email="").save()
