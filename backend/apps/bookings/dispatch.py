"""Putting a booking in front of providers, and resolving what they say.

There is no ranking here, and no scoring. Eligibility is a filter, every eligible
provider is offered the job at the same moment, and the first to accept wins. A
ranking or widening strategy is a later decision; inventing one now would bury a
business rule in code nobody agreed on.
"""

from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework import status as http_status

from apps.bookings.offers import Offer, OfferKind, OfferStatus
from apps.bookings.state import ActorType, BookingStatus
from apps.common.exceptions import APIError
from apps.notifications import service as notifications
from apps.notifications.events import EventType
from apps.providers.models import ProviderProfile, VerificationStatus

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.bookings.models import Booking
    from apps.catalog.models import Service


class OfferNotFound(APIError):
    """An offer that is not this provider's, or does not exist.

    One code for both, so an id cannot be probed to discover whose it is. It is a
    404 for the same reason the rest of the API returns 404 on someone else's
    object.
    """

    status_code = http_status.HTTP_404_NOT_FOUND
    default_code = "OFFER_NOT_FOUND"
    default_detail = "That offer could not be found."


class OfferNotActionable(APIError):
    """The offer exists and belongs to this provider, but the moment has passed."""

    status_code = http_status.HTTP_409_CONFLICT
    default_code = "OFFER_ALREADY_RESPONDED"
    default_detail = "You have already responded to this offer."


class OfferExpired(APIError):
    status_code = http_status.HTTP_410_GONE
    default_code = "OFFER_EXPIRED"
    default_detail = "This offer has expired."


class BookingNoLongerAvailable(APIError):
    """Someone else took it, or the customer withdrew it.

    Deliberately does not say which, and never says who. A provider learning that
    a named competitor took the job is information they are not owed.
    """

    status_code = http_status.HTTP_409_CONFLICT
    default_code = "BOOKING_NO_LONGER_AVAILABLE"
    default_detail = "This job is no longer available."


class NoEligibleProviders(APIError):
    status_code = http_status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "NO_ELIGIBLE_PROVIDERS"
    default_detail = "Nobody is available for this service in your area right now."


def offer_ttl() -> timedelta:
    return timedelta(seconds=settings.BOOKING_OFFERS["TTL_SECONDS"])


def eligible_providers(service: Service, state: str) -> QuerySet[ProviderProfile]:
    """Who may be offered this job.

    A filter, not a ranking. Every condition is a fact already recorded in M2:

    * they offer this service, and that offering is active
    * their verification is approved, because an unapproved provider must not be
      sent into a customer's home
    * they have their own switch on
    * they cover the state the job is in, either the whole state or any LGA in it
    """
    return (
        ProviderProfile.objects.filter(
            offered_services__service=service,
            offered_services__is_active=True,
            verification_status=VerificationStatus.APPROVED,
            is_accepting_jobs=True,
        )
        .filter(Q(service_areas__state=state))
        # Every provider matched here is about to be offered the job and then told
        # about it, and telling them needs their user row. Fetched with the
        # provider rather than one query per offer.
        .select_related("user")
        .distinct()
    )


def is_eligible(provider: ProviderProfile, service: Service, state: str) -> bool:
    return eligible_providers(service, state).filter(pk=provider.pk).exists()


@transaction.atomic
def dispatch_offers(
    booking: Booking, direct_provider: ProviderProfile | None = None
) -> list[Offer]:
    """Creates the offers for a booking that has just entered MATCHING.

    A named provider gets a single DIRECT offer. Otherwise every eligible provider
    gets a BROADCAST offer at the same time, and whoever answers first takes it.
    """
    expires_at = timezone.now() + offer_ttl()

    if direct_provider is not None:
        offers = [
            Offer.objects.create(
                booking=booking,
                provider=direct_provider,
                kind=OfferKind.DIRECT,
                expires_at=expires_at,
            )
        ]
        _announce_offers(offers)
        return offers

    providers = list(eligible_providers(booking.service, booking.address_state))
    if not providers:
        raise NoEligibleProviders

    offers = Offer.objects.bulk_create(
        [
            Offer(
                booking=booking,
                provider=provider,
                kind=OfferKind.BROADCAST,
                expires_at=expires_at,
            )
            for provider in providers
        ]
    )

    # An offer nobody is told about is an offer nobody takes. This is the point of
    # the whole notification system for providers: a broadcast that only reaches
    # somebody who happens to have the app open is not a marketplace.
    _announce_offers(offers)

    return offers


def _announce_offers(offers: list[Offer]) -> None:
    """Tells each provider they have been offered work.

    One message each, and each one deduplicated on its own offer, so a booking
    re-dispatched after a failure does not offer the same job twice to the same
    person. Nothing here can raise: `notify` swallows its own failures, and a
    provider who cannot be reached simply does not get told.
    """
    for offer in offers:
        notifications.offer_received(offer)


