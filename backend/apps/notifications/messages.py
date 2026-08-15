"""What each message actually says.

Written for the person receiving it, on a phone, possibly on a bad connection,
possibly about money. So: short, plain, and specific about what happened and what
to do next.

**Nothing internal appears in a message.** No database id, no provider response,
no error text, no verification internals. The only identifier that ever goes out
is a reference a person can quote back to support: `SY-8F3K2A` for a booking,
`SYT-...` for a transfer. Amounts are formatted here rather than sent as kobo,
because nobody reads kobo.

An SMS is one message where possible. Termii bills per 160 characters, and a
three-part message about a job offer costs three times as much as a good one.
"""

from collections.abc import Callable
from dataclasses import dataclass

from apps.notifications.events import EventType


@dataclass(frozen=True)
class Message:
    """One rendered message, ready for whichever channel asked for it."""

    subject: str
    body: str

    @property
    def sms(self) -> str:
        """The body alone. An SMS has no subject line."""
        return self.body


def naira(kobo: int) -> str:
    """Kobo as naira, for a person rather than for a ledger.

    Mirrors the mobile formatter deliberately: a customer who sees a figure in
    the app and the same figure in a message should not have to wonder whether
    they are the same number.
    """
    return f"NGN {kobo / 100:,.0f}"


def render(event_type: str, context: dict) -> Message:
    """The message for one event.

    `context` carries only what the caller took from the domain object on
    purpose: references, names and amounts. If a value is not here it is not in
    the message, which is the mechanism that keeps an address or a phone number
    out of an email nobody meant to put it in.
    """
    builder = _BUILDERS.get(event_type)
    if builder is None:
        # An event with no message is a programming error, not a runtime one.
        # Answering with something neutral rather than raising keeps a missing
        # template from being able to affect the domain call that triggered it.
        return Message(subject="Sync", body="There is an update on your Sync account.")

    return builder(context)


def _get(context: dict, key: str, default: str = "") -> str:
    value = context.get(key, default)
    return str(value) if value is not None else default


# --- customer --------------------------------------------------------------


def _booking_created(context: dict) -> Message:
    service = _get(context, "service_name", "your service")
    reference = _get(context, "reference")

    return Message(
        subject=f"Your Sync booking {reference}",
        body=(
            f"Your {service} booking {reference} is in. We are finding you a provider "
            "and will let you know as soon as somebody takes it."
        ),
    )


def _provider_assigned(context: dict) -> Message:
    provider = _get(context, "provider_name", "A provider")
    reference = _get(context, "reference")

    return Message(
        subject=f"{provider} took your booking {reference}",
        body=f"{provider} has accepted your Sync booking {reference} and will be in touch.",
    )


def _en_route(context: dict) -> Message:
    provider = _get(context, "provider_name", "Your provider")

    return Message(
        subject=f"{provider} is on the way",
        body=f"{provider} is on the way for your Sync booking {_get(context, 'reference')}.",
    )


def _in_progress(context: dict) -> Message:
    return Message(
        subject=f"Work has started on {_get(context, 'reference')}",
        body=(
            f"{_get(context, 'provider_name', 'Your provider')} has started work on your "
            f"Sync booking {_get(context, 'reference')}."
        ),
    )


def _awaiting_confirmation(context: dict) -> Message:
    reference = _get(context, "reference")

    return Message(
        subject=f"Confirm the work on {reference}",
        body=(
            f"Your provider has marked booking {reference} finished. Open Sync to confirm "
            "the work was done."
        ),
    )


def _booking_completed(context: dict) -> Message:
    reference = _get(context, "reference")

    return Message(
        subject=f"Booking {reference} is complete",
        body=f"Thank you. Your Sync booking {reference} is complete.",
    )


def _payment_succeeded(context: dict) -> Message:
    amount = naira(int(context.get("amount_kobo", 0)))
    reference = _get(context, "reference")

    return Message(
        subject=f"Payment received for {reference}",
        body=f"We have received your {amount} payment for Sync booking {reference}.",
    )


def _payment_failed(context: dict) -> Message:
    reference = _get(context, "reference")

    return Message(
        subject=f"Payment did not go through for {reference}",
        body=(
            f"Your payment for Sync booking {reference} did not go through. No money has "
            "left your account. Open Sync to try again."
        ),
    )


# --- provider --------------------------------------------------------------


