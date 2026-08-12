"""The booking lifecycle, in one authoritative place.

Every status change in the system goes through `transition()`. Nothing assigns
`booking.status` directly, and the API never accepts a status from a client. That
is what makes the table below the whole truth about how a booking can move.

The statuses are the canonical set from docs/architecture.md. M3 implements the
subset a booking reaches without quoting, payment or matching:

    ASSIGNED -> [EN_ROUTE] -> IN_PROGRESS -> AWAITING_CONFIRMATION -> COMPLETED

EN_ROUTE is optional because ASSIGNED reaches IN_PROGRESS directly as well, so a
service with no travel step simply never uses it. DRAFT, QUOTED, PENDING_PAYMENT,
MATCHING, EXPIRED and DISPUTED are deliberately absent: the milestones that give
them meaning have not been built, and defining them now would be guessing.
"""

from django.db import models


class BookingStatus(models.TextChoices):
    ASSIGNED = "ASSIGNED", "Assigned"
    EN_ROUTE = "EN_ROUTE", "Provider on the way"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION", "Awaiting customer confirmation"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class ActorType(models.TextChoices):
    CUSTOMER = "CUSTOMER", "Customer"
    PROVIDER = "PROVIDER", "Provider"
    SYSTEM = "SYSTEM", "System"
    ADMIN = "ADMIN", "Admin"


#: Where a booking begins. A customer picks the provider directly in M3, so there
#: is nothing to match and the booking is assigned on creation. When M4 adds offers
#: and provider acceptance, MATCHING is inserted before this and the transition
#: table gains a row; nothing else here changes.
INITIAL_STATUS = BookingStatus.ASSIGNED

TERMINAL_STATUSES = frozenset({BookingStatus.COMPLETED, BookingStatus.CANCELLED})

#: Legal moves, and who may make each one. Actors matter as much as the edges: a
#: customer must not be able to declare work in progress, and a provider must not
#: be able to confirm on the customer's behalf that a job was done well.
ALLOWED_TRANSITIONS: dict[str, dict[str, frozenset[str]]] = {
    BookingStatus.ASSIGNED: {
        BookingStatus.EN_ROUTE: frozenset({ActorType.PROVIDER}),
        BookingStatus.IN_PROGRESS: frozenset({ActorType.PROVIDER}),
        BookingStatus.CANCELLED: frozenset({ActorType.CUSTOMER, ActorType.PROVIDER}),
    },
    BookingStatus.EN_ROUTE: {
        BookingStatus.IN_PROGRESS: frozenset({ActorType.PROVIDER}),
        BookingStatus.CANCELLED: frozenset({ActorType.CUSTOMER, ActorType.PROVIDER}),
    },
    BookingStatus.IN_PROGRESS: {
        # The provider says the work is done; the customer decides whether it is.
        BookingStatus.AWAITING_CONFIRMATION: frozenset({ActorType.PROVIDER}),
    },
    BookingStatus.AWAITING_CONFIRMATION: {
        BookingStatus.COMPLETED: frozenset({ActorType.CUSTOMER}),
    },
    BookingStatus.COMPLETED: {},
    BookingStatus.CANCELLED: {},
}


def targets_from(current: str) -> frozenset[str]:
    return frozenset(ALLOWED_TRANSITIONS.get(current, {}))


def is_allowed(current: str, target: str, actor_type: str) -> bool:
    return actor_type in ALLOWED_TRANSITIONS.get(current, {}).get(target, frozenset())


def actors_for(current: str, target: str) -> frozenset[str]:
    return ALLOWED_TRANSITIONS.get(current, {}).get(target, frozenset())