def _terminal_error(offer: Offer) -> Exception:
    """Why this offer can no longer be acted on, in the provider's terms.

    A superseded offer is not one the provider responded to: somebody else was
    quicker. Telling them they already answered would be simply untrue.
    """
    if offer.status == OfferStatus.SUPERSEDED:
        return BookingNoLongerAvailable()
    if offer.status == OfferStatus.EXPIRED:
        return OfferExpired()
    return OfferNotActionable()


def _respond(offer: Offer, status: str, *, reason: str = "") -> None:
    offer.status = status
    offer.responded_at = timezone.now()
    offer.decline_reason = reason
    offer.save(update_fields=["status", "responded_at", "decline_reason", "updated_at"])


def accept_offer(offer_id, provider: ProviderProfile, actor: User) -> Booking:
    """Takes the job, or explains why it could not be taken.

    The booking row is locked first, so two providers racing for the same job
    serialise behind it. The loser finds the booking already assigned and is told
    the job is gone, rather than both of them being told they have it.

    Failures that mark the offer are raised after the transaction commits. Raising
    from inside would roll the marking back, leaving an offer that says PENDING
    while the caller was told it had lapsed.
    """
    from apps.accounts import policy
    from apps.bookings.models import Booking
    from apps.bookings.services import transition

    policy.enforce(actor, policy.Capability.ACCEPT_JOB)

    error: Exception | None = None
    booking = None

    with transaction.atomic():
        try:
            offer = Offer.objects.select_related("booking").get(pk=offer_id, provider=provider)
        except Offer.DoesNotExist, DjangoValidationError, ValueError, TypeError:
            # Nothing written, so raising here is safe.
            raise OfferNotFound from None

        # Lock the booking, not the offer. The contention is over the booking, and
        # locking the thing being contested is what makes the race deterministic.
        booking = Booking.objects.select_for_update().get(pk=offer.booking_id)
        offer.refresh_from_db()

        if offer.status != OfferStatus.PENDING:
            raise _terminal_error(offer)

        if offer.is_expired:
            _respond(offer, OfferStatus.EXPIRED)
            error = OfferExpired()
        elif booking.status != BookingStatus.MATCHING:
            # Somebody won, or the customer withdrew it while this request waited.
            _respond(offer, OfferStatus.SUPERSEDED)
            error = BookingNoLongerAvailable()
        else:
            try:
                _respond(offer, OfferStatus.ACCEPTED)
            except IntegrityError as exc:
                # The partial unique index is the last word. If it fires, another
                # acceptance committed and this one must lose.
                raise BookingNoLongerAvailable from exc

            # Everyone else was asked but did not get it. Not a decline: they did
            # nothing wrong and their acceptance rate should not record one.
            losing = Offer.objects.filter(booking=booking, status=OfferStatus.PENDING).exclude(
                pk=offer.pk
            )
            # Read before the update, because after it they no longer match. Only
            # the ids and their providers, so the list stays small on a broadcast
            # that went to everybody in a state.
            losers = list(losing.select_related("provider__user", "booking"))

            losing.update(
                status=OfferStatus.SUPERSEDED,
                responded_at=timezone.now(),
                updated_at=timezone.now(),
            )

            booking.provider = provider
            booking.save(update_fields=["provider", "updated_at"])

            transition(
                booking,
                BookingStatus.ASSIGNED,
                actor_type=ActorType.SYSTEM,
                actor_id=actor.id,
                reason="Offer accepted",
                metadata={"offer_id": str(offer.pk), "provider_id": str(provider.pk)},
            )

            # Called inside the transaction on purpose. Nothing is handed to a
            # worker until it commits, so an acceptance that loses the race at the
            # unique index below tells nobody they won.
            notifications.offer_resolved(offer, EventType.OFFER_ACCEPTED)
            for lost in losers:
                notifications.offer_resolved(lost, EventType.OFFER_SUPERSEDED)

    if error is not None:
        raise error

    return booking


def decline_offer(offer_id, provider: ProviderProfile, actor: User, reason: str = "") -> Offer:
    """Turns a job down.

    Declining touches only this provider's offer. If it was the last one standing,
    the booking has nobody left and moves to EXPIRED, which is what the
    architecture defines for a request no provider took.
    """
    from apps.bookings.models import Booking
    from apps.bookings.services import transition

    with transaction.atomic():
        try:
            offer = Offer.objects.select_related("booking").get(pk=offer_id, provider=provider)
        except Offer.DoesNotExist, DjangoValidationError, ValueError, TypeError:
            raise OfferNotFound from None

        booking = Booking.objects.select_for_update().get(pk=offer.booking_id)
        offer.refresh_from_db()

        if offer.status != OfferStatus.PENDING:
            raise _terminal_error(offer)

        _respond(offer, OfferStatus.DECLINED, reason=reason)

        still_open = Offer.objects.filter(booking=booking, status=OfferStatus.PENDING).exists()
        if not still_open and booking.status == BookingStatus.MATCHING:
            transition(
                booking,
                BookingStatus.EXPIRED,
                actor_type=ActorType.SYSTEM,
                reason="Every provider declined",
            )

    return offer
