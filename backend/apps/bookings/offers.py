from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel


class OfferKind(models.TextChoices):
    """How this provider came to be offered the job.

    DIRECT means the customer named them. BROADCAST means they were one of the
    eligible providers the request went out to. The distinction is recorded rather
    than inferred, because a direct request is a different promise to the customer
    than an open one.
    """

    DIRECT = "DIRECT", "Requested directly by the customer"
    BROADCAST = "BROADCAST", "Offered to eligible providers"


class OfferStatus(models.TextChoices):
    """An offer's lifecycle.

    An explicit status rather than a nullable `responded` flag, matching the
    pattern the booking and verification lifecycles already use. Every terminal
    state is terminal: nothing returns to PENDING.
    """

    PENDING = "PENDING", "Awaiting a response"
    ACCEPTED = "ACCEPTED", "Accepted"
    DECLINED = "DECLINED", "Declined"
    #: The offer's own window closed without a response.
    EXPIRED = "EXPIRED", "Lapsed"
    #: Another provider took the booking first, so this offer is moot. Kept
    #: distinct from DECLINED because the provider did nothing wrong and their
    #: acceptance rate should not suffer for it.
    SUPERSEDED = "SUPERSEDED", "Another provider took it"


TERMINAL_OFFER_STATUSES = frozenset(
    {
        OfferStatus.ACCEPTED,
        OfferStatus.DECLINED,
        OfferStatus.EXPIRED,
        OfferStatus.SUPERSEDED,
    }
)


class Offer(BaseModel):
    """A job put in front of one provider.

    Carries no copy of the booking's service, customer or address: those are one
    join away and duplicating them would create two versions of the truth. What it
    does own is the record of who was asked, when, and what they said.
    """

    booking = models.ForeignKey("bookings.Booking", on_delete=models.CASCADE, related_name="offers")
    provider = models.ForeignKey(
        "providers.ProviderProfile",
        # An offer is part of the audit trail of how a booking was filled, so it
        # must outlive a provider tidying up their profile.
        on_delete=models.PROTECT,
        related_name="offers",
    )

    kind = models.CharField(max_length=10, choices=OfferKind.choices)
    status = models.CharField(
        max_length=12, choices=OfferStatus.choices, default=OfferStatus.PENDING
    )

    sent_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    responded_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "bookings_offer"
        ordering = ["-created_at"]
        constraints = [
            # A provider is asked about a booking once. Without this, a retried
            # dispatch would put the same job in an inbox twice.
            models.UniqueConstraint(
                fields=["booking", "provider"], name="bookings_offer_unique_per_provider"
            ),
            # The invariant that makes concurrent acceptance safe: at most one
            # accepted offer per booking, enforced by the database rather than by
            # application checks that two transactions can both pass.
            models.UniqueConstraint(
                fields=["booking"],
                condition=models.Q(status="ACCEPTED"),
                name="bookings_offer_one_accepted_per_booking",
            ),
            # A response and a responded-at timestamp travel together.
            models.CheckConstraint(
                condition=(
                    models.Q(status="PENDING", responded_at__isnull=True)
                    | (~models.Q(status="PENDING") & models.Q(responded_at__isnull=False))
                ),
                name="bookings_offer_responded_at_matches_status",
            ),
        ]
        indexes = [
            # The provider inbox: their pending offers, newest first.
            models.Index(fields=["provider", "status", "-created_at"]),
            models.Index(fields=["booking", "status"]),
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider_id} <- {self.booking_id} ({self.status})"

    @property
    def is_pending(self) -> bool:
        return self.status == OfferStatus.PENDING

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_OFFER_STATUSES

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_actionable(self) -> bool:
        """Whether this provider could still accept or decline it."""
        return self.is_pending and not self.is_expired
