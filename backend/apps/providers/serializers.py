from rest_framework import serializers

from apps.catalog.models import Service
from apps.providers.models import ProviderProfile, ProviderService, ProviderServiceArea


class ProviderProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderProfile
        fields = [
            "id",
            "display_name",
            "bio",
            "provider_type",
            "business_name",
            "verification_status",
            "is_accepting_jobs",
            "created_at",
            "updated_at",
        ]
        # verification_status is adjudicated, never self-declared. Leaving it
        # writable would let a provider approve themselves.
        read_only_fields = ["id", "verification_status", "created_at", "updated_at"]


class ProviderServiceSerializer(serializers.ModelSerializer):
    service_slug = serializers.SlugRelatedField(
        source="service", slug_field="slug", queryset=Service.objects.filter(is_active=True)
    )
    service_name = serializers.CharField(source="service.name", read_only=True)
    effective_price_kobo = serializers.IntegerField(read_only=True)

    class Meta:
        model = ProviderService
        fields = [
            "id",
            "service_slug",
            "service_name",
            "price_override_kobo",
            "effective_price_kobo",
            "experience_years",
            "is_active",
        ]
        read_only_fields = ["id", "service_name", "effective_price_kobo"]

    def validate_price_override_kobo(self, value: int | None) -> int | None:
        if value is not None and value < 0:
            raise serializers.ValidationError("A price cannot be negative.")
        return value


class ProviderServiceAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProviderServiceArea
        fields = ["id", "state", "lga"]
        read_only_fields = ["id"]
