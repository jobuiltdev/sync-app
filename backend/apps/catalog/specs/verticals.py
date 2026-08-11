"""The six Phase 1 verticals.

Each declares only what its own requests need. If a change here ever requires
touching booking or payment code, the abstraction has failed and that is the
signal to stop and fix it rather than work around it.
"""

from rest_framework import serializers

from apps.catalog.specs.base import ServiceSpec


class DispatchDetailsSerializer(serializers.Serializer):
    pickup_landmark = serializers.CharField(max_length=255, label="Pickup landmark")
    dropoff_landmark = serializers.CharField(max_length=255, label="Dropoff landmark")
    package_size = serializers.ChoiceField(
        choices=["SMALL", "MEDIUM", "LARGE"], label="Package size"
    )
    package_description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    recipient_phone = serializers.CharField(max_length=20, label="Recipient phone")


class DispatchSpec(ServiceSpec):
    key = "dispatch"
    details_serializer = DispatchDetailsSerializer

    def summary(self, details: dict) -> str:
        return f"{details.get('pickup_landmark', '')} to {details.get('dropoff_landmark', '')}"


class CleaningDetailsSerializer(serializers.Serializer):
    property_type = serializers.ChoiceField(
        choices=["APARTMENT", "HOUSE", "OFFICE"], label="Property type"
    )
    bedrooms = serializers.IntegerField(min_value=0, max_value=20)
    bathrooms = serializers.IntegerField(min_value=0, max_value=20)
    depth = serializers.ChoiceField(choices=["STANDARD", "DEEP"], label="Cleaning depth")
    has_supplies = serializers.BooleanField(
        default=False, label="Customer provides cleaning supplies"
    )


class CleaningSpec(ServiceSpec):
    key = "cleaning"
    details_serializer = CleaningDetailsSerializer

    def summary(self, details: dict) -> str:
        return f"{details.get('bedrooms', 0)} bedroom {str(details.get('depth', '')).lower()} clean"


class ErrandsDetailsSerializer(serializers.Serializer):
    tasks = serializers.ListField(
        child=serializers.CharField(max_length=255), min_length=1, max_length=10, label="Tasks"
    )
    budget_cap_kobo = serializers.IntegerField(
        min_value=0, required=False, label="Spending limit", help_text="In kobo."
    )
    requires_purchase = serializers.BooleanField(default=False)


class ErrandsSpec(ServiceSpec):
    key = "errands"
    details_serializer = ErrandsDetailsSerializer

    def summary(self, details: dict) -> str:
        tasks = details.get("tasks") or []
        return tasks[0] if len(tasks) == 1 else f"{len(tasks)} errands"


class HomeServicesDetailsSerializer(serializers.Serializer):
    trade = serializers.ChoiceField(
        choices=["PLUMBING", "ELECTRICAL", "CARPENTRY", "APPLIANCE", "PAINTING", "AC"],
        label="Trade",
    )
    problem_description = serializers.CharField(max_length=1000, label="What is the problem")
    inspection_first = serializers.BooleanField(
        default=True,
        label="Inspect before quoting",
        help_text="Most repairs cannot be priced without seeing them.",
    )


class HomeServicesSpec(ServiceSpec):
    key = "home_services"
    details_serializer = HomeServicesDetailsSerializer

    def summary(self, details: dict) -> str:
        return str(details.get("trade", "")).replace("_", " ").capitalize()


class BeautyDetailsSerializer(serializers.Serializer):
    treatments = serializers.ListField(
        child=serializers.CharField(max_length=120), min_length=1, max_length=10
    )
    venue = serializers.ChoiceField(choices=["AT_HOME", "AT_SALON"], label="Where")
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)


class BeautySpec(ServiceSpec):
    key = "beauty"
    details_serializer = BeautyDetailsSerializer

    def summary(self, details: dict) -> str:
        return ", ".join(details.get("treatments") or [])


class LaundryDetailsSerializer(serializers.Serializer):
    item_count = serializers.IntegerField(min_value=1, max_value=200, label="Number of items")
    wash_type = serializers.ChoiceField(
        choices=["WASH_AND_FOLD", "WASH_AND_IRON", "DRY_CLEAN"], label="Wash type"
    )
    express = serializers.BooleanField(default=False, label="Express turnaround")


class LaundrySpec(ServiceSpec):
    key = "laundry"
    details_serializer = LaundryDetailsSerializer

    def summary(self, details: dict) -> str:
        return f"{details.get('item_count', 0)} items"


ALL_SPECS: list[ServiceSpec] = [
    DispatchSpec(),
    CleaningSpec(),
    ErrandsSpec(),
    HomeServicesSpec(),
    BeautySpec(),
    LaundrySpec(),
]
