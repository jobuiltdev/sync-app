from rest_framework import exceptions, status
from rest_framework.test import APIRequestFactory, APITestCase

from apps.common.exceptions import APIError, api_exception_handler


def handle(exc):
    return api_exception_handler(exc, {"request": APIRequestFactory().get("/")})


class ErrorEnvelopeTests(APITestCase):
    def test_wraps_a_drf_exception(self):
        response = handle(exceptions.NotFound())

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            set(response.data["error"]),
            {"code", "message", "details"},
        )
        self.assertEqual(response.data["error"]["code"], "NOT_FOUND")

    def test_validation_errors_carry_the_offending_fields(self):
        response = handle(exceptions.ValidationError({"email": ["This field is required."]}))

        error = response.data["error"]
        self.assertEqual(error["code"], "VALIDATION_ERROR")
        self.assertEqual(error["details"]["fields"], {"email": ["This field is required."]})

    def test_api_error_carries_its_own_code_and_details(self):
        response = handle(
            APIError(
                "Verify your phone number to book a service.",
                code="PHONE_VERIFICATION_REQUIRED",
                details={"unmet": ["PHONE_VERIFIED"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["error"]["code"], "PHONE_VERIFICATION_REQUIRED")
        self.assertEqual(response.data["error"]["details"], {"unmet": ["PHONE_VERIFIED"]})

    def test_details_is_always_present(self):
        response = handle(exceptions.NotAuthenticated())

        self.assertEqual(response.data["error"]["details"], {})

    def test_unrecognised_exceptions_are_left_to_django(self):
        self.assertIsNone(handle(ValueError("boom")))


class ErrorEnvelopeIntegrationTests(APITestCase):
    """Proves the handler is wired into DRF, not just that it works in isolation.

    The route used has to behave the same under every settings module, since this
    suite runs under dev settings via `manage.py test` and under test settings via
    pytest. An unsupported method on the health endpoint is a real DRF error that
    no environment changes.
    """

    def test_a_real_request_error_returns_the_envelope(self):
        response = self.client.post("/api/v1/health/")

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data["error"]["code"], "METHOD_NOT_ALLOWED")
        self.assertEqual(response.data["error"]["details"], {})
        self.assertNotIn("detail", response.data)
