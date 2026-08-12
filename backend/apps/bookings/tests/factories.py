"""Fixtures for the booking suite."""

import itertools

from django.utils import timezone

from apps.accounts.address import Address
from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.bookings.state import ActorType, BookingStatus
from apps.catalog.models import Service
from apps.catalog.tests.factories import make_service
from apps.providers.models import ProviderProfile, ProviderService

PASSWORD = "Lagos-Rider-2026"

VALID_CLEANING_DETAILS = {
    "property_type": "APARTMENT",
    "bedrooms": 3,
    "bathrooms": 2,
    "depth": "STANDARD",
    "has_supplies": False,
}


#: Emails are unique, so factories that may be called several times in one test
#: need distinct ones. A counter keeps them readable, unlike a UUID.
_sequence = itertools.count(1)


def unique_email(prefix: str) -> str:
    return f"{prefix}{next(_sequence)}@example.com"


def make_customer(email: str | None = None, *, phone_verified: bool = True) -> User:
    user = User.objects.create_user(email=email or unique_email("customer"), password=PASSWORD)
    if phone_verified:
        user.phone_verified_at = timezone.now()
        user.save(update_fields=["phone_verified_at"])
    return user


def make_address(user: User, **overrides) -> Address:
    defaults = {
        "user": user,
        "street_address": "14 Adeola Odeku Street",
        "landmark": "Opposite Eko Hotel gate",
        "area": "Victoria Island",
        "lga": "Eti-Osa",
        "state": "LAGOS",
        "directions_note": "Blue gate, second floor.",
    }
    return Address.objects.create(**{**defaults, **overrides})


def make_provider_offering(service: Service, email: str | None = None) -> ProviderProfile:
    provider = ProviderProfile.objects.create(
        user=User.objects.create_user(email=email or unique_email("provider"), password=PASSWORD),
        display_name="Ada Cleaning Services",
    )
    ProviderService.objects.create(provider=provider, service=service)
    return provider


def booking_setup(spec_key: str = "cleaning", slug: str = "standard-clean") -> dict:
    """The full cast needed for a booking: customer, address, service, provider."""
    service = make_service(slug=slug, spec_key=spec_key)
    return {
        "customer": make_customer(),
        "service": service,
        "provider": make_provider_offering(service),
        "address": None,
    }


def full_setup() -> dict:
    data = booking_setup()
    data["address"] = make_address(data["customer"])
    return data


def make_booking(*, status: str = BookingStatus.ASSIGNED, **overrides) -> Booking:
    """Builds a booking directly, bypassing the API and its policy check.

    Lifecycle tests need a booking in a given state without re-exercising creation.
    """
    data = full_setup()
    booking = Booking(
        customer=overrides.get("customer", data["customer"]),
        provider=overrides.get("provider", data["provider"]),
        service=overrides.get("service", data["service"]),
        spec_key=data["service"].spec_key,
        details=overrides.get("details", VALID_CLEANING_DETAILS),
        status=status,
    )
    booking.snapshot_address(overrides.get("address", data["address"]))
    booking.save()
    return booking


ACTORS = ActorType
