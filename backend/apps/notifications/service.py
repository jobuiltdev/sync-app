"""Telling somebody something, without the domain having to care how.

`notify()` is the whole public surface. A domain service calls it with an event
and the safe context for it, and everything after that is this module's problem:
which channels, whether there is a usable destination, when to hand it to a
worker, and what to record.

Three rules hold this together, and they are the reason it is safe to call from
inside a booking or a payment.

**A notification can never break the thing that caused it.** Every failure here
is caught and logged. If this module raises, a customer's booking fails, and a
booking that failed because an SMS could not be composed would be an absurd way
to lose business.

**Nothing is queued until the transaction commits.** Delivery is scheduled with
`transaction.on_commit`, so work that rolled back sends nothing. Without that, a
booking that failed after this point would still have told the customer it
succeeded.

**Sending twice is impossible, not merely unlikely.** Each message carries a
deduplication key built from the event, the subject and the channel, and the
column is unique. A retried task, a redelivered webhook and two workers racing
all produce the same key, and the database keeps one.
"""

import logging
from functools import partial
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction

from apps.notifications.events import Channel, EventType, channels_for
from apps.notifications.models import DeliveryStatus, Notification

if TYPE_CHECKING:
    from apps.accounts.models import User

logger = logging.getLogger(__name__)


def dedupe_key(event_type: str, subject_id: Any, channel: str, recipient_id: Any) -> str:
    """The identity of one message.

    Includes the recipient because one event legitimately goes to several people
    (an offer broadcast is one booking and many providers), and the channel
    because the same news by SMS and by email is two messages, not one.
    """
    return f"{event_type}:{subject_id}:{channel}:{recipient_id}"


def notify(
    *,
    event_type: str,
    recipient: User,
    subject_type: str = "",
    subject_id: Any = None,
    subject_reference: str = "",
    context: dict | None = None,
) -> list[Notification]:
    """Records what to tell somebody, and arranges for it to be sent.

    Returns the notifications it created, which is what tests assert on. Callers
    in the domain ignore the return value: there is nothing useful they could do
    with it, and treating it as meaningful would be the first step towards a
    booking depending on a message.

    Safe to call twice. Safe to call inside a transaction. Safe when the SMS
    provider is down, when the email provider is down, and when the recipient has
    no phone number at all.
    """
    try:
        return _notify(
            event_type=event_type,
            recipient=recipient,
            subject_type=subject_type,
            subject_id=subject_id,
            subject_reference=subject_reference,
            context=context or {},
        )
    except Exception:
        # The whole point. Whatever went wrong here, the booking, the payment or
        # the payout that called it is still correct and still committed.
        logger.exception(
            "Could not record a notification",
            extra={"event_type": event_type, "subject_reference": subject_reference},
        )
        return []


def _enqueue(notification_id: Any, context: dict) -> None:
    """Hands one notification to the queue, and never lets that hurt anybody.

    This runs inside an `on_commit` callback, which is the one place a stray
    exception is genuinely dangerous: the callbacks fire after the commit but
    still inside the caller's stack, so anything raised here surfaces in the
    booking or payment code that has already succeeded. A broker that is down
    would fail a booking that is committed and correct.

    So the queue being unavailable costs a log line and an undelivered message,
    which is the right price.
    """
    from apps.notifications.tasks import deliver_notification

    try:
        deliver_notification.delay(str(notification_id), context)
    except Exception:
        logger.exception(
            "Could not queue a notification for delivery",
            extra={"notification_id": str(notification_id)},
        )


def _notify(
    *,
    event_type: str,
    recipient: User,
    subject_type: str,
    subject_id: Any,
    subject_reference: str,
    context: dict,
) -> list[Notification]:
    created: list[Notification] = []

    for channel in channels_for(event_type):
        key = dedupe_key(event_type, subject_id, channel, recipient.pk)

        try:
            with transaction.atomic():
                notification = Notification.objects.create(
                    event_type=event_type,
                    channel=channel,
                    recipient=recipient,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    subject_reference=subject_reference[:40],
                    dedupe_key=key,
                )
        except IntegrityError:
            # Already recorded. The event happened twice, or a task was retried,
            # or two workers raced. Whichever it was, one message is correct.
            logger.info(
                "Skipped a duplicate notification",
                extra={"event_type": event_type, "channel": channel},
            )
            continue

        created.append(notification)

        # After commit, never before. A transaction that rolls back leaves no
        # row and queues no work, so nothing is sent about something that did
        # not happen. `context` travels with the task rather than being stored,
        # so a message's contents live only as long as its delivery.
        # `partial` rather than a closure, so a loop that records two channels
        # queues two distinct notifications instead of the last one twice.
        transaction.on_commit(partial(_enqueue, notification.pk, dict(context)))

    return created


def destination_for(recipient: User, channel: str) -> str:
    """Where a message on this channel may be sent, or nothing.

    **A channel is only used when that channel is verified.** An unverified phone
    number is a number somebody typed, and it may well be somebody else's: sending
    a customer's address, a provider's name or an amount to it would hand a
    stranger the details of a real booking. An unverified email is the same
    problem with a longer memory.

    Verification codes are exempt and are not sent through here at all, because
    proving a destination is precisely what they are for and requiring
    verification first would make it impossible to ever verify anything.

    Returning nothing is not an error. It is recorded as skipped, which is how an
    operator later answers "why did they never hear about the job".
    """
    if channel == Channel.SMS:
        if not recipient.phone or recipient.phone_verified_at is None:
            return ""
        return recipient.phone

    if channel == Channel.EMAIL:
        if not recipient.email or recipient.email_verified_at is None:
            return ""
        return recipient.email

    return ""


