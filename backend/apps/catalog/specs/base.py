"""The contract every service vertical implements.

This is the mechanism that keeps six categories from becoming six products. A
booking will carry a validated `details` payload, and the spec registered against
a service owns the shape of that payload. Core booking code never learns the
vocabulary of dispatch or laundry, so adding a seventh category is a new module
here plus a Service row, not a migration against the booking tables.

Pricing is deliberately absent. It belongs beside the Quote model that consumes
it, which arrives in M3; adding an unused hook now would only invite guesses about
its signature.
"""

from abc import ABC, abstractmethod

from rest_framework import serializers


class ServiceSpec(ABC):
    """Per-vertical requirements for one kind of service."""

    #: Matches Service.spec_key. Stable, because it is persisted against rows.
    key: str

    @property
    @abstractmethod
    def details_serializer(self) -> type[serializers.Serializer]:
        """Validates and shapes the vertical-specific part of a request."""

    def summary(self, details: dict) -> str:
        """One line describing a request, for lists and notifications.

        Defaults to nothing rather than guessing at a format, so a vertical that
        has not thought about it renders as blank instead of as noise.
        """
        return ""

    def details_schema(self) -> dict:
        """Describes the fields a client must collect, so the mobile request form
        can be driven by the API rather than hardcoded per category."""
        fields = []
        for name, field in self.details_serializer().get_fields().items():
            fields.append(
                {
                    "name": name,
                    "type": field.__class__.__name__.replace("Field", "").lower(),
                    "required": field.required,
                    "label": field.label or name.replace("_", " ").capitalize(),
                    "choices": list(getattr(field, "choices", {}) or {}) or None,
                }
            )
        return {"key": self.key, "fields": fields}
