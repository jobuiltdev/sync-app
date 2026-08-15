"""What the marketplace tells people, and how.

The event vocabulary is a closed list. A notification nobody can query for is a
notification nobody can debug, and a free-text type would make the admin useless
the first time somebody typoed one.

**These are side effects.** The domain is authoritative and stays that way: a
notification that fails to send changes nothing about a booking, a payment or a
payout. Nothing here is a second lifecycle, and no business decision is ever made
from a notification's state.
"""

from django.db import models


class EventType(models.TextChoices):
    """Every transactional message this marketplace sends.

    Named for the domain event that caused it rather than for the message, so
    the reason a person was contacted is legible from the row.
    """

    # --- customer ----------------------------------------------------------
    BOOKING_CREATED = "BOOKING_CREATED", "Booking created"
    PROVIDER_ASSIGNED = "PROVIDER_ASSIGNED", "A provider took the job"
    BOOKING_EN_ROUTE = "BOOKING_EN_ROUTE", "Provider on the way"
    BOOKING_IN_PROGRESS = "BOOKING_IN_PROGRESS", "Work started"
    BOOKING_AWAITING_CONFIRMATION = (
        "BOOKING_AWAITING_CONFIRMATION",
        "Work finished, awaiting confirmation",
    )
    BOOKING_COMPLETED = "BOOKING_COMPLETED", "Booking completed"
    PAYMENT_SUCCEEDED = "PAYMENT_SUCCEEDED", "Payment received"
    PAYMENT_FAILED = "PAYMENT_FAILED", "Payment did not go through"

    # --- provider ----------------------------------------------------------
    OFFER_RECEIVED = "OFFER_RECEIVED", "New job offered"
    OFFER_EXPIRED = "OFFER_EXPIRED", "Offer window closed"
    OFFER_ACCEPTED = "OFFER_ACCEPTED", "You took the job"
    OFFER_SUPERSEDED = "OFFER_SUPERSEDED", "Somebody else took it"
    JOB_CANCELLED = "JOB_CANCELLED", "A job was cancelled"
    EARNINGS_AVAILABLE = "EARNINGS_AVAILABLE", "Earnings available"
    PAYOUT_REQUESTED = "PAYOUT_REQUESTED", "Payout requested"
    PAYOUT_PROCESSING = "PAYOUT_PROCESSING", "Payout on its way"
    PAYOUT_PAID = "PAYOUT_PAID", "Payout paid"
    PAYOUT_FAILED = "PAYOUT_FAILED", "Payout failed"


class Channel(models.TextChoices):
    SMS = "SMS", "SMS"
    EMAIL = "EMAIL", "Email"


#: Which channels carry which event.
#:
#: The rule is what the person has to do about it, not how important it feels.
#: SMS interrupts and costs money per message, so it is reserved for things
#: somebody has to act on soon or would want to know while away from the app: a
#: job being offered, a provider arriving, money moving. Everything else is
#: email, which is free, keeps a record, and can be read later.
#:
#: A few events use both, and only where missing it has a real cost: a provider
#: not seeing an offer loses the work, and a failed payout is money that did not
#: arrive.
#:
#: Verification codes are deliberately absent. They belong to the verification
#: system, which owns its own timings, attempt caps and cooldowns, and routing
#: them through here would make one flow depend on two sets of rules.
CHANNEL_POLICY: dict[str, tuple[str, ...]] = {
    # A booking is made in the app, with the confirmation on screen, so the
    # message is a record rather than news.
    EventType.BOOKING_CREATED: (Channel.EMAIL,),
    # News. The customer has been waiting to hear whether anybody took it.
    EventType.PROVIDER_ASSIGNED: (Channel.SMS, Channel.EMAIL),
    # Somebody is about to arrive at their home. This is the most time-critical
    # message in the system.
    EventType.BOOKING_EN_ROUTE: (Channel.SMS,),
    EventType.BOOKING_IN_PROGRESS: (Channel.EMAIL,),
    # The customer has to do something: confirm the work was done.
    EventType.BOOKING_AWAITING_CONFIRMATION: (Channel.SMS, Channel.EMAIL),
    EventType.BOOKING_COMPLETED: (Channel.EMAIL,),
    EventType.PAYMENT_SUCCEEDED: (Channel.EMAIL,),
    # Their booking is not paid for and they may need to try again.
    EventType.PAYMENT_FAILED: (Channel.SMS, Channel.EMAIL),
    # Work, with a window that closes. A provider who misses it loses the job.
    EventType.OFFER_RECEIVED: (Channel.SMS, Channel.EMAIL),
    EventType.OFFER_EXPIRED: (Channel.EMAIL,),
    EventType.OFFER_ACCEPTED: (Channel.EMAIL,),
    EventType.OFFER_SUPERSEDED: (Channel.EMAIL,),
    # A job they were expecting to do is off, which changes their day.
    EventType.JOB_CANCELLED: (Channel.SMS, Channel.EMAIL),
    EventType.EARNINGS_AVAILABLE: (Channel.EMAIL,),
    EventType.PAYOUT_REQUESTED: (Channel.EMAIL,),
    EventType.PAYOUT_PROCESSING: (Channel.EMAIL,),
    # Money arrived, or did not. Both are worth interrupting somebody for.
    EventType.PAYOUT_PAID: (Channel.SMS, Channel.EMAIL),
    EventType.PAYOUT_FAILED: (Channel.SMS, Channel.EMAIL),
}


def channels_for(event_type: str) -> tuple[str, ...]:
    """Which channels this event uses. Unknown events send nothing.

    Returning nothing rather than guessing at a default: an event nobody has
    written a policy for is an event nobody has decided the cost of, and quietly
    sending it by SMS would be spending money on that guess.
    """
    return CHANNEL_POLICY.get(event_type, ())
