from apps.catalog.specs.base import ServiceSpec
from apps.catalog.specs.registry import (
    SpecNotRegistered,
    get,
    is_registered,
    register,
    registered_keys,
)

__all__ = [
    "ServiceSpec",
    "SpecNotRegistered",
    "get",
    "is_registered",
    "load_specs",
    "register",
    "registered_keys",
]


def load_specs() -> None:
    """Registers the built-in verticals. Called once from the app's ready()."""
    from apps.catalog.specs.verticals import ALL_SPECS

    for spec in ALL_SPECS:
        if not is_registered(spec.key):
            register(spec)
