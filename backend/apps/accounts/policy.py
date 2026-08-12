"""What an account is allowed to do, and what it must prove first.

One table, consulted from everywhere. Scattering these checks across serializers
is how an API ends up enforcing a rule on one path and forgetting it on another.

Verification state lives on the User (M1) and the ProviderProfile (M2); this module
is the only place that decides what that state permits. M3 is the first consumer.
M4 adds ACCEPT_JOB, M5 adds REQUEST_PAYOUT, and neither needs to change anything
here beyond adding a row.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from apps.accounts.models import User


class Capability(models.TextChoices):
    """A gated action. Named for what the user is doing, not for an endpoint."""

    CREATE_BOOKING = "CREATE_BOOKING", "Create a booking"


class Requirement(models.TextChoices):
    EMAIL_VERIFIED = "EMAIL_VERIFIED", "Verified email address"
    PHONE_VERIFIED = "PHONE_VERIFIED", "Verified phone number"


#: Booking requires a verified phone and deliberately not a verified email. A
#: provider on their way to an address needs to reach the customer by phone; an
#: email address does nothing for that, and demanding both would cost conversion at
#: the exact moment the customer is ready to commit.
CAPABILITY_REQUIREMENTS: dict[str, list[str]] = {
    Capability.CREATE_BOOKING: [Requirement.PHONE_VERIFIED],
}


#: How a client resolves each requirement. Returned with the error so the app can
#: send the user somewhere useful rather than to a dead end.
REQUIREMENT_NEXT_STEP: dict[str, dict[str, str]] = {
    Requirement.PHONE_VERIFIED: {
        "requirement": Requirement.PHONE_VERIFIED,
        "action": "POST /api/v1/auth/phone/verification/request/",
    },
    Requirement.EMAIL_VERIFIED: {
        "requirement": Requirement.EMAIL_VERIFIED,
        "action": "POST /api/v1/auth/email/verification/request/",
    },
}


def _is_satisfied(user: User, requirement: str) -> bool:
    if requirement == Requirement.EMAIL_VERIFIED:
        return user.email_verified_at is not None
    if requirement == Requirement.PHONE_VERIFIED:
        return user.phone_verified_at is not None
    raise ValueError(f"Unknown requirement {requirement!r}.")


@dataclass(frozen=True)
class PolicyResult:
    """The outcome of a check, rather than a bare boolean.

    Callers need to know which requirements are outstanding to tell the user
    anything useful, so the unmet list travels with the answer.
    """

    capability: str
    satisfied: list[str]
    unmet: list[str]

    @property
    def allowed(self) -> bool:
        return not self.unmet

    def as_details(self) -> dict:
        details: dict = {
            "capability": self.capability,
            "unmet": list(self.unmet),
            "satisfied": list(self.satisfied),
        }
        if self.unmet:
            details["next_step"] = REQUIREMENT_NEXT_STEP.get(self.unmet[0], {})
        return details


def check(user: User, capability: str) -> PolicyResult:
    """Reports whether a user holds a capability. Never raises, never mutates."""
    requirements = CAPABILITY_REQUIREMENTS.get(capability, [])

    satisfied = [r for r in requirements if _is_satisfied(user, r)]
    unmet = [r for r in requirements if r not in satisfied]

    return PolicyResult(capability=capability, satisfied=satisfied, unmet=unmet)


def enforce(user: User, capability: str) -> None:
    """Raises the appropriate API error when a capability is not held.

    Imported lazily to keep this module free of DRF, so it stays callable from a
    management command, a Celery task or a test without pulling in the web layer.
    """
    result = check(user, capability)
    if result.allowed:
        return

    from apps.accounts.errors import verification_required

    raise verification_required(result)
