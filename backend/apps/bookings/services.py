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

    return booking


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

    return booking
