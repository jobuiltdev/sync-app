"""The record that a provider told us something, and that we handled it once.

Not a webhook framework. It is one model and one rule: an event id is seen at
most once, enforced by a unique index, so a provider redelivering an event, or
sending it three times because our first two acknowledgements were slow, cannot
apply it three times. That is the whole of what payment webhooks need now and the
whole of what payout webhooks will need later.

**The payload is not stored.** A Paystack charge payload carries the customer's
email address and the last four digits of their card, and keeping a copy of every
one of those in our database is a liability that buys very little. What is kept is
the handful of fields reconciliation actually reads, plus a digest of the raw body
so a disputed event can still be matched against the provider's own record.
"""

import hashlib

from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel


class WebhookEvent(BaseModel):
    """One event from one provider, recorded so it is only ever applied once."""

    gateway = models.CharField(max_length=20)
    #: Stable for the same event redelivered, which is what makes it a
    #: deduplication key. Built by the adapter out of whatever the provider gives.
    event_id = models.CharField(max_length=200)
    event_type = models.CharField(max_length=80)

    #: The fields reconciliation reads, and no others.
    reference = models.CharField(max_length=120, blank=True)
    amount_kobo = models.BigIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, blank=True)

    #: SHA-256 of the exact bytes received. Enough to prove later that a given
    #: body is or is not the one we handled, without holding the body.
    payload_digest = models.CharField(max_length=64)

    processed_at = models.DateTimeField(null=True, blank=True)
    #: Why an event was received but changed nothing. An event about a reference
    #: we do not know, or one that arrived after the payment already resolved, is
    #: a normal occurrence rather than an error, and this says which it was.
    outcome = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "payments_webhook_event"
        ordering = ["-created_at"]
        constraints = [
            # The deduplication guarantee, in the database rather than in a check
            # two concurrent deliveries could both pass.
            models.UniqueConstraint(
                fields=["gateway", "event_id"], name="payments_webhook_unique_event"
            ),
        ]
        indexes = [
            models.Index(fields=["gateway", "-created_at"]),
            models.Index(fields=["reference"]),
        ]

    def __str__(self) -> str:
        return f"{self.gateway}:{self.event_id}"

    def mark_processed(self, outcome: str) -> None:
        self.processed_at = timezone.now()
        self.outcome = outcome[:200]
        self.save(update_fields=["processed_at", "outcome", "updated_at"])


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()
