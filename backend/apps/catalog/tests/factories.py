"""Builders for domain fixtures used across the catalog and provider suites."""

from apps.catalog.models import BookingMode, PricingModel, Service, ServiceCategory, ServiceOption


def make_category(slug: str = "cleaning", **overrides) -> ServiceCategory:
    """Reuses an existing category with the same slug.

    Several tests build two services without caring which category they land in.
    Creating rather than reusing would collide on the unique slug and fail the test
    for a reason that has nothing to do with what it is asserting.
    """
    defaults = {"name": slug.replace("-", " ").title(), "sort_order": 0}
    category, _ = ServiceCategory.objects.get_or_create(
        slug=slug, defaults={**defaults, **overrides}
    )
    return category


def make_service(
    category: ServiceCategory | None = None,
    slug: str = "standard-clean",
    spec_key: str = "cleaning",
    **overrides,
) -> Service:
    # Reuses by slug for the same reason make_category does: several tests build the
    # same service more than once and care about something else entirely.
    defaults = {
        "category": category or make_category(),
        "name": slug.replace("-", " ").title(),
        "spec_key": spec_key,
        "booking_modes": BookingMode.SCHEDULED,
        "pricing_model": PricingModel.FIXED,
        "base_price_kobo": 1_500_000,
        **overrides,
    }
    service, _ = Service.objects.get_or_create(slug=slug, defaults=defaults)
    return service


def make_option(service: Service, key: str = "ironing", **overrides) -> ServiceOption:
    defaults = {"service": service, "key": key, "label": key.title(), "price_delta_kobo": 200_000}
    return ServiceOption.objects.create(**{**defaults, **overrides})
