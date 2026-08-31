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


#: The option key that makes a clean a deep clean.
#:
#: One Cleaning service with a depth question, rather than two services. The two
#: rows were the same form twice, and a customer had to decide between them from
#: a name before being shown what either includes.
DEEP_CLEAN_OPTION = "depth-deep"


class CleaningSpec(ServiceSpec):
    key = "cleaning"
    details_serializer = CleaningDetailsSerializer

    presentation = {
        "depth": {
            "style": "cards",
            "choice_labels": {
                "STANDARD": "Standard cleaning",
                "DEEP": "Deep cleaning",
            },
            "choice_help": {
                "STANDARD": (
                    "Routine upkeep. Floors, surfaces, kitchen and bathrooms, "
                    "cleaned the way you would weekly."
                ),
                "DEEP": (
                    "Everything in a standard clean, plus inside the oven and fridge, "
                    "skirting boards, tiles, and behind and under furniture."
                ),
            },
        },
        "has_supplies": {
            "style": "yes_no",
            "help_text": "If not, the cleaner brings their own.",
        },
    }

    def option_keys(self, details: dict) -> list[str]:
        return [DEEP_CLEAN_OPTION] if details.get("depth") == "DEEP" else []

    def summary(self, details: dict) -> str:
        return f"{details.get('bedrooms', 0)} bedroom {str(details.get('depth', '')).lower()} clean"


class ErrandsDetailsSerializer(serializers.Serializer):
    tasks = serializers.ListField(
        child=serializers.CharField(max_length=255), min_length=1, max_length=10, label="Tasks"
    )
    budget_cap_kobo = serializers.IntegerField(
        min_value=0, required=False, label="Spending limit", help_text="In kobo."
    )
    #: Stays a boolean so every booking ever made still reads correctly. What
    #: changed is the question: "Requires purchase" was a form label rather than
    #: something anybody would say out loud, and it left customers unsure whether
    #: it meant "will you buy it" or "have I already paid".
    requires_purchase = serializers.BooleanField(
        default=False, label="Will the provider need to buy anything for you?"
    )


class ErrandsSpec(ServiceSpec):
    key = "errands"
    details_serializer = ErrandsDetailsSerializer

    presentation = {
        "requires_purchase": {
            "style": "yes_no",
            # Deliberately says only what is true today. Sync does not front the
            # money for purchases and does not settle them, so this must not
            # imply either.
            "help_text": (
                "The cost of whatever they buy is separate from the service fee "
                "shown here, and you settle it with the provider directly."
            ),
        },
        "tasks": {
            "placeholder": "Pick up my package from the post office",
            "hint": "Add each errand separately.",
        },
        "budget_cap_kobo": {
            "help_text": "The most the provider should spend on your behalf.",
        },
    }

    def summary(self, details: dict) -> str:
        tasks = details.get("tasks") or []
        return tasks[0] if len(tasks) == 1 else f"{len(tasks)} errands"


class HomeServicesDetailsSerializer(serializers.Serializer):
    #: Four trades, not six. Air conditioning and appliance repair were separate
    #: options until a customer had to choose between them and "electrical" for
    #: the same fault, which is a question about our category list rather than
    #: about their problem. Both are electrical work and both are done by the
    #: same person, so they are electrical. `problem_description` carries the
    #: specifics, which is what the provider actually reads.
    #:
    #: OTHER is the fifth, and it exists because a fixed list of trades is a
    #: guess about what breaks in somebody's home. Anyone whose job did not fit
    #: previously had to miscategorise it, and the provider found out on arrival.
    trade = serializers.ChoiceField(
        choices=["PLUMBING", "ELECTRICAL", "CARPENTRY", "PAINTING", "OTHER"],
        label="Trade",
    )
    problem_description = serializers.CharField(max_length=1000, label="What is the problem")
    inspection_first = serializers.BooleanField(
        default=True,
        label="Inspect before quoting",
        help_text="Most repairs cannot be priced without seeing them.",
    )

    #: Enough words to dispatch the right person. Not a format, not a tag list,
    #: and only asked for when the trade itself carries no information.
    OTHER_MIN_LENGTH = 15

    def validate(self, attrs: dict) -> dict:
        if attrs.get("trade") != "OTHER":
            return attrs

        description = (attrs.get("problem_description") or "").strip()
        if len(description) < self.OTHER_MIN_LENGTH:
            raise serializers.ValidationError(
                {
                    "problem_description": (
                        "Tell us what needs doing, in your own words. With no trade "
                        "selected this is all the provider has to go on."
                    )
                }
            )

        return attrs


