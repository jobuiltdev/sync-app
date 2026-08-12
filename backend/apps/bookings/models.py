import secrets

from django.conf import settings
from django.db import models

from apps.accounts.address import Address
from apps.bookings.state import ActorType, BookingStatus
from apps.catalog.models import Service
from apps.common.models import BaseModel
from apps.common.nigeria import NigerianState
from apps.providers.models import ProviderProfile

#: Excludes characters people confuse when reading a reference aloud to support:
#: no O versus 0, no I versus 1.
REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
REFERENCE_LENGTH = 6


def generate_reference() -> str:
    return "SY-" + "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(REFERENCE_LENGTH))


class Booking(BaseModel):
    """A customer's request for one service from one provider.

    The address is copied onto the booking rather than referenced. A booking is a
    historical record of where a job was requested, and an Address is a mutable
    row a customer edits or deletes freely. Pointing at it would mean last month's
    completed job silently moves house when the customer updates their flat number.
    `source_address` keeps the link for convenience and is allowed to go null.

    `details` holds the vertical-specific payload, validated on the way in against
    the spec registered for the service. `spec_key` is copied alongside it so the
    payload stays interpretable even if the Service is later repointed.
    """

    reference = models.CharField(
        max_length=12,
        unique=True,
        default=generate_reference,
        editable=False,
        help_text="Short human-readable id, quoted in support conversations.",
    )

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        # A booking is a record of something that happened between two people. It
        # must outlive a profile edit, so an account with bookings is deactivated
        # rather than deleted.
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    provider = models.ForeignKey(
        ProviderProfile,
        on_delete=models.PROTECT,
        related_name="bookings",
        # Nullable so that M4's automatic matching can create a booking before a
        # provider exists for it. The M3 API requires one, because the customer
        # chooses directly.
        null=True,
        blank=True,
    )
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="bookings")

    status = models.CharField(
        max_length=24, choices=BookingStatus.choices, default=BookingStatus.ASSIGNED
    )

    spec_key = models.CharField(max_length=60, editable=False)
    details = models.JSONField(default=dict)

    scheduled_for = models.DateTimeField(
        null=True, blank=True, help_text="Null for an on-demand request."
    )

    # --- address snapshot, taken at creation and never rewritten ---------------
    source_address = models.ForeignKey(
        Address,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
        help_text="The saved address this was copied from, if it still exists.",
    )
    address_label = models.CharField(max_length=10, blank=True)
    address_street = models.CharField(max_length=255)
    address_landmark = models.CharField(max_length=255)
    address_area = models.CharField(max_length=120, blank=True)
    address_lga = models.CharField(max_length=120, blank=True)
    address_state = models.CharField(max_length=20, choices=NigerianState.choices)
    address_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    address_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    address_directions = models.TextField(blank=True)

    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "bookings_booking"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(address_landmark=""),
                name="bookings_booking_landmark_not_empty",
            ),
            models.CheckConstraint(
                condition=~models.Q(address_street=""),
                name="bookings_booking_street_not_empty",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(address_latitude__isnull=True, address_longitude__isnull=True)
                    | models.Q(address_latitude__isnull=False, address_longitude__isnull=False)
                ),
                name="bookings_booking_coordinates_paired",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["provider", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.reference} ({self.service_id and self.service.name})"

    @property
    def is_terminal(self) -> bool:
        from apps.bookings.state import TERMINAL_STATUSES

        return self.status in TERMINAL_STATUSES

    @property
    def address_summary(self) -> str:
        parts = [self.address_street, self.address_landmark, self.address_area]
        return ", ".join(part for part in parts if part)

    def snapshot_address(self, address: Address) -> None:
        """Copies an address onto this booking.

        Called once, at creation. Nothing updates a snapshot afterwards: the point
        of it is that it stops tracking the source.
        """
        self.source_address = address
        self.address_label = address.label
        self.address_street = address.street_address
        self.address_landmark = address.landmark
        self.address_area = address.area
        self.address_lga = address.lga
        self.address_state = address.state
        self.address_latitude = address.latitude
        self.address_longitude = address.longitude
        self.address_directions = address.directions_note


class BookingStatusEvent(BaseModel):
    """One line of a booking's history. Append-only.

    Rows are never updated or deleted. This is the record of who moved a booking
    and when, which is the first thing anyone asks in a dispute, and a mutable
    history would be worth nothing there.
    """

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="events")
    from_status = models.CharField(max_length=24, choices=BookingStatus.choices, blank=True)
    to_status = models.CharField(max_length=24, choices=BookingStatus.choices)

    actor_type = models.CharField(max_length=10, choices=ActorType.choices)
    # Not a foreign key: the event must survive the actor, and it records who acted
    # at that moment rather than who they are now.
    actor_id = models.UUIDField(null=True, blank=True)

    reason = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "bookings_status_event"
        ordering = ["created_at"]
        indexes = [models.Index(fields=["booking", "created_at"])]

    def __str__(self) -> str:
        return f"{self.booking_id}: {self.from_status or 'new'} -> {self.to_status}"
