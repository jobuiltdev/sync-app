from rest_framework import serializers

from apps.bookings.offers import Offer


class OfferSummarySerializer(serializers.ModelSerializer):
    """A job in the provider's inbox.

    Carries enough of the booking to decide, and nothing that identifies the
    customer beyond where the work is. A provider deciding whether to take a job
    needs the service, the area and the time, not a name and a phone number for
    someone they have no relationship with yet.
    """

    booking_reference = serializers.CharField(source="booking.reference", read_only=True)
    booking_status = serializers.CharField(source="booking.status", read_only=True)
    service_name = serializers.CharField(source="booking.service.name", read_only=True)
    service_slug = serializers.SlugField(source="booking.service.slug", read_only=True)
    area = serializers.CharField(source="booking.address_area", read_only=True)
    lga = serializers.CharField(source="booking.address_lga", read_only=True)
    state = serializers.CharField(source="booking.address_state", read_only=True)
    scheduled_for = serializers.DateTimeField(source="booking.scheduled_for", read_only=True)
    is_actionable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Offer
        fields = [
            "id",
            "kind",
            "status",
            "booking_reference",
            "booking_status",
            "service_name",
            "service_slug",
            "area",
            "lga",
            "state",
            "scheduled_for",
            "sent_at",
            "expires_at",
            "responded_at",
            "is_actionable",
        ]
        read_only_fields = fields


class OfferDetailSerializer(OfferSummarySerializer):
    """Adds what the provider needs to actually do the job.

    The full address and the request details appear here rather than in the list,
    because a provider browsing an inbox has no need for someone's landmark and
    directions until they are deciding on that specific job.
    """

    street_address = serializers.CharField(source="booking.address_street", read_only=True)
    landmark = serializers.CharField(source="booking.address_landmark", read_only=True)
    directions_note = serializers.CharField(source="booking.address_directions", read_only=True)
    spec_key = serializers.CharField(source="booking.spec_key", read_only=True)
    details = serializers.JSONField(source="booking.details", read_only=True)
    decline_reason = serializers.CharField(read_only=True)

    class Meta(OfferSummarySerializer.Meta):
        fields = [
            *OfferSummarySerializer.Meta.fields,
            "street_address",
            "landmark",
            "directions_note",
            "spec_key",
            "details",
            "decline_reason",
        ]
        read_only_fields = fields


class OfferDeclineSerializer(serializers.Serializer):
    """Body for declining. Carries a reason only.

    The outcome is fixed by the endpoint, so there is no way to ask for an
    arbitrary offer status.
    """

    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
