"""The record that somebody was told something, and whether it arrived.

One model. It holds delivery state and nothing else: no business meaning is ever
read out of it, and no domain decision depends on it. If this whole table were
dropped, every booking, payment, settlement and payout would still be correct.

**No message body is stored.** A rendered message contains the customer's
address, the provider's name, an amount. Keeping a copy of every one of those
would build, over a year, a second database of exactly the information the rest
of the system is careful with. What is stored is the event, the recipient, the
domain object it concerns, and what happened to the send. The message can be
rendered again from the domain object whenever anybody actually needs to see it.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel
from apps.notifications.events import Channel, EventType


class DeliveryStatus(models.TextChoices):
    """Where one message got to.

    Delivery state, not business state. `FAILED` here means a message did not
    arrive, never that anything about the booking or the money is wrong.
    """

    PENDING = "PENDING", "Waiting to be sent"
    SENT = "SENT", "Handed to the provider"
    FAILED = "FAILED", "Could not be delivered"
    #: No usable destination, so nothing was attempted. Kept rather than deleted
    #: because "we never told them" is an operational fact worth being able to
    #: see when somebody asks why they did not hear about a job.
    SKIPPED = "SKIPPED", "No verified destination for this channel"


TERMINAL_STATUSES = frozenset({DeliveryStatus.SENT, DeliveryStatus.FAILED, DeliveryStatus.SKIPPED})


class Notification(BaseModel):
    """One message, on one channel, to one person, about one domain object."""

    event_type = models.CharField(max_length=40, choices=EventType.choices)
    channel = models.CharField(max_length=10, choices=Channel.choices)

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        # A notification is a record of contacting a person. It has no meaning
        # once that person is gone, and it must not keep an account alive.
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    #: What it is about. A UUID rather than a foreign key, because one event type
    #: may concern a booking, a payment or a payout, and three nullable relations
    #: would be three chances to point at the wrong one. Same shape as
    #: FinancialAnomaly, for the same reason.
    subject_type = models.CharField(max_length=40)
    subject_id = models.UUIDField(null=True, blank=True)
    #: The user-facing handle, so an operator can search for what the person was
    #: given rather than for a UUID.
    subject_reference = models.CharField(max_length=40, blank=True)

    status = models.CharField(
        max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )

    #: The identity of this message, used to make sending it exactly once a
    #: database guarantee rather than a hope. Built from the event, the subject
    #: and the channel, so a retried task, a redelivered webhook and two workers
    #: racing all produce the same string and only one row survives.
    dedupe_key = models.CharField(max_length=200, unique=True)

    attempts = models.PositiveSmallIntegerField(default=0)
    #: Why it did not arrive, in terms an operator can act on. Never a provider
    #: response body, never a credential, never a stack trace.
    failure_reason = models.CharField(max_length=255, blank=True)

    queued_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications_notification"
        ordering = ["-created_at"]
        constraints = [
            # A delivered message says when. The rest cannot claim to have been.
            models.CheckConstraint(
                condition=(
                    models.Q(status="SENT", delivered_at__isnull=False)
                    | (~models.Q(status="SENT") & models.Q(delivered_at__isnull=True))
                ),
                name="notifications_delivered_at_matches_status",
            ),
            # Only a failure carries a reason.
            models.CheckConstraint(
                condition=models.Q(status="FAILED")
                | models.Q(status="SKIPPED")
                | models.Q(failure_reason=""),
                name="notifications_reason_only_when_unsent",
            ),
        ]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["event_type", "-created_at"]),
            models.Index(fields=["subject_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} to {self.recipient_id} by {self.channel} ({self.status})"

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def mark_sent(self) -> None:
        self.status = DeliveryStatus.SENT
        self.delivered_at = timezone.now()
        self.failure_reason = ""
        self.save(update_fields=["status", "delivered_at", "failure_reason", "updated_at"])

    def mark_failed(self, reason: str) -> None:
        self.status = DeliveryStatus.FAILED
        self.failure_reason = reason[:255]
        self.save(update_fields=["status", "failure_reason", "updated_at"])

    def mark_skipped(self, reason: str) -> None:
        self.status = DeliveryStatus.SKIPPED
        self.failure_reason = reason[:255]
        self.save(update_fields=["status", "failure_reason", "updated_at"])
