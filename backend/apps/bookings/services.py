"""Booking operations.

Views validate, authorize and serialize. Everything that changes a booking happens
here, so an admin action or a future background task takes exactly the same path
as an API request.
"""

from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone
from rest_framework import status as http_status

from apps.accounts import policy
from apps.accounts.address import Address
from apps.bookings.models import Booking, BookingStatusEvent
from apps.bookings.state import ActorType, BookingStatus, actors_for, is_allowed, targets_from
from apps.catalog.models import Service
from apps.common.exceptions import APIError

# The whole of this module's contact with messaging. It knows that something
# happened and who it happened to; which channels that reaches, what the message
# says and whether it arrived are entirely the notifications app's business.
from apps.notifications import service as notifications
from apps.providers.models import ProviderProfile

if TYPE_CHECKING:
    from apps.accounts.models import User


class IllegalTransition(APIError):
    """A status change the lifecycle does not permit, or not by this actor."""

    status_code = http_status.HTTP_409_CONFLICT
    default_code = "ILLEGAL_TRANSITION"
    default_detail = "This booking cannot move to that status."


class ProviderUnavailable(APIError):
    default_code = "PROVIDER_NOT_AVAILABLE"
    default_detail = "That provider is not available for this service in your area."


def agreed_price_kobo(service: Service, provider: ProviderProfile | None) -> int:
    """What this booking costs, decided once, at the moment it is requested.

    A customer who named a provider is quoted that provider's price, override
    included. A customer who did not is quoted the catalog price, and the provider
    who wins the broadcast takes the job at the price the customer already agreed
    to. Repricing a job after a provider accepts would mean the figure shown on the
    review screen was never binding, which is a worse promise than a provider
    occasionally earning their catalog rate instead of their override.

    Returns kobo, always an integer. There is no floating point anywhere in the
    money path, here or downstream.
    """
    from apps.providers.models import ProviderService

    if provider is not None:
        offering = ProviderService.objects.filter(provider=provider, service=service).first()
        if offering is not None:
            return offering.effective_price_kobo

    return service.base_price_kobo


def transition(
    booking: Booking,
    target: str,
    *,
    actor_type: str,
    actor_id: Any = None,
    reason: str = "",
    metadata: dict | None = None,
) -> Booking:
    """The only way a booking's status changes.

    Refuses anything the table disallows and anything this actor may not do, and
    writes the history row in the same transaction as the change so the two cannot
    drift apart.
    """
    current = booking.status

    if not is_allowed(current, target, actor_type):
        permitted = actors_for(current, target)
        if permitted:
            detail = (
                f"Only {' or '.join(sorted(permitted)).lower()} can move a booking from "
                f"{current} to {target}."
            )
        else:
            allowed = ", ".join(sorted(targets_from(current))) or "nothing"
            detail = f"A booking in {current} can move to: {allowed}."

        raise IllegalTransition(
            detail,
            details={
                "current_status": current,
                "requested_status": target,
                "allowed_transitions": sorted(targets_from(current)),
            },
        )

    with transaction.atomic():
        booking.status = target
        updated = ["status", "updated_at"]

        now = timezone.now()
        if target == BookingStatus.COMPLETED:
            booking.completed_at = now
            updated.append("completed_at")
        elif target == BookingStatus.CANCELLED:
            booking.cancelled_at = now
            updated.append("cancelled_at")

        booking.save(update_fields=updated)

        BookingStatusEvent.objects.create(
            booking=booking,
            from_status=current,
            to_status=target,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            metadata=metadata or {},
        )

        if target == BookingStatus.COMPLETED:
            # Finishing a job is one of the two things that make money owed. The
            # other is the customer having paid, and either can happen first, so
            # this asks rather than asserts: if the booking is already paid for,
            # the settlement is written in the same transaction as the completion,
            # and if it is not, the payment path writes it when the money lands.
            #
            # An explicit call rather than a signal: this is one of the two places
            # a booking becomes money, and it should be readable here. The import
            # is local because payments depends on bookings for the Booking.
            from apps.payments.services import settle_if_ready

            settle_if_ready(booking)

    # Inside the function but outside the atomic block, so a transition that
    # rolled back tells nobody anything. Every call here is a side effect: none of
    # them can raise, and none of them is read back.
    _announce(booking, target)

    return booking


def _announce(booking: Booking, target: str) -> None:
    """Tells whoever this status change concerns, if anybody.

    Kept apart from `transition` because it is not part of the lifecycle. The
    lifecycle table decides what may happen; this decides who hears about it, and
    conflating the two would put message routing inside a state machine.
    """
    if target == BookingStatus.ASSIGNED:
        # The one a customer is actually waiting for.
        notifications.provider_assigned(booking)
        return

    if target == BookingStatus.CANCELLED:
        # The provider, not the customer. A customer who cancelled their own
        # booking does not need a message saying so, and a booking cancelled
        # before anybody took it has no provider to tell.
        if booking.provider_id:
            notifications.job_cancelled(booking)
        return

    notifications.booking_status_changed(booking, target)


@transaction.atomic
def create_booking(
    *,
    customer: User,
    service: Service,
    address: Address,
    details: dict,
    provider: ProviderProfile | None = None,
    scheduled_for: Any = None,
) -> Booking:
    """Creates a booking, or nothing at all.

    The capability check runs first and outside any write, so a customer who has
    not verified their phone never causes a row to be written. Everything after it
    is one transaction: booking, address snapshot, opening history row and the
    offers commit together or not at all.

    A booking opens in MATCHING. It is a request until a provider takes it, and
    the only route to ASSIGNED is an accepted offer.
    """
    from apps.bookings.dispatch import dispatch_offers, is_eligible

    policy.enforce(customer, policy.Capability.CREATE_BOOKING)

    if address.user_id != customer.id:
        # Belt and braces. The serializer already scopes the address queryset to
        # the requesting customer, so reaching here means a new caller was added.
        raise APIError("That address does not belong to you.", code="ADDRESS_NOT_FOUND")

    if provider is not None and not is_eligible(provider, service, address.state):
        # A named provider is still held to the same bar as a matched one. An
        # unapproved provider must not reach a customer's home by being asked for
        # by name.
        raise ProviderUnavailable

    booking = Booking(
        customer=customer,
        service=service,
        spec_key=service.spec_key,
        details=details,
        scheduled_for=scheduled_for,
        status=BookingStatus.MATCHING,
        total_kobo=agreed_price_kobo(service, provider),
    )
    booking.snapshot_address(address)
    booking.save()

    BookingStatusEvent.objects.create(
        booking=booking,
        from_status="",
        to_status=BookingStatus.MATCHING,
        actor_type=ActorType.CUSTOMER,
        actor_id=customer.id,
        reason="Booking created",
    )

    dispatch_offers(booking, direct_provider=provider)

    # Telling the customer is a side effect of the booking, not part of it. This
    # queues nothing until the transaction commits and swallows its own failures,
    # so a booking cannot fail because a message could not be composed.
    notifications.booking_created(booking)

    return booking
