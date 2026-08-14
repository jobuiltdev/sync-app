"""Financial work that happens when nobody is looking.

Four tasks, in two retry classes, and the classification is a statement about
money rather than about code. See `apps/common/tasks.py` for the contract they
all follow.

**Safe to retry**: every reconciliation and the consistency sweep. All of them
read from the provider or from our own rows, and re-check under a lock before
writing anything.

**Requires reconciliation, never retried**: payout execution. It makes the one
external call in this system that moves money out, and a retry of an unanswered
submission is the one mistake that cannot be undone.
"""

import logging

from django.conf import settings

from apps.common.tasks import batched, reconciled_task, safe_task

logger = logging.getLogger(__name__)


# --- payments --------------------------------------------------------------


@safe_task(name="apps.payments.tasks.reconcile_pending_payments")
def reconcile_pending_payments() -> dict[str, int]:
    """Asks the provider about payments that never resolved themselves.

    Safe to retry: it asks a question and applies the answer through the same
    guarded path a webhook takes. Running it twice against one payment resolves
    it once and then finds nothing to do.
    """
    from apps.payments.reconciliation import (
        flag_unresolvable_payments,
        reconcilable_payments,
        reconcile_payment,
    )

    limit = settings.TASK_BATCH_SIZE
    tally = {"resolved": 0, "pending": 0, "unreachable": 0, "mismatch": 0}

    for intent_id in batched(reconcilable_payments().values_list("pk", flat=True), limit):
        verdict = reconcile_payment(intent_id).verdict
        key = {
            "RESOLVED": "resolved",
            "PENDING": "pending",
            "UNREACHABLE": "unreachable",
            "MISMATCH": "mismatch",
        }.get(verdict)
        if key:
            tally[key] += 1

    tally["flagged"] = flag_unresolvable_payments(limit)

    if any(tally.values()):
        logger.info("Payment reconciliation: %s", tally)

    return tally


@safe_task(name="apps.payments.tasks.reconcile_payment")
def reconcile_payment_task(intent_id: str) -> str:
    """Reconciles one payment, on demand.

    Exists so an operator can chase a single payment without waiting for the
    sweep, and so a failed webhook can be followed up individually.
    """
    from apps.payments.reconciliation import reconcile_payment

    return reconcile_payment(intent_id).verdict


# --- payouts ---------------------------------------------------------------


@reconciled_task(name="apps.payments.tasks.execute_payout")
def execute_payout_task(payout_id: str) -> str:
    """Sends the money for one payout. Never retried.

    `max_retries=0` is the most important line in this module. If this task
    fails after the provider was contacted, we do not know whether money moved,
    and a retry is how it moves twice. The payout is left carrying its transfer
    reference, which is the state `reconcile_payouts` exists to resolve, and
    nothing here will submit for it again.

    A failure that happened before the provider was contacted is equally safe:
    the payout still says REQUESTED with no reference, and an operator can send
    it again deliberately.
    """
    from apps.payments.execution import PayoutAlreadySubmitted, execute_payout
    from apps.payments.payouts import PayoutRequest

    try:
        payout = execute_payout(payout_id)
    except PayoutAlreadySubmitted:
        # Somebody or something already sent this. Exactly the outcome the
        # refusal is for, and not a failure worth raising into the queue.
        logger.info("Payout %s was already submitted; leaving it to reconciliation", payout_id)
        return "already submitted"
    except Exception:
        logger.exception("Payout %s could not be executed", payout_id)
        # Re-raised so it is visible as a failed task, but with no retry behind
        # it. Whether anything was submitted is answered by the row, not by
        # guessing here.
        raise

    return PayoutRequest.objects.values_list("status", flat=True).get(pk=payout.pk)


@safe_task(name="apps.payments.tasks.reconcile_payouts")
def reconcile_payouts() -> dict[str, int]:
    """Resolves payouts whose transfer outcome we never learned.

    Safe to retry, because it only ever asks. This is the task that closes the
    crash window: a payout submitted at the moment the process died is sitting in
    PROCESSING with a reference, and asking the provider about that reference is
    the authoritative way to find out what happened to it.
    """
    from apps.payments.execution import reconcile_payout
    from apps.payments.payouts import PayoutRequest, PayoutStatus

    limit = settings.TASK_BATCH_SIZE

    unresolved = (
        PayoutRequest.objects.filter(status=PayoutStatus.PROCESSING)
        .exclude(transfer_reference="")
        .order_by("submitted_at")
        .values_list("pk", flat=True)
    )

    tally = {"paid": 0, "failed": 0, "still_processing": 0}

    for payout_id in batched(unresolved, limit):
        payout = reconcile_payout(payout_id)
        if payout.status == PayoutStatus.PAID:
            tally["paid"] += 1
        elif payout.status == PayoutStatus.FAILED:
            tally["failed"] += 1
        else:
            tally["still_processing"] += 1

    if any(tally.values()):
        logger.info("Payout reconciliation: %s", tally)

    return tally


# --- consistency -----------------------------------------------------------


@safe_task(name="apps.payments.tasks.sweep_financial_consistency")
def sweep_financial_consistency() -> dict[str, int]:
    """Looks for states that should not exist, and repairs only the unambiguous.

    Reads our own rows, so it is cheap and entirely safe to run twice. Anything
    it is not certain about is recorded rather than changed.
    """
    from apps.payments.reconciliation import sweep

    result = sweep(settings.TASK_BATCH_SIZE)

    if result["review"]:
        logger.warning("Consistency sweep found %d anomalies needing review", result["review"])

    return result
