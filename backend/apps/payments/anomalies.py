"""Things that should not be true, written down where an operator will see them.

Not a logging system. One table, holding the specific inconsistencies the
consistency sweep knows how to look for, so that the questions an operator
actually asks have an answer: why is this money in a pending state, what did the
sweep decide about it, and has anybody dealt with it.

**Most anomalies are not repaired automatically.** The sweep repairs exactly the
cases where the invariant and the intended outcome are both unambiguous, and
records everything else for a person. Silently fixing a settlement whose amount
disagrees with its booking would destroy the evidence of whatever caused the
disagreement, which is the only thing worth having when it happens.
"""

from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel


class AnomalyKind(models.TextChoices):
    """The specific things the sweep knows how to find.

    A closed list rather than a free-text label, because an anomaly nobody can
    query for is an anomaly nobody will act on.
    """

    UNSETTLED_PAID_BOOKING = (
        "UNSETTLED_PAID_BOOKING",
        "Completed and paid, but never settled",
    )
    SETTLEMENT_WITHOUT_PAYMENT = (
        "SETTLEMENT_WITHOUT_PAYMENT",
        "Settled, but no successful payment",
    )
    SETTLEMENT_AMOUNT_MISMATCH = (
        "SETTLEMENT_AMOUNT_MISMATCH",
        "Settled for an amount the booking does not agree with",
    )
    SETTLEMENT_ON_UNFINISHED_BOOKING = (
        "SETTLEMENT_ON_UNFINISHED_BOOKING",
        "Settled, but the booking is not completed",
    )
    STALE_SUBMITTED_PAYOUT = (
        "STALE_SUBMITTED_PAYOUT",
        "Transfer submitted long ago and still unresolved",
    )
    UNRESOLVED_PAYMENT = (
        "UNRESOLVED_PAYMENT",
        "Payment pending far longer than any customer would wait",
    )


class AnomalyClass(models.TextChoices):
    """What may be done about it, decided by the sweep and not by a person.

    The distinction that matters: REPAIRED means the system already acted,
    because there was exactly one thing it could have meant. REVIEW means it
    did not act, and will not, until somebody decides.
    """

    REPAIRED = "REPAIRED", "Repaired automatically"
    RETRYABLE = "RETRYABLE", "Will resolve itself on a later run"
    REVIEW = "REVIEW", "Needs a person"


class FinancialAnomaly(BaseModel):
    """One inconsistency, found once and kept until somebody closes it.

    Deduplicated on kind plus subject while open, so a sweep running hourly
    against a problem nobody has fixed produces one row rather than one row an
    hour. The `last_seen_at` bump is how long it has been going on.
    """

    kind = models.CharField(max_length=40, choices=AnomalyKind.choices)
    classification = models.CharField(max_length=12, choices=AnomalyClass.choices)

    #: What it is about. A UUID rather than a foreign key, because an anomaly may
    #: concern a booking, a payment or a payout, and three nullable relations
    #: would be three chances to point at the wrong one.
    subject_type = models.CharField(max_length=40)
    subject_id = models.UUIDField()
    #: The human-readable handle, so an operator can search for what they were
    #: given rather than for a UUID.
    subject_reference = models.CharField(max_length=40, blank=True)

    #: What was found, in words. Never a payload, never a credential, never an
    #: account number: enough to know what to look at and nothing more.
    detail = models.CharField(max_length=500)

    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    times_seen = models.PositiveIntegerField(default=1)

    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "payments_financial_anomaly"
        ordering = ["-last_seen_at"]
        verbose_name_plural = "financial anomalies"
        constraints = [
            # One open row per problem. Without this an hourly sweep against an
            # unfixed anomaly buries every other anomaly under copies of it.
            models.UniqueConstraint(
                fields=["kind", "subject_id"],
                condition=models.Q(resolved_at__isnull=True),
                name="payments_anomaly_one_open_per_subject",
            ),
        ]
        indexes = [
            models.Index(fields=["classification", "-last_seen_at"]),
            models.Index(fields=["kind", "-last_seen_at"]),
            models.Index(fields=["resolved_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.kind} on {self.subject_reference or self.subject_id}"

    @property
    def is_open(self) -> bool:
        return self.resolved_at is None

    def resolve(self, resolution: str) -> None:
        self.resolved_at = timezone.now()
        self.resolution = resolution[:200]
        self.save(update_fields=["resolved_at", "resolution", "updated_at"])


def record(
    *,
    kind: str,
    classification: str,
    subject_type: str,
    subject_id,
    detail: str,
    subject_reference: str = "",
) -> FinancialAnomaly:
    """Notes an anomaly, or notes that an open one is still happening."""
    existing = FinancialAnomaly.objects.filter(
        kind=kind, subject_id=subject_id, resolved_at__isnull=True
    ).first()

    if existing is not None:
        existing.last_seen_at = timezone.now()
        existing.times_seen += 1
        existing.detail = detail[:500]
        existing.classification = classification
        existing.save(
            update_fields=[
                "last_seen_at",
                "times_seen",
                "detail",
                "classification",
                "updated_at",
            ]
        )
        return existing

    return FinancialAnomaly.objects.create(
        kind=kind,
        classification=classification,
        subject_type=subject_type,
        subject_id=subject_id,
        subject_reference=subject_reference[:40],
        detail=detail[:500],
    )
