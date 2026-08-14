"""Moving money out to a provider, and finding out what happened when we could not tell.

This is the riskiest code in the system. Everything else either takes money in,
which a customer starts and a provider confirms, or writes down what is owed.
This sends real naira to a real bank account, and it does so by making a request
across a network that can fail at the exact moment that matters.

### The failure window, stated plainly

We call the provider. They receive it, start a transfer, and begin their reply.
The connection drops, or the process is killed, or the container is rescheduled.
Money has moved and we have no record of it.

From our side that is indistinguishable from a request that never arrived. So the
system does not try to distinguish them at the moment of failure. Instead:

**A reference is reserved before the call.** `transfer_reference` is generated and
committed, with the payout moved to `PROCESSING`, in a transaction that finishes
before the provider is contacted. The instant that commits, the payout means
"this may have moved money". If the process dies one microsecond later, the row
already says so.

**A payout with a reference is never resubmitted.** Not by a retry, not by an
operator, not by the reconciliation task. `execute_payout` refuses outright. That
refusal is the guarantee against duplicate transfers, and it holds regardless of
what any provider does about idempotency.

**Reconciliation asks, using our reference.** Because the reference was ours and
was written down first, the question "did that transfer happen" always has
somewhere to be asked, and the answer is authoritative. That is why the transfer
interface requires `fetch(reference)` and why a provider that cannot answer by
our reference cannot be used here.

Paystack also treats a transfer reference as idempotent, so a resubmission would
return the original rather than duplicate it. That is a second line of defence and
it is deliberately not the first: relying on a vendor's idempotency for the one
operation that must never happen twice would be trusting a promise we cannot check.

### What each state means

| Payout state | What is true |
| --- | --- |
| `REQUESTED`, no reference | Definitely not sent |
| `PROCESSING`, reference, no gateway reference | Submitted, outcome unknown |
| `PROCESSING`, reference and gateway reference | Submitted, provider still working |
| `PAID` | Definitely successful |
| `FAILED` | Definitely failed, and the money is available again |
"""

import logging
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.bookings.state import ActorType
from apps.payments.errors import (
    InsufficientBalance,
    InvalidPayoutDestination,
    PayoutNotActionable,
    PayoutNotFound,
)
from apps.payments.payouts import PayoutRequest, PayoutStatus, generate_transfer_reference
from apps.payments.transfers.base import (
    TransferError,
    TransferRejected,
    TransferResult,
    TransferState,
    get_transfer_provider,
)
from apps.providers.models import ProviderProfile

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PayoutAlreadySubmitted(PayoutNotActionable):
    """Asked to send a transfer for a payout that already has one.

    The refusal that prevents duplicate money movement. It is not an error in the
    ordinary sense: it is the system declining to do the one thing it must never
    do twice, and the correct response is to reconcile rather than to try again.
    """

    default_code = "PAYOUT_ALREADY_SUBMITTED"
    default_detail = "A transfer has already been submitted for this payout."


def _recipient_for(provider: ProviderProfile) -> tuple[str, Any]:
    """The transfer provider's handle for where this payout is going.

    Read, never created. The handle is issued during account verification, which
    is the one moment the account number is in hand, and is the reason this
    system can pay a provider without ever having stored their account number:
    the handle is enough to pay against.

    A destination that is verified but carries no handle is one confirmed before
    a transfer provider was configured. It cannot be paid to, and the provider is
    asked to confirm the account again, which issues one.
    """
    from apps.payments.services import usable_destination

    destination = usable_destination(provider)

    if not destination.provider_reference:
        raise InvalidPayoutDestination(
            "Confirm your bank account again so we can set it up for payouts."
        )

    return destination.provider_reference, destination


