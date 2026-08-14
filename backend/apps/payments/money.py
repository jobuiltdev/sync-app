"""Money, and the one arithmetic operation the financial domain performs.

Everything here is integer kobo. There is no float in this module, and none
anywhere else in the payments app: a float cannot hold a tenth exactly, and money
that is out by a fraction of a kobo per booking is money that is out by a real
amount by the end of a month.

The commission split is a pure function so it can be reasoned about and tested on
its own, without a database, a booking or a provider.
"""

from dataclasses import dataclass

from django.db import models


class Currency(models.TextChoices):
    """The currencies this marketplace settles in.

    One entry, and it is stored on every financial record rather than assumed.
    A row that does not say what unit it is in is a row nobody can safely read
    once a second currency exists, and adding the column later means backfilling
    history from memory.
    """

    NGN = "NGN", "Nigerian naira"


#: A rate is basis points, an integer hundredth of a percent, so 2000 is twenty
#: percent. Percentages invite a float; basis points keep the whole calculation in
#: integers and still express every rate anyone has asked for.
BASIS_POINTS = 10_000


@dataclass(frozen=True)
class Split:
    """How one booking's money divides. Every field is kobo."""

    gross_kobo: int
    commission_kobo: int
    provider_kobo: int
    rate_bps: int


def split_commission(gross_kobo: int, rate_bps: int) -> Split:
    """Divides a booking's total between the platform and the provider.

    Rounding is floor division, so a fraction of a kobo goes to the provider
    rather than to us. It is a rounding rule that has to be picked deliberately,
    and picking the one that never rounds in our own favour is the one we can
    defend to a provider reading their statement.

    The provider's share is derived by subtraction rather than by a second
    multiplication, which is what makes the invariant hold exactly:

        provider_kobo = gross_kobo - commission_kobo
    """
    if gross_kobo < 0:
        raise ValueError("A booking total cannot be negative.")
    if not 0 <= rate_bps <= BASIS_POINTS:
        raise ValueError("A commission rate must be between 0 and 10000 basis points.")

    commission_kobo = gross_kobo * rate_bps // BASIS_POINTS

    return Split(
        gross_kobo=gross_kobo,
        commission_kobo=commission_kobo,
        provider_kobo=gross_kobo - commission_kobo,
        rate_bps=rate_bps,
    )
