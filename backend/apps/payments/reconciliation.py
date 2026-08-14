"""Finding out what really happened, for things nobody was watching.

Two jobs, both reads against our own records and one provider:

* **Payment reconciliation** resolves payments left `INITIALIZED` because the
  customer closed the app, or the webhook never arrived, or it arrived while we
  were restarting.
* **The consistency sweep** looks for combinations that should be impossible and
  decides, per anomaly, whether the system may fix it or a person must.

The rule both obey: **an unknown provider state never becomes SUCCESSFUL.** Age
is not evidence. A payment that has been pending for a week is a payment we have
not been able to resolve, which is a different thing from a payment that failed,
and marking it either way on the strength of a clock would be inventing a fact.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.bookings.state import BookingStatus
from apps.payments import anomalies
from apps.payments.anomalies import AnomalyClass, AnomalyKind
from apps.payments.errors import PaymentAmountMismatch
from apps.payments.gateways.base import GatewayError, PaymentState, get_payment_gateway
from apps.payments.intents import PaymentIntent, PaymentStatus
from apps.payments.settlements import BookingSettlement

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconcileOutcome:
    """What one reconciliation attempt established.

    `intent` is None only when the payment vanished between the sweep listing it
    and this looking at it, which a deletion in the admin can do.
    """

    intent: PaymentIntent | None
    #: RESOLVED when the payment reached a terminal state, PENDING when the
    #: provider says it is still working, UNKNOWN when we could not establish
    #: anything, MISMATCH when the provider described a different transaction.
    verdict: str


def pending_after() -> timedelta:
    return timedelta(seconds=settings.PAYMENT_RECONCILIATION["PENDING_AFTER_SECONDS"])


def give_up_after() -> timedelta:
    return timedelta(seconds=settings.PAYMENT_RECONCILIATION["GIVE_UP_AFTER_SECONDS"])


def reconcilable_payments():
    """Payments old enough to be worth asking about, and young enough to bother.

    The upper bound matters as much as the lower one. A payment nobody has been
    able to resolve for a week is not going to be resolved by asking an eighth
    time, and sweeping it forever buries the ones that are still answerable.
    """
    now = timezone.now()

    return PaymentIntent.objects.filter(
        status=PaymentStatus.INITIALIZED,
        created_at__lte=now - pending_after(),
        created_at__gte=now - give_up_after(),
    ).order_by("created_at")


def reconcile_payment(intent_id: Any) -> ReconcileOutcome:
    """Asks the provider what happened to one payment, and records the answer.

    Reuses the same apply function the customer's verify endpoint and the webhook
    both use, so all three reach identical conclusions from identical answers.
    There is one definition in this system of what a provider's word means, and
    this is not a second one.
    """
    from django.db import transaction

    from apps.payments.payment_services import _apply, verify_payment  # noqa: F401

    with transaction.atomic():
        intent = PaymentIntent.objects.select_for_update().filter(pk=intent_id).first()

        if intent is None or intent.is_terminal:
            # Resolved by a webhook or by the customer between the sweep reading
            # the list and getting here, which is the common case and not an
            # error.
            return ReconcileOutcome(intent=intent, verdict="ALREADY_RESOLVED")

        try:
            reported = get_payment_gateway().fetch(intent.reference)
        except GatewayError:
            # Could not ask. Left exactly as it was, and the task's own retry
            # policy decides whether to try again shortly. Nothing about a
            # provider being unreachable tells us anything about the payment.
            logger.warning("Could not reach the payment provider to reconcile %s", intent.reference)
            return ReconcileOutcome(intent=intent, verdict="UNREACHABLE")

        if reported.reference and reported.reference != intent.reference:
            # The provider answered about a different transaction. Refusing is
            # the only safe reading, and it is worth a person's attention.
            anomalies.record(
                kind=AnomalyKind.UNRESOLVED_PAYMENT,
                classification=AnomalyClass.REVIEW,
                subject_type="PaymentIntent",
                subject_id=intent.pk,
                subject_reference=intent.reference,
                detail="The provider answered about a different transaction reference.",
            )
            return ReconcileOutcome(intent=intent, verdict="MISMATCH")

        if reported.state == PaymentState.PENDING:
            # Genuinely still in flight. Left alone, deliberately: a customer
            # part-way through a bank transfer is not a failed payment.
            return ReconcileOutcome(intent=intent, verdict="PENDING")

        try:
            outcome = _apply(intent, reported)
        except PaymentAmountMismatch as exc:
            # A provider reporting success for the wrong sum. Never applied, and
            # always escalated: this is either a bug or somebody's money in the
            # wrong place, and both need a person.
            anomalies.record(
                kind=AnomalyKind.UNRESOLVED_PAYMENT,
                classification=AnomalyClass.REVIEW,
                subject_type="PaymentIntent",
                subject_id=intent.pk,
                subject_reference=intent.reference,
                detail=(
                    f"The provider reported a different amount for this payment. "
                    f"Expected {intent.amount_kobo} kobo. {exc.detail}"
                ),
            )
            return ReconcileOutcome(intent=intent, verdict="MISMATCH")

    return ReconcileOutcome(
        intent=outcome.intent,
        verdict="RESOLVED" if outcome.changed else "PENDING",
    )


def flag_unresolvable_payments(limit: int) -> int:
    """Records the payments that have aged out of reconciliation.

    They are not failed and are not marked failed. They are payments nobody has
    been able to establish anything about, which is exactly the state an operator
    should be shown rather than have tidied away.
    """
    cutoff = timezone.now() - give_up_after()

    stale = PaymentIntent.objects.filter(
        status=PaymentStatus.INITIALIZED, created_at__lt=cutoff
    ).order_by("created_at")[:limit]

    flagged = 0
    for intent in stale:
        anomalies.record(
            kind=AnomalyKind.UNRESOLVED_PAYMENT,
            classification=AnomalyClass.REVIEW,
            subject_type="PaymentIntent",
            subject_id=intent.pk,
            subject_reference=intent.reference,
            detail=(
                "Pending since "
                f"{intent.created_at:%Y-%m-%d %H:%M} and no longer being reconciled "
                "automatically."
            ),
        )
        flagged += 1

    return flagged


# --- the consistency sweep -------------------------------------------------


def sweep(limit: int) -> dict[str, int]:
    """Looks for combinations that should not be possible.

    Reads our own rows only, so it is cheap and completely safe to run twice.
    Every finding is classified, and only one class is acted on.
    """
    found = {"repaired": 0, "review": 0}

    found["repaired"] += _repair_unsettled_paid_bookings(limit)
    found["review"] += _flag_settlements_without_payment(limit)
    found["review"] += _flag_settlement_amount_mismatches(limit)
    found["review"] += _flag_stale_submitted_payouts(limit)

    return found


def _repair_unsettled_paid_bookings(limit: int) -> int:
    """The one anomaly the system may fix on its own.

    A booking that is completed and paid for, with no settlement, has exactly one
    correct outcome and the code to produce it already exists. Nothing is being
    guessed: the amount comes from the booking, the rate from configuration, and
    the same function writes it that the ordinary path uses.

    It happens when a process dies between the two conditions being met and the
    settlement being written, which the transaction makes very unlikely and not
    impossible.
    """
    from apps.bookings.models import Booking
    from apps.payments.services import is_paid, settle_if_ready

    candidates = Booking.objects.filter(
        status=BookingStatus.COMPLETED, settlement__isnull=True
    ).order_by("-completed_at")[:limit]

    repaired = 0
    for booking in candidates:
        if not is_paid(booking):
            # Completed and unpaid is an ordinary state, not an anomaly. The
            # customer simply has not paid yet.
            continue

        settlement = settle_if_ready(booking)
        if settlement is None:
            continue

        anomalies.record(
            kind=AnomalyKind.UNSETTLED_PAID_BOOKING,
            classification=AnomalyClass.REPAIRED,
            subject_type="Booking",
            subject_id=booking.pk,
            subject_reference=booking.reference,
            detail="Completed and paid but unsettled. The settlement has been written.",
        ).resolve("Settled by the consistency sweep")
        repaired += 1

    if repaired:
        logger.info("Consistency sweep settled %d completed and paid booking(s)", repaired)

    return repaired


def _flag_settlements_without_payment(limit: int) -> int:
    """A provider owed money for a booking nobody paid for.

    Never repaired automatically. Deleting a settlement would destroy a provider's
    earnings on the say-so of a sweep, and there is no other way to "fix" this
    that does not involve deciding whose mistake it was.
    """
    suspect = BookingSettlement.objects.select_related("booking").order_by("-created_at")[
        : limit * 2
    ]

    flagged = 0
    for settlement in suspect:
        if PaymentIntent.objects.filter(
            booking_id=settlement.booking_id, status=PaymentStatus.SUCCESSFUL
        ).exists():
            continue

        anomalies.record(
            kind=AnomalyKind.SETTLEMENT_WITHOUT_PAYMENT,
            classification=AnomalyClass.REVIEW,
            subject_type="BookingSettlement",
            subject_id=settlement.pk,
            subject_reference=settlement.booking.reference,
            detail=(
                f"{settlement.provider_amount_kobo} kobo owed to a provider for a booking "
                "with no successful payment."
            ),
        )
        flagged += 1

    return flagged


def _flag_settlement_amount_mismatches(limit: int) -> int:
    """A settlement that does not agree with the booking behind it.

    The invariant inside a settlement is a database constraint and cannot break.
    This is the other question: whether the gross it recorded is the total the
    customer actually agreed to. Never repaired, because rewriting a settled
    amount is precisely what the immutability rule forbids, and a compensating
    record is a decision for whoever owns the money.
    """
    suspect = (
        BookingSettlement.objects.select_related("booking")
        .exclude(gross_amount_kobo__isnull=True)
        .order_by("-created_at")[: limit * 2]
    )

    flagged = 0
    for settlement in suspect:
        if settlement.gross_amount_kobo == settlement.booking.total_kobo:
            continue

        anomalies.record(
            kind=AnomalyKind.SETTLEMENT_AMOUNT_MISMATCH,
            classification=AnomalyClass.REVIEW,
            subject_type="BookingSettlement",
            subject_id=settlement.pk,
            subject_reference=settlement.booking.reference,
            detail=(
                f"Settled at {settlement.gross_amount_kobo} kobo against a booking total of "
                f"{settlement.booking.total_kobo} kobo."
            ),
        )
        flagged += 1

    return flagged


def _flag_stale_submitted_payouts(limit: int) -> int:
    """Money that was sent, or may have been, and is still unresolved.

    The single most important thing an operator can be told. Reconciliation is
    already asking the provider every few minutes; if it is still unresolved an
    hour later then the provider is not answering usefully and somebody needs to
    look in their dashboard.
    """
    from apps.payments.execution import stale_after
    from apps.payments.payouts import PayoutRequest, PayoutStatus

    cutoff = timezone.now() - timedelta(seconds=stale_after())

    stuck = (
        PayoutRequest.objects.filter(status=PayoutStatus.PROCESSING, submitted_at__lte=cutoff)
        .exclude(transfer_reference="")
        .order_by("submitted_at")[:limit]
    )

    flagged = 0
    for payout in stuck:
        anomalies.record(
            kind=AnomalyKind.STALE_SUBMITTED_PAYOUT,
            classification=AnomalyClass.REVIEW,
            subject_type="PayoutRequest",
            subject_id=payout.pk,
            subject_reference=payout.transfer_reference,
            detail=(
                f"{payout.amount_kobo} kobo submitted at "
                f"{payout.submitted_at:%Y-%m-%d %H:%M} and still unresolved. "
                f"Provider reference: {payout.gateway_reference or 'never received'}."
            ),
        )
        flagged += 1

    return flagged


def open_anomalies():
    """Everything currently waiting on a person."""
    return anomalies.FinancialAnomaly.objects.filter(
        Q(resolved_at__isnull=True) & Q(classification=AnomalyClass.REVIEW)
    )
