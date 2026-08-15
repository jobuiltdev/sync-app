"""Fixtures for the notifications suite.

The booking factories verify a customer's phone and nothing else, because that is
all `CREATE_BOOKING` needs. Notifications care about something different: whether
a channel has been proven, which is what decides if a message may be sent at all.
So the helpers here are about verification state rather than about roles.
"""

from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.sms.locmem import LocMemSMSProvider
from apps.bookings.tests.factories import unique_email
from apps.notifications.models import Notification

PASSWORD = "Lagos-Rider-2026"


def make_reachable(prefix: str = "reachable") -> User:
    """Somebody who can be reached on both channels."""
    user = User.objects.create_user(email=unique_email(prefix), password=PASSWORD)
    user.phone = f"+2348030000{User.objects.count():04d}"
    user.phone_verified_at = timezone.now()
    user.email_verified_at = timezone.now()
    user.save()
    return user


def make_unreachable(prefix: str = "unreachable") -> User:
    """Somebody with contact details on file, none of them proven.

    The case the whole destination rule exists for: an unverified number may be
    somebody else's, and it is the same shape as a typo.
    """
    user = User.objects.create_user(email=unique_email(prefix), password=PASSWORD)
    user.phone = "+2348039999999"
    user.save()
    return user


def verify_channels(user: User, *, phone: bool = True, email: bool = True) -> User:
    user.phone_verified_at = timezone.now() if phone else None
    user.email_verified_at = timezone.now() if email else None
    user.save(update_fields=["phone_verified_at", "email_verified_at"])
    return user


def sms_bodies() -> list[str]:
    """Every SMS the fake provider has taken, as it would have gone out."""
    return [message.body for message in LocMemSMSProvider.messages]


def events_for(user: User) -> set[str]:
    return set(Notification.objects.filter(recipient=user).values_list("event_type", flat=True))
