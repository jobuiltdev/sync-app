"""A provider asking for their money, and what may happen to that request.

The lifecycle here follows the same shape as the booking and offer state machines:
one table of legal moves, the actor as part of the edge rather than an afterthought,
and no path by which a client names a status. The reason the actors matter this
time is blunt. A provider must be able to ask to be paid and to change their mind,
and must never be able to record that they were paid.
"""

from django.db import models

# The booking lifecycle already names the four kinds of actor in this system, and
# payments already depends on bookings for the settlement's booking. Declaring a
# second, identical enum here would mean two lists to keep in step for no gain.
from apps.bookings.state import ActorType
from apps.common.models import BaseModel
from apps.payments.money import Currency


class PayoutStatus(models.TextChoices):
    REQUESTED = "REQUESTED", "Requested"
    #: Handed to whoever moves the money. No transfer provider is integrated yet,
    #: so nothing reaches this state without an admin putting it there.
    PROCESSING = "PROCESSING", "Being processed"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled by the provider"


#: Money asked for but not yet sent. It is not spent, and it is not available
#: either: counting it as available is what would let a provider request the same
#: earnings twice.
RESERVING_STATUSES = frozenset({PayoutStatus.REQUESTED, PayoutStatus.PROCESSING})

#: Money that has left. Permanently subtracted from what can be asked for again.
SPENT_STATUSES = frozenset({PayoutStatus.PAID})

TERMINAL_STATUSES = frozenset({PayoutStatus.PAID, PayoutStatus.FAILED, PayoutStatus.CANCELLED})

#: Legal moves, and who may make each one.
#:
#: Only SYSTEM and ADMIN appear on the edges that end in PROCESSING or PAID. That
#: is the rule the whole model exists to enforce: a provider marking their own
#: payout paid would make the record worthless, and no endpoint in this app gives
#: a provider either actor type.
#:
#: A failed payout is terminal rather than returning to REQUESTED. The money goes
#: back into the available balance either way, and asking the provider to make a
#: fresh request leaves a clean record of two attempts instead of one row that
#: quietly changed its mind.
ALLOWED_TRANSITIONS: dict[str, dict[str, frozenset[str]]] = {
    PayoutStatus.REQUESTED: {
        PayoutStatus.PROCESSING: frozenset({ActorType.SYSTEM, ActorType.ADMIN}),
        PayoutStatus.FAILED: frozenset({ActorType.SYSTEM, ActorType.ADMIN}),
        PayoutStatus.CANCELLED: frozenset({ActorType.PROVIDER, ActorType.ADMIN}),
    },
    PayoutStatus.PROCESSING: {
        PayoutStatus.PAID: frozenset({ActorType.SYSTEM, ActorType.ADMIN}),
        PayoutStatus.FAILED: frozenset({ActorType.SYSTEM, ActorType.ADMIN}),
    },
    PayoutStatus.PAID: {},
    PayoutStatus.FAILED: {},
    PayoutStatus.CANCELLED: {},
}


def targets_from(current: str) -> frozenset[str]:
    return frozenset(ALLOWED_TRANSITIONS.get(current, {}))


def is_allowed(current: str, target: str, actor_type: str) -> bool:
    return actor_type in ALLOWED_TRANSITIONS.get(current, {}).get(target, frozenset())


def actors_for(current: str, target: str) -> frozenset[str]:
    return ALLOWED_TRANSITIONS.get(current, {}).get(target, frozenset())


class PayoutRequest(BaseModel):
    """One request to be paid out some of what a provider has earned.

    Deliberately not linked to particular settlements. A payout is a claim against
    a balance, and the balance is derived by summing the immutable records on both
    sides, so there is no allocation table to get out of step with them. What stops
    the same earnings being claimed twice is the arithmetic in
    `services.available_balance` plus the two database constraints below.
    """

    provider = models.ForeignKey(
        "providers.ProviderProfile",
        on_delete=models.PROTECT,
        related_name="payout_requests",
    )

    amount_kobo = models.BigIntegerField()
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.NGN)
    status = models.CharField(
        max_length=12, choices=PayoutStatus.choices, default=PayoutStatus.REQUESTED
    )

    requested_at = models.DateTimeField(auto_now_add=True)
    #: Set when the payout reaches a terminal state, whichever one it is.
    processed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    #: The client's Idempotency-Key for the request that created this row. Blank
    #: when the client sent none, which is why the uniqueness below is partial:
    #: several keyless requests are several genuine payouts, but the same key
    #: twice is one payout asked for twice over a bad connection.
    idempotency_key = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "payments_payout_request"
        ordering = ["-created_at"]
        constraints = [
            # A payout for nothing is not a payout. Zero and negative amounts are
            # refused in the service layer with a useful message; this is the
            # guarantee that holds even if a future caller forgets to.
            models.CheckConstraint(
                condition=models.Q(amount_kobo__gt=0),
                name="payments_payout_amount_positive",
            ),
            # One live payout per provider. This is the double-spend guard the
            # database itself enforces: two requests racing on the same balance
            # cannot both commit, whatever the application layer believed.
            models.UniqueConstraint(
                fields=["provider"],
                condition=models.Q(status__in=["REQUESTED", "PROCESSING"]),
                name="payments_payout_one_in_flight_per_provider",
            ),
            # A retry carrying the key of a request that already succeeded is the
            # same request, not a second one.
            models.UniqueConstraint(
                fields=["provider", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="payments_payout_unique_idempotency_key",
            ),
            # A resolved payout says when it was resolved, and an unresolved one
            # cannot claim to have been.
            models.CheckConstraint(
                condition=(
                    models.Q(status__in=["PAID", "FAILED", "CANCELLED"], processed_at__isnull=False)
                    | models.Q(status__in=["REQUESTED", "PROCESSING"], processed_at__isnull=True)
                ),
                name="payments_payout_processed_at_matches_status",
            ),
            # Only a failure carries a reason. A cancelled or paid row holding one
            # would be a record of something that did not happen.
            models.CheckConstraint(
                condition=models.Q(status="FAILED") | models.Q(failure_reason=""),
                name="payments_payout_reason_only_when_failed",
            ),
        ]
        indexes = [
            models.Index(fields=["provider", "-created_at"]),
            models.Index(fields=["provider", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.provider_id}: {self.amount_kobo} kobo ({self.status})"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_cancellable(self) -> bool:
        """Whether the provider could still call this off themselves."""
        return self.status == PayoutStatus.REQUESTED