def execute_payout(payout_id: Any, *, actor_type: str = ActorType.SYSTEM) -> PayoutRequest:
    """Sends the money for one requested payout.

    Every check happens behind a lock on the payout, and the amount is
    recalculated from the immutable records rather than trusted from the row: a
    payout requested when the balance covered it must not go out if it no longer
    does.

    Raises rather than retries on anything ambiguous. The caller is a task that
    does not retry, by design.
    """
    from apps.payments.services import available_balance

    transfers = get_transfer_provider()

    # --- everything that must be true, decided under a lock ----------------
    with transaction.atomic():
        try:
            payout = PayoutRequest.objects.select_for_update().get(pk=payout_id)
        except (
            PayoutRequest.DoesNotExist,
            DjangoValidationError,
            ValueError,
            TypeError,
        ):
            raise PayoutNotFound from None

        if payout.is_submitted:
            # The whole point. Something has already been sent, or may have been,
            # and this must not be the thing that sends a second.
            raise PayoutAlreadySubmitted(details={"transfer_reference": payout.transfer_reference})

        if payout.status != PayoutStatus.REQUESTED:
            raise PayoutNotActionable(
                f"A payout in {payout.status} cannot be sent.",
                details={"current_status": payout.status},
            )

        provider = ProviderProfile.objects.select_for_update().get(pk=payout.provider_id)

        # Recalculated from the immutable records, not read off the payout. The
        # payout's own amount is already counted as reserved, so it is added back
        # before comparing: the question is whether the earnings behind this
        # payout still exist, not whether there is a second payout's worth spare.
        earnings = available_balance(provider)
        backing = earnings.available_kobo + payout.amount_kobo
        if payout.amount_kobo > backing:
            raise InsufficientBalance(earnings.available_kobo, payout.amount_kobo)

        recipient_reference, _ = _recipient_for(provider)

        # Reserved and committed before the provider is contacted. After this
        # transaction commits, the payout says "this may have moved money", and
        # nothing will submit for it again.
        payout.transfer_reference = generate_transfer_reference()
        payout.transfer_provider = transfers.name
        payout.submitted_at = timezone.now()
        payout.status = PayoutStatus.PROCESSING
        payout.save(
            update_fields=[
                "transfer_reference",
                "transfer_provider",
                "submitted_at",
                "status",
                "updated_at",
            ]
        )

    # --- the external call, outside any transaction ------------------------
    # Deliberately not inside the block above. Holding a database transaction
    # open across a network call to a third party means holding row locks for as
    # long as they take to answer, and on the day they are slow that is how a
    # payout blocks every other payout for that provider.
    try:
        result = transfers.submit(
            reference=payout.transfer_reference,
            amount_kobo=payout.amount_kobo,
            currency=payout.currency,
            recipient_reference=recipient_reference,
            reason=f"Sync payout {payout.transfer_reference}",
        )
    except TransferRejected as exc:
        # The provider declined and started nothing. Safe to fail the payout,
        # which returns the money to the available balance by arithmetic.
        logger.warning("Payout %s was refused by the provider", payout.pk)
        return _fail(payout, reason=str(exc)[:255], actor_type=actor_type)
    except TransferError:
        # The window. Do not fail it, do not retry it: leave it PROCESSING with
        # its reference, which is exactly the state reconciliation resolves.
        logger.warning(
            "Payout %s was submitted as %s and the outcome is unknown; left for reconciliation",
            payout.pk,
            payout.transfer_reference,
        )
        return payout

    return _apply_transfer_result(payout, result, actor_type=actor_type)


def _apply_transfer_result(
    payout: PayoutRequest, result: TransferResult, *, actor_type: str
) -> PayoutRequest:
    """Records what the provider said about a transfer.

    Shared by execution and reconciliation so both reach the same conclusions
    from the same answer, and there is one place that decides what a provider's
    word means for a payout.
    """
    from apps.payments.services import transition_payout

    with transaction.atomic():
        locked = PayoutRequest.objects.select_for_update().get(pk=payout.pk)

        if locked.is_terminal:
            # Terminal is terminal. A provider answering again about a payout
            # already resolved changes nothing, and this is what stops a late
            # PENDING dragging a PAID payout backwards.
            return locked

        locked.gateway_status = result.raw_status[:40]
        locked.reconciled_at = timezone.now()
        if result.gateway_reference:
            locked.gateway_reference = result.gateway_reference[:120]
        locked.save(
            update_fields=["gateway_status", "gateway_reference", "reconciled_at", "updated_at"]
        )

        if result.state == TransferState.SUCCESSFUL:
            return transition_payout(locked, PayoutStatus.PAID, actor_type=actor_type)

        if result.state == TransferState.FAILED:
            return transition_payout(
                locked,
                PayoutStatus.FAILED,
                actor_type=actor_type,
                reason=result.reason or "The provider could not complete the transfer.",
            )

        # PENDING and UNKNOWN both leave it exactly where it is. Unknown in
        # particular must not become FAILED: a provider that has no record of our
        # reference today may simply not have processed it yet, and releasing the
        # money on that basis is how it gets paid out twice.
        return locked


def _fail(payout: PayoutRequest, *, reason: str, actor_type: str) -> PayoutRequest:
    """Fails a payout that was definitely never sent.

    Clears the reserved reference, because nothing was submitted under it and
    leaving it would make the payout look forever like one that might have moved
    money.
    """
    from apps.payments.services import transition_payout

    with transaction.atomic():
        locked = PayoutRequest.objects.select_for_update().get(pk=payout.pk)
        if locked.is_terminal:
            return locked

        locked.transfer_reference = ""
        locked.submitted_at = None
        locked.save(update_fields=["transfer_reference", "submitted_at", "updated_at"])

        return transition_payout(locked, PayoutStatus.FAILED, actor_type=actor_type, reason=reason)


def reconcile_payout(payout_id: Any) -> PayoutRequest:
    """Asks the provider what became of a submitted transfer.

    A read, so it is safe to run as often as needed and safe to run twice. It is
    the only thing that resolves a payout left in the window, and the only path
    by which such a payout ever becomes terminal.
    """
    try:
        payout = PayoutRequest.objects.get(pk=payout_id)
    except PayoutRequest.DoesNotExist, DjangoValidationError, ValueError, TypeError:
        raise PayoutNotFound from None

    if not payout.needs_reconciliation:
        # Either never submitted, so there is nothing to ask about, or already
        # resolved, so the answer cannot change anything.
        return payout

    result = get_transfer_provider().fetch(payout.transfer_reference)

    return _apply_transfer_result(payout, result, actor_type=ActorType.SYSTEM)


def stale_after() -> int:
    return int(settings.PAYOUT_EXECUTION["STALE_AFTER_SECONDS"])
