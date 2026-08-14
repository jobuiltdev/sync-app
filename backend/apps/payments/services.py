"""Financial operations.

Every write to the financial domain happens here, so an admin action, a future
transfer adapter and an API request all take the same path and are held to the
same rules.

Two ideas carry the weight of this module:

* **Records are immutable, balances are derived.** There is no stored balance to
  drift out of step with reality. What a provider may withdraw is computed from
  the settlements they earned and the payouts they have already asked for, every
  time it is asked for. A number that is recalculated cannot silently be wrong in
  a way nobody notices for a month.
* **The database has the last word.** Locks make the races deterministic and the
  constraints make them safe. Neither is trusted alone, because an application
  check that two transactions can both pass is not a guarantee.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.accounts import policy
from apps.bookings.state import ActorType, BookingStatus
from apps.payments.destinations import PayoutDestination
from apps.payments.errors import (
    InsufficientBalance,
    InvalidPayoutAmount,
    InvalidPayoutDestination,
    PayoutAlreadyRequested,
    PayoutNotActionable,
    PayoutNotFound,
    SettlementUnavailable,
)
from apps.payments.money import Currency, split_commission
from apps.payments.payouts import (
    RESERVING_STATUSES,
    SPENT_STATUSES,
    TERMINAL_STATUSES,
    PayoutRequest,
    PayoutStatus,
    actors_for,
    is_allowed,
    targets_from,
)
from apps.payments.settlements import BookingSettlement, SettlementStatus
from apps.providers.models import ProviderProfile

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.bookings.models import Booking


def commission_rate_bps() -> int:
    """The rate applied to a booking settled right now.

    Read at the moment of settlement and then copied onto the row, so changing
    this setting affects the next completed booking and never a past one.
    """
    return int(settings.PLATFORM_COMMISSION["RATE_BPS"])


# --- settlement ------------------------------------------------------------


def create_settlement(booking: Booking) -> BookingSettlement:
    """Records what a completed booking earned, exactly once.

    Called as a booking reaches COMPLETED. Safe to call again with the same
    booking from anywhere, by any number of concurrent callers: the booking row is
    locked so the racers serialise, and the one-to-one constraint is the final word
    if they somehow do not.

    The amount comes from the booking's own agreed total, which was fixed when the
    customer requested the job. Nothing here reads a Service or a ProviderService
    price, which is what makes a later price change unable to reach backwards into
    money that has already been earned.
    """
    from apps.bookings.models import Booking

    with transaction.atomic():
        # Lock the booking, which is the row every settlement for it must pass
        # through, then re-read the status from the database rather than trusting
        # the instance the caller happened to be holding.
        locked = Booking.objects.select_for_update().get(pk=booking.pk)

        existing = BookingSettlement.objects.filter(booking=locked).first()
        if existing is not None:
            return existing

        if locked.status != BookingStatus.COMPLETED:
            raise SettlementUnavailable
        if locked.provider_id is None:
            # Unreachable through the lifecycle, since COMPLETED is only ever
            # arrived at through an accepted offer. Refused explicitly anyway,
            # because a settlement with nobody to pay is not a thing to guess at.
            raise SettlementUnavailable

        split = split_commission(locked.total_kobo, commission_rate_bps())

        try:
            # A savepoint, so that losing the race leaves the surrounding
            # transaction usable instead of poisoned.
            with transaction.atomic():
                return BookingSettlement.objects.create(
                    booking=locked,
                    provider_id=locked.provider_id,
                    gross_amount_kobo=split.gross_kobo,
                    commission_amount_kobo=split.commission_kobo,
                    provider_amount_kobo=split.provider_kobo,
                    commission_rate_bps=split.rate_bps,
                    currency=Currency.NGN,
                    status=SettlementStatus.PAYABLE,
                )
        except IntegrityError:
            # Somebody committed one between the read above and this write. Their
            # row is as good as ours would have been.
            return BookingSettlement.objects.get(booking=locked)


# --- earnings --------------------------------------------------------------


@dataclass(frozen=True)
class Earnings:
    """A provider's financial position, derived rather than stored.

    Every field is kobo, and every one of them is a sum over immutable rows.
    """

    currency: str
    settlement_count: int
    gross_earned_kobo: int
    commission_kobo: int
    net_earned_kobo: int
    #: Asked for and not yet resolved. Not spent, but not available either.
    reserved_kobo: int
    paid_out_kobo: int
    available_kobo: int


def _sum(queryset: Any, field: str) -> int:
    return int(queryset.aggregate(total=Coalesce(Sum(field), 0))["total"])


def available_balance(provider: ProviderProfile) -> Earnings:
    """What this provider has earned, and what of it they may still ask for.

        available = earned - already asked for - already paid

    Money sitting in a REQUESTED or PROCESSING payout is subtracted even though it
    has not left, because counting it as available is precisely how the same
    earnings get claimed twice.

    A failed or cancelled payout subtracts nothing, so the money returns to the
    balance by arithmetic rather than by anyone remembering to add it back.
    """
    settlements = BookingSettlement.objects.filter(
        provider=provider, status=SettlementStatus.PAYABLE
    )
    payouts = PayoutRequest.objects.filter(provider=provider)

    gross = _sum(settlements, "gross_amount_kobo")
    commission = _sum(settlements, "commission_amount_kobo")
    net = _sum(settlements, "provider_amount_kobo")

    reserved = _sum(payouts.filter(status__in=RESERVING_STATUSES), "amount_kobo")
    paid = _sum(payouts.filter(status__in=SPENT_STATUSES), "amount_kobo")

    return Earnings(
        currency=Currency.NGN,
        settlement_count=settlements.count(),
        gross_earned_kobo=gross,
        commission_kobo=commission,
        net_earned_kobo=net,
        reserved_kobo=reserved,
        paid_out_kobo=paid,
        available_kobo=net - reserved - paid,
    )


# --- payout destination ----------------------------------------------------


def usable_destination(provider: ProviderProfile) -> PayoutDestination:
    """The account this provider may be paid into, or a refusal saying so."""
    destination = PayoutDestination.objects.filter(provider=provider).first()
    if destination is None or not destination.is_usable:
        raise InvalidPayoutDestination
    return destination


def set_destination(
    provider: ProviderProfile,
    *,
    bank_code: str,
    bank_name: str,
    account_name: str,
    account_number: str,
) -> PayoutDestination:
    """Records where a provider is paid, keeping only what may be kept.

    The account number is hashed and reduced to its last four digits on the way in
    and is not held anywhere afterwards.
    """
    # Fetched rather than get_or_create'd, so the row is complete before it is
    # written. get_or_create would insert with an empty hash and trip the
    # constraint that says a destination must have one.
    destination = PayoutDestination.objects.filter(provider=provider).first()
    if destination is None:
        destination = PayoutDestination(provider=provider)

    destination.bank_code = bank_code
    destination.bank_name = bank_name
    destination.account_name = account_name
    destination.is_active = True
    destination.set_account_number(account_number)
    # Whatever token a transfer provider had issued was issued against the old
    # account, so it does not describe this one.
    destination.provider_reference = ""
    destination.save()

    return destination


# --- payout lifecycle ------------------------------------------------------


def request_payout(
    *,
    provider: ProviderProfile,
    actor: User,
    amount_kobo: int,
    idempotency_key: str = "",
) -> PayoutRequest:
    """Asks to be paid some of what has been earned.

    The capability check runs first, outside any transaction, so a provider who has
    not verified their contact details never causes a financial row to be written.

    Everything after it happens behind a lock on the provider's own row. Two
    requests arriving at the same instant serialise there, so the second one reads
    a balance that already accounts for the first, and the unique index on
    in-flight payouts refuses it even if that reasoning were wrong.
    """
    policy.enforce(actor, policy.Capability.REQUEST_PAYOUT)

    if not isinstance(amount_kobo, int) or isinstance(amount_kobo, bool) or amount_kobo <= 0:
        raise InvalidPayoutAmount

    with transaction.atomic():
        # Every payout for this provider passes through this row, which makes it
        # the natural thing to serialise on. There is no balance row to lock,
        # because a stored balance is the thing this design does without.
        locked = ProviderProfile.objects.select_for_update().get(pk=provider.pk)

        if idempotency_key:
            replay = PayoutRequest.objects.filter(
                provider=locked, idempotency_key=idempotency_key
            ).first()
            if replay is not None:
                # The same request arriving twice over a bad connection. Answering
                # with the payout it already created is the whole point of the key.
                return replay

        # Checked before the balance so a provider with no account on file is told
        # what to fix rather than how much they could have withdrawn.
        usable_destination(locked)

        if PayoutRequest.objects.filter(provider=locked, status__in=RESERVING_STATUSES).exists():
            raise PayoutAlreadyRequested

        earnings = available_balance(locked)
        if amount_kobo > earnings.available_kobo:
            raise InsufficientBalance(earnings.available_kobo, amount_kobo)

        try:
            with transaction.atomic():
                return PayoutRequest.objects.create(
                    provider=locked,
                    amount_kobo=amount_kobo,
                    currency=Currency.NGN,
                    status=PayoutStatus.REQUESTED,
                    idempotency_key=idempotency_key,
                )
        except IntegrityError as exc:
            # The in-flight index fired. Another request committed first, and this
            # one must not become a second claim on the same earnings.
            raise PayoutAlreadyRequested from exc


def transition_payout(
    payout: PayoutRequest,
    target: str,
    *,
    actor_type: str,
    reason: str = "",
) -> PayoutRequest:
    """The only way a payout's status changes.

    Refuses anything the table disallows and anything this actor may not do. There
    is no endpoint anywhere that accepts a status from a client, and no code path
    that gives a provider the SYSTEM or ADMIN actor type, so the pair of those
    facts is what stops a provider marking their own payout paid.
    """
    if not is_allowed(payout.status, target, actor_type):
        permitted = actors_for(payout.status, target)
        if permitted:
            detail = (
                f"Only {' or '.join(sorted(permitted)).lower()} can move a payout from "
                f"{payout.status} to {target}."
            )
        else:
            allowed = ", ".join(sorted(targets_from(payout.status))) or "nothing"
            detail = f"A payout in {payout.status} can move to: {allowed}."

        raise PayoutNotActionable(
            detail,
            details={
                "current_status": payout.status,
                "requested_status": target,
                "allowed_transitions": sorted(targets_from(payout.status)),
            },
        )

    payout.status = target
    updated = ["status", "updated_at"]

    if target in TERMINAL_STATUSES:
        payout.processed_at = timezone.now()
        updated.append("processed_at")

    if target == PayoutStatus.FAILED:
        payout.failure_reason = reason[:255]
        updated.append("failure_reason")

    payout.save(update_fields=updated)
    return payout


def provider_payouts(provider: ProviderProfile):
    """This provider's payouts and nobody else's.

    The scoping that makes another provider's payout a 404 rather than a 403 lives
    here as well as in the view, so a future caller that is not a view inherits it.
    """
    return PayoutRequest.objects.filter(provider=provider)


def cancel_payout(payout_id: Any, provider: ProviderProfile) -> PayoutRequest:
    """The provider calling off their own request.

    The only lifecycle move a provider may make. It is theirs to make because
    cancelling releases money back to them and takes nothing from anybody.
    """
    with transaction.atomic():
        try:
            payout = provider_payouts(provider).select_for_update().get(pk=payout_id)
        except PayoutRequest.DoesNotExist, DjangoValidationError, ValueError, TypeError:
            raise PayoutNotFound from None

        return transition_payout(payout, PayoutStatus.CANCELLED, actor_type=ActorType.PROVIDER)


def start_processing(payout: PayoutRequest, *, actor_type: str = ActorType.ADMIN) -> PayoutRequest:
    """Hands a payout to whoever moves the money.

    No transfer provider is integrated, so today this is an operator in the admin
    saying they are doing it by hand. When an adapter exists it calls this with
    SYSTEM, and nothing else about the lifecycle changes.
    """
    return transition_payout(payout, PayoutStatus.PROCESSING, actor_type=actor_type)


def mark_paid(payout: PayoutRequest, *, actor_type: str = ActorType.ADMIN) -> PayoutRequest:
    return transition_payout(payout, PayoutStatus.PAID, actor_type=actor_type)


def mark_failed(
    payout: PayoutRequest, *, reason: str, actor_type: str = ActorType.ADMIN
) -> PayoutRequest:
    """Records that the money did not move.

    The amount returns to the available balance by arithmetic: a FAILED payout
    reserves nothing, so the next call to `available_balance` simply stops
    subtracting it. Nothing has to remember to credit anything back.
    """
    return transition_payout(payout, PayoutStatus.FAILED, actor_type=actor_type, reason=reason)
