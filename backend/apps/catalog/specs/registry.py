"""Lookup from a Service's spec_key to the spec implementing it."""

from apps.catalog.specs.base import ServiceSpec

_REGISTRY: dict[str, ServiceSpec] = {}


class SpecNotRegistered(KeyError):
    """Raised when a Service names a spec that no module provides.

    Surfaces as a validation error rather than a 500, because the usual cause is a
    Service row created or edited with a typo in spec_key.
    """


def register(spec: ServiceSpec) -> ServiceSpec:
    if spec.key in _REGISTRY:
        raise ValueError(f"A spec is already registered for {spec.key!r}.")
    _REGISTRY[spec.key] = spec
    return spec


def get(key: str) -> ServiceSpec:
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        raise SpecNotRegistered(key) from exc


def is_registered(key: str) -> bool:
    return key in _REGISTRY


def registered_keys() -> list[str]:
    return sorted(_REGISTRY)
