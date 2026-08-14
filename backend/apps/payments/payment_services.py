"""Taking payment for a booking.

Three ways a payment can change state, and all of them go through here:

* **Initialization** creates the intent and asks the provider to start collecting.
  It never marks anything successful.
* **Verification** asks the provider what happened. The customer's app triggers
  it, but the answer comes from the provider, never from the request body.
* **A webhook** is the provider volunteering the same information, and is checked
  against our record in exactly the same way.

The rule underneath all three: **a payment becomes SUCCESSFUL only when the
provider says so and the amount and currency match what we recorded.** A client
cannot assert it, and a provider event about the wrong sum is refused rather than
accepted with the number it happened to carry.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.state import BookingStatus
from apps.payments.errors import (
    BookingNotPayable,
    PaymentAmountMismatch,
    PaymentNotFound,
)
from apps.payments.gateways.base import (
    GatewayEvent,
    GatewayPayment,
    PaymentState,
    get_payment_gateway,
)
from apps.payments.intents import PaymentIntent, PaymentStatus
from apps.payments.money import Currency
from apps.payments.webhooks import WebhookEvent, digest

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.bookings.models import Booking

#: A booking can be paid for from the moment it is a real request until it is
#: over. Cancelled and expired bookings are excluded because there is nothing to
#: pay for; COMPLETED is included on purpose, since paying after the work is done
#: is an ordinary sequence and the settlement waits for the money either way.
PAYABLE_BOOKING_STATUSES = frozenset(
    {
        BookingStatus.MATCHING,
        BookingStatus.ASSIGNED,
        BookingStatus.EN_ROUTE,
        BookingStatus.IN_PROGRESS,
        BookingStatus.AWAITING_CONFIRMATION,
        BookingStatus.COMPLETED,
    }
)


@dataclass(frozen=True)
class PaymentOutcome:
    """What happened to an intent, and whether this call is what changed it."""

    intent: PaymentIntent
    changed: bool
    detail: str = ""


def customer_intents(customer: User):
    """This customer's payments and nobody else's.

    Scoped here as well as in the view, so a caller that is not a view inherits
    the same rule and another customer's payment stays a 404.
    """
    return PaymentIntent.objects.filter(customer=customer)


# --- initialization --------------------------------------------------------


def initialize_payment(
    *,
    booking: Booking,
    customer: User,
    idempotency_key: str = "",
) -> PaymentIntent:
    """Starts collecting the price of a booking.

    The amount is the booking's own snapshotted total. Nothing here reads a
    Service or a ProviderService, so a price change between booking and payment
    cannot alter what the customer is charged.

    The booking row is locked, which makes two simultaneous taps serialise: the
    second finds the intent the first created and returns it rather than asking
    the provider to start a second collection.
    """
    from apps.bookings.models import Booking

    if booking.customer_id != customer.id:
        # Belt and braces. The view scopes its queryset to the requesting
        # customer, so reaching here means a new caller was added.
        raise PaymentNotFound

    with transaction.atomic():
        locked = Booking.objects.select_for_update().get(pk=booking.pk)

        if locked.status not in PAYABLE_BOOKING_STATUSES:
            raise BookingNotPayable(
                details={"booking_status": locked.status},
            )
        if locked.total_kobo <= 0:
            raise BookingNotPayable(
                "This booking has no amount to pay.",
                details={"booking_status": locked.status},
            )

        existing = _reusable_intent(locked, idempotency_key)
        if existing is not None:
            return existing

        gateway = get_payment_gateway()

        intent = PaymentIntent(
            booking=locked,
            customer=customer,
            amount_kobo=locked.total_kobo,
            currency=Currency.NGN,
            status=PaymentStatus.INITIALIZED,
            gateway=gateway.name,
            idempotency_key=idempotency_key,
        )

        # Saved before the provider is called so the reference exists to give
        # them, and so a provider timeout leaves a record we can reconcile
        # against rather than a payment nobody here has heard of.
        try:
            with transaction.atomic():
                intent.save()
        except IntegrityError:
            # The idempotency index fired: another request with this key
            # committed first, and its intent is the one to answer with.
            replay = _reusable_intent(locked, idempotency_key)
            if replay is not None:
                return replay
            raise

        started = gateway.initialize(
            reference=intent.reference,
            amount_kobo=intent.amount_kobo,
            email=customer.email,
            currency=intent.currency,
            metadata={"booking_id": str(locked.pk), "booking_reference": locked.reference},
        )

        intent.gateway_reference = started.gateway_reference
        intent.authorization_url = started.authorization_url
        intent.save(update_fields=["gateway_reference", "authorization_url", "updated_at"])

        return intent


def _reusable_intent(booking: Booking, idempotency_key: str) -> PaymentIntent | None:
    """An existing attempt this request should be answered with.

    Three cases, in order. A booking already paid for is answered with the
    payment that settled it. A retry carrying a key we have seen is answered with
    what that key created. And an attempt already in flight is reused rather than
    replaced, because a customer who backgrounds the app mid-payment and comes
    back should return to the payment they left, not start a second one.
    """
    paid = PaymentIntent.objects.filter(booking=booking, status=PaymentStatus.SUCCESSFUL).first()
    if paid is not None:
        return paid

    if idempotency_key:
        replay = PaymentIntent.objects.filter(
            booking=booking, idempotency_key=idempotency_key
        ).first()
        if replay is not None:
            return replay

    return (
        PaymentIntent.objects.filter(booking=booking, status=PaymentStatus.INITIALIZED)
        .order_by("-created_at")
        .first()
    )


# --- applying what the provider says ---------------------------------------


def _apply(intent: PaymentIntent, reported: GatewayPayment) -> PaymentOutcome:
    """Moves an intent to match what the provider reported, or refuses to.

    Everything that decides whether a payment is real happens here, once, so the
    verification endpoint and the webhook cannot disagree about what counts.

    The intent must already be locked by the caller.
    """
    if intent.is_terminal:
        # Terminal is terminal. A late webhook about a payment that already
        # succeeded changes nothing, and one about a payment that already failed
        # must not resurrect it: only a fresh attempt can do that.
        return PaymentOutcome(intent=intent, changed=False, detail=f"already {intent.status}")

    if reported.state == PaymentState.PENDING:
        return PaymentOutcome(intent=intent, changed=False, detail="still pending")

    if reported.state == PaymentState.SUCCESSFUL:
        # The check that matters. A provider reporting success for an amount that
        # is not the one we asked for is not a successful payment for this
        # booking, whatever its own status field says.
        if reported.amount_kobo != intent.amount_kobo:
            raise PaymentAmountMismatch(
                expected_kobo=intent.amount_kobo, reported_kobo=reported.amount_kobo
            )
        if reported.currency and reported.currency.upper() != intent.currency:
            raise PaymentAmountMismatch(
                expected_kobo=intent.amount_kobo,
                reported_kobo=reported.amount_kobo,
                message="That payment was made in a different currency.",
            )

        intent.status = PaymentStatus.SUCCESSFUL
        intent.paid_at = timezone.now()
    else:
        intent.status = PaymentStatus.FAILED
        intent.failed_at = timezone.now()

    intent.gateway_status = reported.raw_status[:40]
    intent.method = reported.method[:40]
    if reported.gateway_reference:
        intent.gateway_reference = reported.gateway_reference[:120]

    try:
        with transaction.atomic():
            intent.save(
                update_fields=[
                    "status",
                    "paid_at",
                    "failed_at",
                    "gateway_status",
                    "method",
                    "gateway_reference",
                    "updated_at",
                ]
            )
    except IntegrityError:
        # Either another attempt for this booking succeeded first, or this
        # provider transaction is already attached to another intent. Both mean
        # this call is not the one that gets to record the money.
        intent.refresh_from_db()
        return PaymentOutcome(intent=intent, changed=False, detail="superseded")

    if intent.is_successful:
        # Money has arrived, which may be the last thing a completed booking was
        # waiting for. Same call the completion path makes, so whichever happens
        # second is the one that writes the settlement.
        from apps.payments.services import settle_if_ready

        settle_if_ready(intent.booking)

    return PaymentOutcome(intent=intent, changed=True, detail=intent.status)


def verify_payment(intent_id: Any, customer: User) -> PaymentOutcome:
    """Asks the provider what happened, and records the answer.

    The customer's app calls this when it thinks the payment finished. What the
    app thinks is not consulted: the only input is the provider's own account of
    the transaction, fetched fresh.
    """
    with transaction.atomic():
        try:
            intent = customer_intents(customer).select_for_update().get(pk=intent_id)
        except PaymentIntent.DoesNotExist, ValueError, TypeError:
            raise PaymentNotFound from None
        except Exception as exc:
            if type(exc).__name__ == "ValidationError":
                raise PaymentNotFound from None
            raise

        if intent.is_terminal:
            return PaymentOutcome(intent=intent, changed=False, detail=f"already {intent.status}")

        reported = get_payment_gateway().fetch(intent.reference)

        if reported.reference and reported.reference != intent.reference:
            # The provider answered about a different transaction. Refusing is the
            # only safe reading: a mismatched reference means our request and its
            # answer are not about the same money.
            raise PaymentNotFound

        return _apply(intent, reported)


# --- webhooks --------------------------------------------------------------


def record_webhook(*, gateway_name: str, event: GatewayEvent, body: bytes) -> WebhookEvent | None:
    """Writes the event down, or reports that it has been seen before.

    Returns None for a duplicate. The unique index does the deciding, so two
    simultaneous deliveries of one event cannot both proceed.
    """
    payment = event.payment

    try:
        with transaction.atomic():
            return WebhookEvent.objects.create(
                gateway=gateway_name,
                event_id=event.event_id,
                event_type=event.event_type,
                reference=payment.reference if payment else "",
                amount_kobo=payment.amount_kobo if payment else None,
                currency=payment.currency[:3] if payment else "",
                payload_digest=digest(body),
            )
    except IntegrityError:
        return None


def apply_webhook_event(event: GatewayEvent, *, gateway_name: str, body: bytes) -> str:
    """Handles one provider event, exactly once.

    Returns a short description of what it did, which is recorded on the event and
    is what makes an unexplained "nothing happened" impossible to confuse with a
    bug later.
    """
    record = record_webhook(gateway_name=gateway_name, event=event, body=body)
    if record is None:
        return "duplicate"

    if event.payment is None or not event.payment.reference:
        record.mark_processed("no payment in event")
        return "ignored"

    with transaction.atomic():
        intent = (
            PaymentIntent.objects.select_for_update()
            .filter(reference=event.payment.reference)
            .first()
        )

        if intent is None:
            # An event about a reference we never issued. Normal in a shared
            # provider account, and not something to raise about.
            record.mark_processed("unknown reference")
            return "unknown reference"

        try:
            outcome = _apply(intent, event.payment)
        except PaymentAmountMismatch:
            # Recorded, deliberately not applied. An event claiming success for
            # the wrong sum is exactly what this check is for, and it must leave
            # the payment untouched.
            record.mark_processed("amount or currency mismatch, not applied")
            return "mismatch"

    record.mark_processed(f"{outcome.detail}{'' if outcome.changed else ' (no change)'}")
    return outcome.detail
