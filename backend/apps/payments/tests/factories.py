"""Fixtures for the payments suite.

Everything here builds on the booking factories rather than writing financial
rows directly. A settlement that was inserted by hand proves nothing about the
path a real one takes, and the path is most of what these tests are checking.
"""

from apps.bookings.models import Booking
from apps.bookings.services import transition
from apps.bookings.state import ActorType, BookingStatus
from apps.bookings.tests.factories import (
    VALID_CLEANING_DETAILS,
    make_address,
    make_customer,
    make_provider_offering,
)
from apps.catalog.tests.factories import make_service
from apps.payments import payment_services, services
from apps.payments.banks.fake import FakeBankResolver
from apps.payments.destinations import PayoutDestination
from apps.payments.gateways.base import PaymentState
from apps.payments.gateways.fake import FakeGateway
from apps.payments.intents import PaymentIntent
from apps.payments.settlements import BookingSettlement
from apps.providers.models import ProviderProfile

#: Twenty thousand naira. A round figure that divides cleanly at the default
#: twenty percent, so a test reading it can do the arithmetic in their head.
DEFAULT_PRICE_KOBO = 2_000_000


def make_priced_service(price_kobo: int = DEFAULT_PRICE_KOBO, **overrides):
    return make_service(base_price_kobo=price_kobo, **overrides)


def pay_booking(booking: Booking, *, state: str = PaymentState.SUCCESSFUL) -> PaymentIntent:
    """Takes payment for a booking the way production does.

    Through initialization and then verification against the provider, rather
    than by writing a SUCCESSFUL row: the point of the payment path is that only
    the provider's answer moves an intent, and a fixture that skipped it would
    leave that untested everywhere it is relied on.
    """
    intent = payment_services.initialize_payment(booking=booking, customer=booking.customer)
    FakeGateway.arrange(
        intent.reference,
        state=state,
        amount_kobo=intent.amount_kobo,
        currency=intent.currency,
    )
    outcome = payment_services.verify_payment(intent.pk, booking.customer)
    return outcome.intent


def complete_booking(booking: Booking) -> Booking:
    """Walks a booking from ASSIGNED to COMPLETED the way production does.

    Through the real transitions, so the settlement is created by the same hook a
    customer confirming on their phone would fire. Writing COMPLETED onto the row
    directly would skip the very thing under test.
    """
    provider_id = booking.provider_id

    transition(
        booking,
        BookingStatus.IN_PROGRESS,
        actor_type=ActorType.PROVIDER,
        actor_id=provider_id,
    )
    transition(
        booking,
        BookingStatus.AWAITING_CONFIRMATION,
        actor_type=ActorType.PROVIDER,
        actor_id=provider_id,
    )
    transition(
        booking,
        BookingStatus.COMPLETED,
        actor_type=ActorType.CUSTOMER,
        actor_id=booking.customer_id,
    )
    return booking


def earning_setup(price_kobo: int = DEFAULT_PRICE_KOBO, *, slug: str = "standard-clean") -> dict:
    """A provider, a customer, and a bookable service priced at `price_kobo`."""
    service = make_priced_service(price_kobo, slug=slug)
    customer = make_customer()

    return {
        "service": service,
        "customer": customer,
        "address": make_address(customer),
        "provider": make_provider_offering(service),
    }


def earn(setup: dict, price_kobo: int | None = None) -> BookingSettlement:
    """Puts one completed booking's worth of earnings behind a provider.

    Creates the booking through the API's own service function, has the setup's
    provider accept the offer, and walks it to COMPLETED.
    """
    from apps.bookings.services import create_booking
    from apps.bookings.tests.factories import accept_first_offer

    if price_kobo is not None:
        setup["service"].base_price_kobo = price_kobo
        setup["service"].save(update_fields=["base_price_kobo"])

    booking = create_booking(
        customer=setup["customer"],
        service=setup["service"],
        address=setup["address"],
        details=VALID_CLEANING_DETAILS,
    )
    accept_first_offer(booking, setup["provider"])
    booking.refresh_from_db()
    # Paid before completion. Either order settles, and this is the one a
    # customer paying up front produces.
    pay_booking(booking)
    complete_booking(booking)

    return BookingSettlement.objects.get(booking=booking)


def make_destination(
    provider: ProviderProfile, *, verified: bool = True, **overrides
) -> PayoutDestination:
    """A payout destination, confirmed with the bank unless a test says not to.

    Verified by default because that is what a usable destination is from M6A,
    and a fixture that produced an unusable one would make every payout test
    fail for a reason none of them are about.
    """
    defaults = {
        "bank_code": "058",
        "bank_name": "Guaranty Trust Bank",
        "account_name": "Adaeze Okonkwo",
        "account_number": "0123456789",
    }
    values = {**defaults, **overrides}
    destination = services.set_destination(provider, **values)

    if verified:
        FakeBankResolver.arrange(
            account_number=values["account_number"],
            bank_code=values["bank_code"],
            account_name=values["account_name"],
        )
        destination = services.verify_destination(provider, values["account_number"])

    return destination
