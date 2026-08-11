from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User

PASSWORD = "Lagos-Rider-2026"

REGISTER_URL = "/api/v1/auth/register/"
LOGIN_URL = "/api/v1/auth/login/"
REFRESH_URL = "/api/v1/auth/refresh/"
LOGOUT_URL = "/api/v1/auth/logout/"
ME_URL = "/api/v1/auth/me/"


def make_user(email: str = "ada@example.com", **extra) -> User:
    return User.objects.create_user(email=email, password=PASSWORD, **extra)


class RegistrationTests(APITestCase):
    def test_creates_an_account_and_returns_a_session(self):
        response = self.client.post(
            REGISTER_URL,
            {"email": "ada@example.com", "password": PASSWORD, "first_name": "Ada"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["email"], "ada@example.com")
        self.assertTrue(response.data["tokens"]["access"])
        self.assertTrue(response.data["tokens"]["refresh"])
        self.assertTrue(User.objects.filter(email="ada@example.com").exists())

    def test_never_returns_the_password(self):
        response = self.client.post(
            REGISTER_URL, {"email": "ada@example.com", "password": PASSWORD}, format="json"
        )

        self.assertNotIn("password", response.data["user"])
        self.assertNotIn(PASSWORD, str(response.data))

    def test_normalises_the_email_before_storing_it(self):
        response = self.client.post(
            REGISTER_URL, {"email": "  Ada@Example.COM  ", "password": PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["user"]["email"], "ada@example.com")

    def test_normalises_a_local_phone_number(self):
        response = self.client.post(
            REGISTER_URL,
            {"email": "ada@example.com", "password": PASSWORD, "phone": "0803 123 4567"},
            format="json",
        )

        self.assertEqual(response.data["user"]["phone"], "+2348031234567")

    def test_registers_without_a_phone(self):
        response = self.client.post(
            REGISTER_URL, {"email": "ada@example.com", "password": PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(response.data["user"]["phone"])

    def test_the_new_account_starts_unverified(self):
        response = self.client.post(
            REGISTER_URL, {"email": "ada@example.com", "password": PASSWORD}, format="json"
        )

        self.assertFalse(response.data["user"]["is_email_verified"])
        self.assertFalse(response.data["user"]["is_phone_verified"])

    def test_rejects_a_duplicate_email_regardless_of_case(self):
        make_user("ada@example.com")

        response = self.client.post(
            REGISTER_URL, {"email": "ADA@Example.com", "password": PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("email", response.data["error"]["details"]["fields"])

    def test_rejects_a_duplicate_phone_written_differently(self):
        make_user("one@example.com", phone="08031234567")

        response = self.client.post(
            REGISTER_URL,
            {"email": "two@example.com", "password": PASSWORD, "phone": "+234 803 123 4567"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data["error"]["details"]["fields"])

    def test_rejects_an_undialable_phone(self):
        response = self.client.post(
            REGISTER_URL,
            {"email": "ada@example.com", "password": PASSWORD, "phone": "0800000"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data["error"]["details"]["fields"])

    def test_rejects_a_short_password(self):
        response = self.client.post(
            REGISTER_URL, {"email": "ada@example.com", "password": "short1"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data["error"]["details"]["fields"])

    def test_rejects_a_common_password(self):
        response = self.client.post(
            REGISTER_URL, {"email": "ada@example.com", "password": "password123"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data["error"]["details"]["fields"])

    def test_rejects_an_entirely_numeric_password(self):
        response = self.client.post(
            REGISTER_URL, {"email": "ada@example.com", "password": "84726194037"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data["error"]["details"]["fields"])

    def test_rejects_a_password_that_looks_like_the_email(self):
        response = self.client.post(
            REGISTER_URL,
            {"email": "adaokeke@example.com", "password": "adaokeke@example"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data["error"]["details"]["fields"])

    def test_rejects_a_malformed_email(self):
        response = self.client.post(
            REGISTER_URL, {"email": "not-an-email", "password": PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data["error"]["details"]["fields"])


class LoginTests(APITestCase):
    def setUp(self):
        self.user = make_user()

    def test_signs_in_with_correct_credentials(self):
        response = self.client.post(
            LOGIN_URL, {"email": "ada@example.com", "password": PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], str(self.user.id))
        self.assertTrue(response.data["tokens"]["access"])

    def test_email_is_normalised_before_matching(self):
        response = self.client.post(
            LOGIN_URL, {"email": "  ADA@Example.COM ", "password": PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_rejects_a_wrong_password(self):
        response = self.client.post(
            LOGIN_URL,
            {"email": "ada@example.com", "password": "wrong-password-here"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "INVALID_CREDENTIALS")

    def test_rejects_an_unknown_account(self):
        response = self.client.post(
            LOGIN_URL, {"email": "nobody@example.com", "password": PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "INVALID_CREDENTIALS")

    def test_an_unknown_account_is_indistinguishable_from_a_wrong_password(self):
        # If these two differed, the endpoint would report which addresses exist.
        unknown = self.client.post(
            LOGIN_URL, {"email": "nobody@example.com", "password": PASSWORD}, format="json"
        )
        wrong = self.client.post(
            LOGIN_URL,
            {"email": "ada@example.com", "password": "wrong-password-here"},
            format="json",
        )

        self.assertEqual(unknown.status_code, wrong.status_code)
        self.assertEqual(unknown.data, wrong.data)

    def test_a_deactivated_account_is_told_so(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.post(
            LOGIN_URL, {"email": "ada@example.com", "password": PASSWORD}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"]["code"], "ACCOUNT_INACTIVE")

    def test_requires_both_fields(self):
        response = self.client.post(LOGIN_URL, {"email": "ada@example.com"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")


class AccessTokenTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.tokens = self.client.post(
            LOGIN_URL, {"email": "ada@example.com", "password": PASSWORD}, format="json"
        ).data["tokens"]

    def test_me_returns_the_signed_in_user(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.tokens['access']}")

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "ada@example.com")
        self.assertEqual(response.data["id"], str(self.user.id))

    def test_me_rejects_an_unauthenticated_request(self):
        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")

    def test_me_rejects_a_garbage_token(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_rejects_the_refresh_token_used_as_an_access_token(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.tokens['refresh']}")

        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_errors_use_the_standard_envelope(self):
        response = self.client.get(ME_URL)

        self.assertEqual(set(response.data["error"]), {"code", "message", "details"})
        self.assertNotIn("detail", response.data)


class RefreshTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.tokens = self.client.post(
            LOGIN_URL, {"email": "ada@example.com", "password": PASSWORD}, format="json"
        ).data["tokens"]

    def test_exchanges_a_refresh_token_for_a_new_pair(self):
        response = self.client.post(REFRESH_URL, {"refresh": self.tokens["refresh"]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["access"])
        self.assertTrue(response.data["refresh"])

    def test_the_rotated_refresh_token_is_a_new_one(self):
        response = self.client.post(REFRESH_URL, {"refresh": self.tokens["refresh"]}, format="json")

        self.assertNotEqual(response.data["refresh"], self.tokens["refresh"])

    def test_the_new_access_token_works(self):
        refreshed = self.client.post(
            REFRESH_URL, {"refresh": self.tokens["refresh"]}, format="json"
        ).data

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed['access']}")
        response = self.client.get(ME_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_a_spent_refresh_token_cannot_be_reused(self):
        self.client.post(REFRESH_URL, {"refresh": self.tokens["refresh"]}, format="json")

        response = self.client.post(REFRESH_URL, {"refresh": self.tokens["refresh"]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "INVALID_TOKEN")

    def test_rejects_a_malformed_refresh_token(self):
        response = self.client.post(REFRESH_URL, {"refresh": "nonsense"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "INVALID_TOKEN")

    def test_refuses_to_refresh_for_a_deactivated_account(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.post(REFRESH_URL, {"refresh": self.tokens["refresh"]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "INVALID_TOKEN")

    def test_refuses_to_refresh_for_a_deleted_account(self):
        refresh = self.tokens["refresh"]
        self.user.delete()

        response = self.client.post(REFRESH_URL, {"refresh": refresh}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class LogoutTests(APITestCase):
    def setUp(self):
        make_user()
        self.tokens = self.client.post(
            LOGIN_URL, {"email": "ada@example.com", "password": PASSWORD}, format="json"
        ).data["tokens"]

    def test_signs_out_and_invalidates_the_refresh_token(self):
        response = self.client.post(LOGOUT_URL, {"refresh": self.tokens["refresh"]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        reuse = self.client.post(REFRESH_URL, {"refresh": self.tokens["refresh"]}, format="json")
        self.assertEqual(reuse.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_works_without_a_valid_access_token(self):
        # Signing out must not depend on an access token that may have expired while
        # the app was in the background.
        response = self.client.post(LOGOUT_URL, {"refresh": self.tokens["refresh"]}, format="json")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_rejects_a_malformed_token(self):
        response = self.client.post(LOGOUT_URL, {"refresh": "nonsense"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "INVALID_TOKEN")

    def test_requires_a_refresh_token(self):
        response = self.client.post(LOGOUT_URL, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")


class TokenClaimTests(TestCase):
    def test_the_token_carries_the_user_uuid(self):
        user = make_user()

        token = RefreshToken.for_user(user)

        self.assertEqual(str(token.payload["user_id"]), str(user.id))
