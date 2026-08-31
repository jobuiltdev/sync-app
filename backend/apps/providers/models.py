from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.catalog.models import Service
from apps.common.models import BaseModel
from apps.common.nigeria import NigerianState


class VerificationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending submission"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    SUSPENDED = "SUSPENDED", "Suspended"


#: The only legal moves. Kept as data rather than scattered conditionals so the
#: whole lifecycle can be read, and tested, in one place. The booking state machine
#: in M3 follows this same shape.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    VerificationStatus.PENDING: {VerificationStatus.UNDER_REVIEW},
    VerificationStatus.UNDER_REVIEW: {VerificationStatus.APPROVED, VerificationStatus.REJECTED},
    # A rejected provider fixes what was wrong and resubmits.
    VerificationStatus.REJECTED: {VerificationStatus.UNDER_REVIEW},
    VerificationStatus.APPROVED: {VerificationStatus.SUSPENDED},
    VerificationStatus.SUSPENDED: {VerificationStatus.APPROVED},
}


class IllegalTransition(ValidationError):
    """A verification status change that the lifecycle does not permit."""

    def __init__(self, current: str, target: str) -> None:
        allowed = ", ".join(sorted(ALLOWED_TRANSITIONS.get(current, set()))) or "nothing"
        super().__init__(
            f"Cannot move verification from {current} to {target}. Allowed from "
            f"{current}: {allowed}.",
            code="illegal_transition",
        )


def can_transition(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


class ProviderProfile(BaseModel):
    """The provider side of an account.

    One to one with User rather than a role flag, because a person here is often
    both customer and provider, and a role enum would force them into two logins.
    Its existence is what makes an account a provider; there is no boolean to keep
    in step with it.

    Nothing gates on `verification_status` yet. The capability policy that decides
    what an unapproved provider may do is deliberately still open, and M4 is where
    it gets consumed.
    """

    class ProviderType(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL", "Individual"
        BUSINESS = "BUSINESS", "Business"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="provider_profile",
    )

    display_name = models.CharField(
        max_length=140,
        help_text="Shown to customers. May differ from the account holder's legal name.",
    )
    bio = models.TextField(blank=True, max_length=2000)
    provider_type = models.CharField(
        max_length=12, choices=ProviderType.choices, default=ProviderType.INDIVIDUAL
    )
    business_name = models.CharField(max_length=200, blank=True)

    verification_status = models.CharField(
        max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )

    #: The provider's own switch for taking work, separate from whether we allow
    #: them to. Conflating the two would mean reinstating a suspended provider
    #: silently puts them back on call.
    is_accepting_jobs = models.BooleanField(default=False)

    class Meta:
        db_table = "providers_profile"
        indexes = [
            models.Index(fields=["verification_status"]),
            models.Index(fields=["verification_status", "is_accepting_jobs"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(display_name=""),
                name="providers_profile_display_name_not_empty",
            ),
        ]

    def __str__(self) -> str:
        return self.display_name

    @property
    def is_approved(self) -> bool:
        return self.verification_status == VerificationStatus.APPROVED

    def transition_verification(self, target: str) -> None:
        """Moves verification state, refusing anything the lifecycle disallows.

        Every change goes through here. Assigning the field directly is possible in
        Python but is not done anywhere in the codebase, and the tests assert the
        illegal moves are refused.
        """
        if not can_transition(self.verification_status, target):
            raise IllegalTransition(self.verification_status, target)

        self.verification_status = target
        self.save(update_fields=["verification_status", "updated_at"])


class ProviderService(BaseModel):
    """A service this provider offers.

    The capability link. A provider offering nothing is a valid state, which is why
    this is a separate table rather than fields on the profile.
    """

    provider = models.ForeignKey(
        ProviderProfile, on_delete=models.CASCADE, related_name="offered_services"
    )
    service = models.ForeignKey(
        Service,
        # Retiring a service that providers offer is an operational decision, not
        # something a delete should silently cascade through.
        on_delete=models.PROTECT,
        related_name="offered_by",
    )

    #: Overrides the service's base price for this provider. Null means the
    #: catalog price stands, which is different from an override that happens to
    #: equal it and would be lost if the catalog price moved.
    price_override_kobo = models.BigIntegerField(null=True, blank=True)
    experience_years = models.PositiveSmallIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "providers_service"
        ordering = ["service__sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "service"], name="providers_service_unique_per_provider"
            ),
            models.CheckConstraint(
                condition=models.Q(price_override_kobo__isnull=True)
                | models.Q(price_override_kobo__gte=0),
                name="providers_service_price_not_negative",
            ),
        ]
        indexes = [models.Index(fields=["service", "is_active"])]

    def __str__(self) -> str:
        return f"{self.provider.display_name}: {self.service.name}"

    @property
    def effective_price_kobo(self) -> int:
        return (
            self.price_override_kobo
            if self.price_override_kobo is not None
            else self.service.base_price_kobo
        )


class ProviderServiceArea(BaseModel):
    """Where a provider is willing to work.

    Coarse by design: state and LGA, not a radius. Matching in M4 can narrow this
    with coordinates, but a provider can answer "which areas do you cover" reliably
    and cannot answer "how many kilometres will you travel".
    """

    provider = models.ForeignKey(
        ProviderProfile, on_delete=models.CASCADE, related_name="service_areas"
    )
    state = models.CharField(max_length=20, choices=NigerianState.choices)
    lga = models.CharField(max_length=120, blank=True, help_text="Blank means the whole state.")

    class Meta:
        db_table = "providers_service_area"
        ordering = ["state", "lga"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "state", "lga"], name="providers_area_unique_per_provider"
            ),
        ]
        indexes = [models.Index(fields=["state", "lga"])]

    def __str__(self) -> str:
        return f"{self.get_state_display()}{f' / {self.lga}' if self.lga else ''}"


# Imported here so Django discovers it. The attempt model lives in its own module
# because it owns a lifecycle of its own, the same arrangement `payments` uses.
from apps.providers.verification import (  # noqa: E402  (circular by design)
    AttemptStatus,
    CheckStatus,
    ProviderVerification,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "AttemptStatus",
    "CheckStatus",
    "IllegalTransition",
    "ProviderProfile",
    "ProviderService",
    "ProviderServiceArea",
    "ProviderVerification",
    "VerificationStatus",
    "can_transition",
]
