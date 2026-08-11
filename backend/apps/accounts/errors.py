"""Authentication errors, as stable machine codes.

These are the codes the mobile app branches on, so they are part of the API
contract. The messages beside them can be reworded freely; the codes cannot.
"""

from rest_framework import status

from apps.common.exceptions import APIError


class InvalidCredentials(APIError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "INVALID_CREDENTIALS"
    # Deliberately does not say which of the two was wrong. Naming the address as
    # unknown would turn this endpoint into a way to enumerate who has an account.
    default_detail = "That email or password is not correct."


class AccountInactive(APIError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "ACCOUNT_INACTIVE"
    default_detail = "This account has been deactivated. Contact support to restore it."


class InvalidToken(APIError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "INVALID_TOKEN"
    default_detail = "Your session has expired. Sign in again."
