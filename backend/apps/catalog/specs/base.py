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

    #: How a field should read on a screen, keyed by field name.
    #:
    #: Copy lives here rather than in the app because the whole point of the spec
    #: system is that a vertical can change its wording without an app release.
    #: Recognised keys per field: `help_text`, `style`, `placeholder`, `hint`,
    #: `choice_labels`, `choice_help`.
    presentation: dict[str, dict] = {}

    def presentation_for(self, service=None) -> dict[str, dict]:
        """Presentation for one service, which may differ inside a vertical.

        Beauty is the reason this takes a service: hair, nails and facials share
        one spec, and "Braids, cornrows" is a useless example on the nails form.
        """
        return self.presentation

    def option_keys(self, details: dict) -> list[str]:
        """Which `ServiceOption` keys this request selects.

        The single place that maps an answer onto a priced add-on. Pricing reads
        it to charge, and the schema below reads it to quote, so the figure on the
        review screen and the figure charged cannot come apart.

        Returning a key no option row exists for is safe and deliberate: it costs
        nothing until operations configures a price for it.
        """
        return []

    def details_schema(self, service=None) -> dict:
        """Describes the fields a client must collect, so the mobile request form
        can be driven by the API rather than hardcoded per category."""
        presentation = self.presentation_for(service)
        deltas = _option_deltas(service)

        fields = []
        for name, field in self.details_serializer().get_fields().items():
            info = presentation.get(name, {})
            choices = list(getattr(field, "choices", {}) or {}) or None
            kind = field.__class__.__name__.replace("Field", "").lower()

            fields.append(
                {
                    "name": name,
                    "type": kind,
                    "required": field.required,
                    "label": field.label or name.replace("_", " ").capitalize(),
                    "choices": choices,
                    "help_text": info.get("help_text") or str(field.help_text or ""),
                    #: A hint to the client about how to render, never what to say.
                    "style": info.get("style", ""),
                    "placeholder": info.get("placeholder", ""),
                    "hint": info.get("hint", ""),
                    "choice_labels": info.get("choice_labels") or {},
                    "choice_help": info.get("choice_help") or {},
                    "price_deltas": self._price_deltas(name, kind, choices, deltas),
                }
            )

        return {"key": self.key, "fields": fields}

    def _price_deltas(
        self, name: str, kind: str, choices: list | None, deltas: dict[str, int]
    ) -> dict[str, int]:
        """What each possible answer adds, in kobo.

        Derived by asking `option_keys` what each candidate answer selects, so the
        client's running total is computed from the same mapping the server bills
        from. An answer that selects nothing, or selects an option nobody has
        priced, is simply absent.
        """
        if not deltas:
            return {}

        candidates: list = list(choices) if choices else ([True] if kind == "boolean" else [])

        result: dict[str, int] = {}
        for value in candidates:
            total = sum(deltas.get(key, 0) for key in self.option_keys({name: value}))
            if total:
                result[str(value).lower() if isinstance(value, bool) else str(value)] = total

        return result


def _option_deltas(service) -> dict[str, int]:
    """Active priced options for a service, as key to kobo.

    Returns nothing when there is no service, which is the case for the registry's
    own schema dumps and for tests that inspect a spec in isolation.
    """
    if service is None or service.pk is None:
        return {}

    return {
        option.key: option.price_delta_kobo for option in service.options.all() if option.is_active
    }
