"""Authentication errors, as stable machine codes.

These are the codes the mobile app branches on, so they are part of the API
contract. The messages beside them can be reworded freely; the codes cannot.
"""

from typing import TYPE_CHECKING

from rest_framework import status

from apps.common.exceptions import APIError

if TYPE_CHECKING:
    from apps.accounts.policy import PolicyResult


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


class VerificationRequired(APIError):
    """A capability the account holds no proof for.

    403 rather than 401: the caller is authenticated and known, they simply have
    not proven something yet. A 401 would tell the app to sign the user out, which
    is exactly the wrong response.
    """

    status_code = status.HTTP_403_FORBIDDEN
    default_code = "VERIFICATION_REQUIRED"
    default_detail = "Verify your details to continue."


#: A single unmet requirement gets its own code so the app can route straight to
#: the right flow without inspecting details. Several unmet fall back to the
#: umbrella code, and the client reads details.unmet in the order given.
_SPECIFIC_CODES = {
    "PHONE_VERIFIED": ("PHONE_VERIFICATION_REQUIRED", "Verify your phone number to continue."),
    "EMAIL_VERIFIED": ("EMAIL_VERIFICATION_REQUIRED", "Verify your email address to continue."),
}


class PhoneNotSet(APIError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "PHONE_NOT_SET"
    default_detail = "Add a phone number to your account first."


class PhoneAlreadyVerified(APIError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "PHONE_ALREADY_VERIFIED"
    default_detail = "This phone number is already verified."


class VerificationCooldown(APIError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "PHONE_VERIFICATION_COOLDOWN"
    default_detail = "A code was sent recently. Wait a moment before asking for another."

    def __init__(self, retry_after: int) -> None:
        super().__init__(details={"retry_after_seconds": retry_after})


class VerificationChallengeNotFound(APIError):
    """No usable challenge.

    Deliberately one code for several situations: unknown id, another account's
    challenge, already consumed, superseded, or bound to a number the account no
    longer has. Distinguishing them would tell an attacker which challenge ids
    exist and which accounts they belong to.
    """

    status_code = status.HTTP_404_NOT_FOUND
    default_code = "VERIFICATION_CHALLENGE_NOT_FOUND"
    default_detail = "That code request is no longer valid. Request a new code."


class VerificationExpired(APIError):
    status_code = status.HTTP_410_GONE
    default_code = "PHONE_VERIFICATION_EXPIRED"
    default_detail = "That code has expired. Request a new one."


class VerificationExhausted(APIError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "PHONE_VERIFICATION_EXHAUSTED"
    default_detail = "Too many incorrect attempts. Request a new code."


class InvalidVerificationCode(APIError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "INVALID_PHONE_VERIFICATION_CODE"
    default_detail = "That code is not correct."

    def __init__(self, attempts_remaining: int) -> None:
        super().__init__(details={"attempts_remaining": attempts_remaining})


def verification_required(result: PolicyResult) -> VerificationRequired:
    code, message = VerificationRequired.default_code, VerificationRequired.default_detail

    if len(result.unmet) == 1:
        code, message = _SPECIFIC_CODES.get(result.unmet[0], (code, message))

    return VerificationRequired(message, code=code, details=result.as_details())
