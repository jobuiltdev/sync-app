"""A customer's attempt to pay for a booking.

`PaymentIntent` is the name docs/architecture.md already gives this, so it is the
name used here rather than a competing one. It is an attempt rather than a
payment: it is created when we ask a provider to start collecting, and it becomes
SUCCESSFUL only when that provider tells us money moved.

Nothing a client sends can make one successful. The only writers of that status
are verification against the provider and a signature-checked webhook, and both
of those compare the provider's amount and currency against this row before they
will touch it.
"""

import secrets

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel
from apps.payments.money import Currency

#: Same alphabet the booking reference uses, for the same reason: no characters
#: that get misread when somebody reads one out to support.
REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
REFERENCE_LENGTH = 10


def generate_reference() -> str:
    """Our own handle on a payment, and the one the provider is given.

    Random rather than sequential. It travels to a third party and back through a
    customer's browser, and a guessable one would let somebody enumerate how much
    business the marketplace does.
    """
    return "SYP-" + "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(REFERENCE_LENGTH))


class PaymentStatus(models.TextChoices):
    """Three states, because three is what the domain acts on.

    A provider's own vocabulary is richer than this and its wording is kept in
    `gateway_status` for support. What the rest of the system needs to know is
    whether money is still in flight, has arrived, or will not be arriving.
    """

    INITIALIZED = "INITIALIZED", "Waiting for the customer to pay"
    SUCCESSFUL = "SUCCESSFUL", "Paid"
    FAILED = "FAILED", "Not paid"


TERMINAL_STATUSES = frozenset({PaymentStatus.SUCCESSFUL, PaymentStatus.FAILED})


class PaymentIntent(BaseModel):
    """One attempt to collect the price of one booking.

    A booking may have several: a card that was declined and then a transfer that
    worked is two attempts and one payment. What it may not have is two that
    succeeded, which is a database constraint rather than a rule anybody has to
    remember.
    """

    booking = models.ForeignKey(
        "bookings.Booking",
        # A payment is a record of money that moved between two people, and must
        # outlive any tidy-up of the thing it paid for.
        on_delete=models.PROTECT,
        related_name="payment_intents",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payment_intents",
    )

    reference = models.CharField(
        max_length=20,
        unique=True,
        default=generate_reference,
        editable=False,
        help_text="Our handle on this payment, and what the provider is told to call it.",
    )

    #: Copied from the booking at creation, never recomputed. The booking's total
    #: is itself a snapshot, so the amount charged is the amount the customer
    #: agreed to at the moment they asked for the work.
    amount_kobo = models.BigIntegerField()
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.NGN)

    status = models.CharField(
        max_length=12, choices=PaymentStatus.choices, default=PaymentStatus.INITIALIZED
    )

    #: Which provider took this payment. Recorded rather than assumed, so a
    #: payment stays identifiable after the configured gateway changes.
    gateway = models.CharField(max_length=20)
    gateway_reference = models.CharField(max_length=120, blank=True)
    #: The provider's own word for the outcome, for support conversations.
    gateway_status = models.CharField(max_length=40, blank=True)
    #: Card, transfer, USSD. Whatever the provider says the customer used.
    method = models.CharField(max_length=40, blank=True)

    #: Where the customer completes the payment. Not a secret: it is a one-time
    #: checkout link scoped to this transaction, which is why the app may hold it.
    authorization_url = models.URLField(max_length=500, blank=True)

    idempotency_key = models.CharField(max_length=100, blank=True)

    paid_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments_payment_intent"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_kobo__gt=0),
                name="payments_intent_amount_positive",
            ),
            # A booking is paid for once. Two successful intents against one
            # booking would mean a customer charged twice, and this is what makes
            # that impossible rather than merely unlikely.
            models.UniqueConstraint(
                fields=["booking"],
                condition=models.Q(status="SUCCESSFUL"),
                name="payments_intent_one_successful_per_booking",
            ),
            # A retry carrying the key of a request that already started a payment
            # is the same request, not a second attempt to charge.
            models.UniqueConstraint(
                fields=["booking", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="payments_intent_unique_idempotency_key",
            ),
            # One provider transaction backs at most one of our records, so a
            # webhook and a verification racing each other cannot end up
            # attaching the same money to two intents.
            models.UniqueConstraint(
                fields=["gateway", "gateway_reference"],
                condition=~models.Q(gateway_reference=""),
                name="payments_intent_unique_gateway_reference",
            ),
            # A resolved payment says when it resolved, and an unresolved one
            # cannot claim to have.
            models.CheckConstraint(
                condition=(
                    models.Q(status="SUCCESSFUL", paid_at__isnull=False)
                    | models.Q(status="FAILED", failed_at__isnull=False)
                    | models.Q(status="INITIALIZED", paid_at__isnull=True, failed_at__isnull=True)
                ),
                name="payments_intent_timestamps_match_status",
            ),
        ]
        indexes = [
            models.Index(fields=["booking", "status"]),
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference}: {self.amount_kobo} kobo ({self.status})"

    @property
    def is_successful(self) -> bool:
        return self.status == PaymentStatus.SUCCESSFUL

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    @property
    def is_payable(self) -> bool:
        """Whether the customer could still complete this attempt."""
        return self.status == PaymentStatus.INITIALIZED
