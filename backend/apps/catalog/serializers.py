from rest_framework import serializers

from apps.catalog.models import Service, ServiceCategory, ServiceOption


class ServiceOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceOption
        fields = ["id", "key", "label", "kind", "price_delta_kobo", "sort_order"]
        read_only_fields = fields


class ServiceSummarySerializer(serializers.ModelSerializer):
    """Shape used in lists. Deliberately excludes the details schema and options,
    which are only needed once a customer opens a service."""

    category_slug = serializers.SlugField(source="category.slug", read_only=True)

    class Meta:
        model = Service
        fields = [
            "id",
            "slug",
            "name",
            "summary",
            "category_slug",
            "booking_modes",
            "pricing_model",
            "base_price_kobo",
        ]
        read_only_fields = fields


class ServiceDetailSerializer(serializers.ModelSerializer):
    category_slug = serializers.SlugField(source="category.slug", read_only=True)
    options = ServiceOptionSerializer(many=True, read_only=True)
    details_schema = serializers.SerializerMethodField()

    class Meta:
        model = Service
        fields = [
            "id",
            "slug",
            "name",
            "summary",
            "description",
            "category_slug",
            "booking_modes",
            "pricing_model",
            "base_price_kobo",
            "options",
            "details_schema",
        ]
        read_only_fields = fields

    @staticmethod
    def get_details_schema(service: Service) -> dict:
        """The fields a request for this service must carry.

        Served from the spec so the mobile request form is driven by the API. A new
        vertical becomes available to the app without shipping a new build.
        """
        return service.spec.details_schema()


class ServiceCategorySerializer(serializers.ModelSerializer):
    services = serializers.SerializerMethodField()

    class Meta:
        model = ServiceCategory
        fields = ["id", "slug", "name", "description", "icon_key", "sort_order", "services"]
        read_only_fields = fields

    @staticmethod
    def get_services(category: ServiceCategory) -> list[dict]:
        # Prefetched by the view, so this does not fire a query per category.
        active = [service for service in category.services.all() if service.is_active]
        return list(ServiceSummarySerializer(active, many=True).data)