class HomeServicesSpec(ServiceSpec):
    key = "home_services"
    details_serializer = HomeServicesDetailsSerializer

    presentation = {
        "trade": {
            "choice_labels": {"OTHER": "Something else"},
            "choice_help": {
                "OTHER": "Describe the job below and we will send the right person.",
            },
        },
        "problem_description": {
            "style": "multiline",
            "placeholder": "The kitchen tap drips constantly and the handle is stiff",
            "help_text": "Plain words are fine. The more specific, the better the quote.",
        },
        "inspection_first": {"style": "yes_no"},
    }

    def summary(self, details: dict) -> str:
        trade = str(details.get("trade", ""))
        if trade == "OTHER":
            # "Other" tells a provider nothing. Their own words do.
            description = str(details.get("problem_description", "")).strip()
            return description[:60] or "Other"
        return trade.replace("_", " ").capitalize()


class BeautyDetailsSerializer(serializers.Serializer):
    treatments = serializers.ListField(
        child=serializers.CharField(max_length=120), min_length=1, max_length=10
    )
    venue = serializers.ChoiceField(choices=["AT_HOME", "AT_SALON"], label="Where")
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)


#: Examples per beauty service. Hair, nails and facials share one spec, so the
#: form asked for "treatments" and suggested "Bread, milk, airtime" to everybody:
#: a shopping list, on a beauty booking, from a placeholder hardcoded in the app.
BEAUTY_EXAMPLES: dict[str, str] = {
    "hair": "Box braids, wash and blow dry",
    "nails": "Gel manicure, pedicure",
    "facials-and-skincare": "Deep cleansing facial, extractions",
}


class BeautySpec(ServiceSpec):
    key = "beauty"
    details_serializer = BeautyDetailsSerializer

    presentation = {
        "treatments": {
            "placeholder": "Box braids",
            "hint": "Add each treatment separately.",
        },
        "venue": {
            "choice_labels": {"AT_HOME": "At my place", "AT_SALON": "At the salon"},
        },
        "notes": {
            "style": "multiline",
            "placeholder": "Anything the stylist should know beforehand",
        },
    }

    def presentation_for(self, service=None) -> dict[str, dict]:
        example = BEAUTY_EXAMPLES.get(getattr(service, "slug", ""))
        if not example:
            return self.presentation

        first = example.split(", ")[0]
        return {
            **self.presentation,
            "treatments": {**self.presentation["treatments"], "placeholder": first},
        }

    def summary(self, details: dict) -> str:
        return ", ".join(details.get("treatments") or [])


class LaundryDetailsSerializer(serializers.Serializer):
    item_count = serializers.IntegerField(min_value=1, max_value=200, label="Number of items")
    wash_type = serializers.ChoiceField(
        choices=["WASH_AND_FOLD", "WASH_AND_IRON", "DRY_CLEAN"], label="Wash type"
    )
    express = serializers.BooleanField(default=False, label="Express turnaround")


#: The option key for express turnaround.
#:
#: What it is worth is a commercial decision and lives in the catalog, not here.
#: This names the answer; the `ServiceOption` row carries the amount, so changing
#: the price of express is an admin edit rather than a deploy.
EXPRESS_OPTION = "express"


class LaundrySpec(ServiceSpec):
    key = "laundry"
    details_serializer = LaundryDetailsSerializer

    presentation = {
        "express": {
            "style": "yes_no",
            "help_text": "Back within 24 hours instead of the usual two to three days.",
        },
        "wash_type": {
            "choice_labels": {
                "WASH_AND_FOLD": "Wash and fold",
                "WASH_AND_IRON": "Wash and iron",
                "DRY_CLEAN": "Dry clean",
            },
        },
    }

    def option_keys(self, details: dict) -> list[str]:
        return [EXPRESS_OPTION] if details.get("express") else []

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
