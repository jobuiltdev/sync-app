"""Booking work that happens when nobody is looking.

One task: closing offers whose window has passed. Until now an offer expired only
in the sense that `is_expired` returned True the next time somebody looked at it,
which meant a booking nobody happened to open stayed in MATCHING forever and a
customer waited on a job no provider could still take.

**Safe to retry.** It writes only our own rows, through the guarded lifecycle,
and every write is conditional on state it re-reads under a lock. Running it
twice against the same offers does nothing the second time.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.offers import Offer, OfferStatus
from apps.bookings.state import ActorType, BookingStatus
from apps.common.tasks import batched, safe_task
from apps.notifications import service as notifications
from apps.notifications.events import EventType

logger = logging.getLogger(__name__)


@safe_task(name="apps.bookings.tasks.expire_stale_offers")
def expire_stale_offers() -> dict[str, int]:
    """Closes offers whose window has passed, and expires bookings nobody took.

    Bounded, and the bound is per run rather than per booking: whatever is left
    is picked up on the next tick a minute later.

    Two workers running this at the same instant is safe and is tested. Each
    offer is locked before it is touched, and the booking is locked before it is
    moved, so the loser of any race finds the work already done and skips it.
    """
    limit = settings.TASK_BATCH_SIZE
    now = timezone.now()

    stale = (
        Offer.objects.filter(
            status=OfferStatus.PENDING,
            expires_at__lte=now,
            # Only offers on bookings still looking for somebody. An offer on a
            # booking that was taken or withdrawn was already superseded when
            # that happened.
            booking__status=BookingStatus.MATCHING,
        )
        .order_by("expires_at")
        .values_list("pk", flat=True)
    )

    expired = 0
    bookings_touched: set = set()

    for offer_id in batched(stale, limit):
        booking_id = _expire_one(offer_id)
        if booking_id is not None:
            expired += 1
            bookings_touched.add(booking_id)

    # Done after the offers, so a booking whose last two offers both lapsed in
    # this run is considered once rather than twice.
    expired_bookings = sum(_expire_booking_if_exhausted(pk) for pk in bookings_touched)

    if expired or expired_bookings:
        logger.info("Expired %d offer(s); %d booking(s) had none left", expired, expired_bookings)

    return {"offers_expired": expired, "bookings_expired": expired_bookings}


def _expire_one(offer_id) -> object | None:
    """Marks one offer expired, or does nothing if somebody got there first.

    Returns the booking it belonged to when it did something, so the caller knows
    which bookings are worth re-examining.
    """
    with transaction.atomic():
        offer = (
            Offer.objects.select_for_update()
            .select_related("provider__user", "booking__service")
            .filter(pk=offer_id, status=OfferStatus.PENDING)
            .first()
        )
        if offer is None:
            # Another worker took it, or the provider answered in the meantime.
            return None

        if not offer.is_expired:
            # The window moved, or the clock did. Not ours to close.
            return None

        offer.status = OfferStatus.EXPIRED
        offer.responded_at = timezone.now()
        offer.save(update_fields=["status", "responded_at", "updated_at"])

        # So a provider's job list and their phone agree about what is still
        # open. Inside the lock, and therefore inside the transaction, so a run
        # that rolls back tells nobody a job closed when it did not.
        notifications.offer_resolved(offer, EventType.OFFER_EXPIRED)

        return offer.booking_id


def _expire_booking_if_exhausted(booking_id) -> int:
    """Moves a booking to EXPIRED once no offer on it can still be answered.

    The lifecycle already defines this: `MATCHING -> EXPIRED` for a request no
    provider took, driven by SYSTEM. Nothing new is invented here, and the move
    goes through the same guarded transition a declined-by-everybody booking
    takes, so the history row is written the same way.
    """
    from apps.bookings.models import Booking
    from apps.bookings.services import IllegalTransition, transition

    with transaction.atomic():
        booking = Booking.objects.select_for_update().filter(pk=booking_id).first()
        if booking is None or booking.status != BookingStatus.MATCHING:
            return 0

        if Offer.objects.filter(booking=booking, status=OfferStatus.PENDING).exists():
            # Somebody can still take it.
            return 0

        try:
            transition(
                booking,
                BookingStatus.EXPIRED,
                actor_type=ActorType.SYSTEM,
                reason="Every offer lapsed unanswered",
                # Which run did this, so an operator asking why a booking
                # expired has the answer in the history row itself.
                metadata={"task": "expire_stale_offers"},
            )
        except IllegalTransition:
            # Something moved it between the lock and here. The lifecycle
            # refusing is the correct outcome, not an error worth raising.
            return 0

        return 1