def _offer_received(context: dict) -> Message:
    service = _get(context, "service_name", "A job")
    where = _get(context, "area") or _get(context, "state", "your area")

    return Message(
        subject=f"New job: {service} in {where}",
        body=(
            f"New Sync job: {service} in {where}. Open the app to accept before it goes "
            "to somebody else."
        ),
    )


def _offer_expired(context: dict) -> Message:
    return Message(
        subject="A job offer has closed",
        body=(
            f"The {_get(context, 'service_name', 'job')} offer in "
            f"{_get(context, 'area') or _get(context, 'state', 'your area')} has closed."
        ),
    )


def _offer_accepted(context: dict) -> Message:
    reference = _get(context, "reference")

    return Message(
        subject=f"You took booking {reference}",
        body=(
            f"You have accepted the {_get(context, 'service_name', 'job')}. It is booking "
            f"{reference} in your jobs."
        ),
    )


def _offer_superseded(context: dict) -> Message:
    # Never names who won. Which competitor took a job is not something a
    # provider is owed, and this message is the easiest place to leak it.
    return Message(
        subject="A job was taken by someone else",
        body=(
            f"The {_get(context, 'service_name', 'job')} you were offered has been taken. "
            "Your acceptance rate is not affected."
        ),
    )


def _job_cancelled(context: dict) -> Message:
    reference = _get(context, "reference")

    return Message(
        subject=f"Booking {reference} was cancelled",
        body=f"Your Sync job {reference} has been cancelled.",
    )


def _earnings_available(context: dict) -> Message:
    amount = naira(int(context.get("amount_kobo", 0)))

    return Message(
        subject="You have earnings available",
        body=(
            f"{amount} from booking {_get(context, 'reference')} is now available in your "
            "Sync earnings."
        ),
    )


def _payout_requested(context: dict) -> Message:
    amount = naira(int(context.get("amount_kobo", 0)))

    return Message(
        subject="Payout requested",
        body=f"We have your request to pay out {amount}. We will let you know when it is sent.",
    )


def _payout_processing(context: dict) -> Message:
    amount = naira(int(context.get("amount_kobo", 0)))

    return Message(
        subject="Your payout is on its way",
        body=f"Your {amount} Sync payout has been sent to your bank.",
    )


def _payout_paid(context: dict) -> Message:
    amount = naira(int(context.get("amount_kobo", 0)))

    return Message(
        subject="Your payout has been paid",
        body=f"Your {amount} Sync payout has been paid into your bank account.",
    )


def _payout_failed(context: dict) -> Message:
    # No provider error text. A bank's wording is rarely useful to the person and
    # sometimes says more about our account than about theirs.
    amount = naira(int(context.get("amount_kobo", 0)))

    return Message(
        subject="Your payout did not go through",
        body=(
            f"Your {amount} Sync payout did not go through and the money is back in your "
            "available balance. Check your bank details in the app and try again."
        ),
    )


#: Keyed by the event's string value rather than by the enum member, because
#: `render` is called with whatever was stored on the row.
_BUILDERS: dict[str, Callable[[dict], Message]] = {
    EventType.BOOKING_CREATED: _booking_created,
    EventType.PROVIDER_ASSIGNED: _provider_assigned,
    EventType.BOOKING_EN_ROUTE: _en_route,
    EventType.BOOKING_IN_PROGRESS: _in_progress,
    EventType.BOOKING_AWAITING_CONFIRMATION: _awaiting_confirmation,
    EventType.BOOKING_COMPLETED: _booking_completed,
    EventType.PAYMENT_SUCCEEDED: _payment_succeeded,
    EventType.PAYMENT_FAILED: _payment_failed,
    EventType.OFFER_RECEIVED: _offer_received,
    EventType.OFFER_EXPIRED: _offer_expired,
    EventType.OFFER_ACCEPTED: _offer_accepted,
    EventType.OFFER_SUPERSEDED: _offer_superseded,
    EventType.JOB_CANCELLED: _job_cancelled,
    EventType.EARNINGS_AVAILABLE: _earnings_available,
    EventType.PAYOUT_REQUESTED: _payout_requested,
    EventType.PAYOUT_PROCESSING: _payout_processing,
    EventType.PAYOUT_PAID: _payout_paid,
    EventType.PAYOUT_FAILED: _payout_failed,
}