def pending_for(recipient: User):
    """This person's undelivered messages. Used by the tests and the admin."""
    return Notification.objects.filter(recipient=recipient, status=DeliveryStatus.PENDING)


# --- the events, as the domain calls them ----------------------------------
#
# Thin helpers rather than the domain building context dictionaries inline. It
# keeps the shape of each event's context in one place, so a template and its
# caller cannot drift, and it keeps the call site in booking or payment code down
# to a single readable line.


def booking_created(booking) -> None:
    notify(
        event_type=EventType.BOOKING_CREATED,
        recipient=booking.customer,
        subject_type="Booking",
        subject_id=booking.pk,
        subject_reference=booking.reference,
        context={"reference": booking.reference, "service_name": booking.service.name},
    )


def booking_status_changed(booking, status: str) -> None:
    """The customer-facing progress of a job.

    Only the transitions a customer would want to hear about. `MATCHING` and
    `ASSIGNED` have their own events, and the rest of the lifecycle is internal.
    """
    mapping = {
        "EN_ROUTE": EventType.BOOKING_EN_ROUTE,
        "IN_PROGRESS": EventType.BOOKING_IN_PROGRESS,
        "AWAITING_CONFIRMATION": EventType.BOOKING_AWAITING_CONFIRMATION,
        "COMPLETED": EventType.BOOKING_COMPLETED,
    }
    event_type = mapping.get(status)
    if event_type is None:
        return

    provider_name = booking.provider.display_name if booking.provider_id else ""

    notify(
        event_type=event_type,
        recipient=booking.customer,
        subject_type="Booking",
        # The same booking for every status, which is correct: the event type is
        # already part of the deduplication key, so a booking moving through four
        # states produces four distinct keys and four messages. Re-running one
        # transition produces the same key and one message.
        subject_id=booking.pk,
        subject_reference=booking.reference,
        context={
            "reference": booking.reference,
            "service_name": booking.service.name,
            "provider_name": provider_name,
        },
    )


def provider_assigned(booking) -> None:
    notify(
        event_type=EventType.PROVIDER_ASSIGNED,
        recipient=booking.customer,
        subject_type="Booking",
        subject_id=booking.pk,
        subject_reference=booking.reference,
        context={
            "reference": booking.reference,
            "service_name": booking.service.name,
            "provider_name": booking.provider.display_name if booking.provider_id else "",
        },
    )


def job_cancelled(booking) -> None:
    """The provider losing work they had already taken.

    Goes to the provider rather than the customer. A customer who cancelled their
    own booking already knows, and a message telling them so reads as a system
    that is not paying attention.
    """
    notify(
        event_type=EventType.JOB_CANCELLED,
        recipient=booking.provider.user,
        subject_type="Booking",
        subject_id=booking.pk,
        subject_reference=booking.reference,
        context={"reference": booking.reference, "service_name": booking.service.name},
    )


def offer_received(offer) -> None:
    booking = offer.booking

    notify(
        event_type=EventType.OFFER_RECEIVED,
        recipient=offer.provider.user,
        subject_type="Offer",
        subject_id=offer.pk,
        subject_reference=booking.reference,
        # Area and state only. A provider deciding whether to take a job needs to
        # know roughly where it is; the street address is theirs once they have
        # accepted and not before.
        context={
            "service_name": booking.service.name,
            "area": booking.address_area,
            "state": booking.get_address_state_display(),
            "reference": booking.reference,
        },
    )


def offer_resolved(offer, event_type: str) -> None:
    """Accepted, superseded or expired, from the provider's side."""
    booking = offer.booking

    notify(
        event_type=event_type,
        recipient=offer.provider.user,
        subject_type="Offer",
        subject_id=offer.pk,
        subject_reference=booking.reference,
        context={
            "service_name": booking.service.name,
            "area": booking.address_area,
            "state": booking.get_address_state_display(),
            # Only the winner is told the booking reference. A provider who lost
            # has no job to look up, and the message deliberately names nobody.
            "reference": booking.reference if event_type == EventType.OFFER_ACCEPTED else "",
        },
    )


def payment_resolved(intent, succeeded: bool) -> None:
    notify(
        event_type=EventType.PAYMENT_SUCCEEDED if succeeded else EventType.PAYMENT_FAILED,
        recipient=intent.customer,
        subject_type="PaymentIntent",
        subject_id=intent.pk,
        subject_reference=intent.booking.reference,
        context={
            "reference": intent.booking.reference,
            "amount_kobo": intent.amount_kobo,
        },
    )


def earnings_available(settlement) -> None:
    notify(
        event_type=EventType.EARNINGS_AVAILABLE,
        recipient=settlement.provider.user,
        subject_type="BookingSettlement",
        subject_id=settlement.pk,
        subject_reference=settlement.booking.reference,
        # The provider's share, not the customer's total. They are different
        # numbers and telling somebody the wrong one about their own money is
        # the sort of mistake that costs trust.
        context={
            "reference": settlement.booking.reference,
            "amount_kobo": settlement.provider_amount_kobo,
        },
    )


def payout_status(payout, event_type: str) -> None:
    notify(
        event_type=event_type,
        recipient=payout.provider.user,
        subject_type="PayoutRequest",
        subject_id=payout.pk,
        subject_reference=payout.transfer_reference or "",
        context={"amount_kobo": payout.amount_kobo},
    )
