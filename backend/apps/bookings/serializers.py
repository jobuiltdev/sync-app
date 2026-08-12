from typing import Any, cast

from rest_framework import serializers

from apps.accounts.address import Address
from apps.bookings.models import Booking, BookingStatusEvent
from apps.catalog.models import Service
from apps.catalog.specs import SpecNotRegistered
from apps.providers.models import ProviderProfile


class BookingStatusEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingStatusEvent
        fields = ["id", "from_status", "to_status", "actor_type", "reason", "created_at"]
        read_only_fields = fields


class BookingAddressSerializer(serializers.Serializer):
    """The snapshot, presented as an address rather than as nine flat fields."""

    # `label` is also the name of an attribute on DRF's Field. Declaring a field
    # called label shadows it, which works because the metaclass collects fields
    # before that matters, but the type checker cannot know that.
    label = serializers.CharField(source="address_label")  # type: ignore[assignment]
    street_address = serializers.CharField(source="address_street")
    landmark = serializers.CharField(source="address_landmark")
    area = serializers.CharField(source="address_area")
    lga = serializers.CharField(source="address_lga")
    state = serializers.CharField(source="address_state")
    latitude = serializers.DecimalField(
        source="address_latitude", max_digits=9, decimal_places=6, allow_null=True
    )
    longitude = serializers.DecimalField(
        source="address_longitude", max_digits=9, decimal_places=6, allow_null=True
    )
    directions_note = serializers.CharField(source="address_directions")


class BookingSummarySerializer(serializers.ModelSerializer):
    service_slug = serializers.SlugField(source="service.slug", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    provider_name = serializers.CharField(
        source="provider.display_name", read_only=True, allow_null=True, default=None
    )
    address_summary = serializers.CharField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "reference",
            "status",
            "service_slug",
            "service_name",
            "provider_name",
            "address_summary",
            "scheduled_for",
            "created_at",
        ]
        read_only_fields = fields


class BookingDetailSerializer(serializers.ModelSerializer):
    service_slug = serializers.SlugField(source="service.slug", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True)
    provider_name = serializers.CharField(
        source="provider.display_name", read_only=True, allow_null=True, default=None
    )
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    address = serializers.SerializerMethodField()
    events = BookingStatusEventSerializer(many=True, read_only=True)
    allowed_transitions = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "reference",
            "status",
            "service_slug",
            "service_name",
            "provider_name",
            "customer_name",
            "spec_key",
            "details",
            "address",
            "scheduled_for",
            "completed_at",
            "cancelled_at",
            "created_at",
            "updated_at",
            "events",
            "allowed_transitions",
        ]
        read_only_fields = fields

    @staticmethod
    def get_address(booking: Booking) -> dict:
        return BookingAddressSerializer(booking).data

    @staticmethod
    def get_allowed_transitions(booking: Booking) -> list[str]:
        """What could happen next, so the app renders the right actions.

        Advisory only. Whether this particular caller may perform one is decided by
        the transition endpoint, which checks the actor as well as the edge.
        """
        from apps.bookings.state import targets_from

        return sorted(targets_from(booking.status))


class BookingCreateSerializer(serializers.Serializer):
    """Validates a booking request, including its vertical-specific payload.

    The querysets on the relation fields are what enforce ownership and
    availability: an address belonging to someone else simply is not in the set,
    so it fails as an unknown value rather than as an authorization error that
    would confirm the id exists.
    """

    service_slug = serializers.SlugRelatedField(
        slug_field="slug", queryset=Service.objects.filter(is_active=True)
    )
    #: Optional. Naming a provider sends them a direct offer; omitting it offers
    #: the job to every eligible provider at once, which is the settled hybrid
    #: matching decision.
    provider_id = serializers.PrimaryKeyRelatedField(
        queryset=ProviderProfile.objects.all(),
        pk_field=serializers.UUIDField(),
        required=False,
        allow_null=True,
    )
    address_id = serializers.PrimaryKeyRelatedField(
        queryset=Address.objects.none(), pk_field=serializers.UUIDField()
    )
    details = serializers.JSONField()
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            # Narrowing the queryset here is what enforces address ownership: an
            # address belonging to someone else is simply not a valid choice.
            address_field = cast(serializers.PrimaryKeyRelatedField, self.fields["address_id"])
            address_field.queryset = Address.objects.filter(user=request.user)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        service: Service = attrs["service_slug"]

        try:
            spec = service.spec
        except SpecNotRegistered as exc:
            raise serializers.ValidationError(
                {"service_slug": "This service is not currently bookable."}
            ) from exc

        # The service decides what a valid request looks like. Validating against
        # the spec registered for the chosen service is what stops a payload that
        # is perfectly valid for laundry being accepted as a dispatch request.
        details = attrs.get("details")
        if not isinstance(details, dict):
            raise serializers.ValidationError({"details": "Expected an object."})

        details_serializer = spec.details_serializer(data=details)
        if not details_serializer.is_valid():
            raise serializers.ValidationError({"details": details_serializer.errors})

        attrs["details"] = details_serializer.validated_data
        return attrs


class BookingTransitionSerializer(serializers.Serializer):
    """Body for the guarded action endpoints.

    Carries a reason only. The target status is fixed by the endpoint, never
    supplied by the client, so there is no way to ask for an arbitrary status.
    """

    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
