"""What a completed booking earned, and whose it is.

A settlement is written once, when a booking reaches COMPLETED, and is never
updated afterwards. That is the whole point of it: it is the record of what was
agreed at the moment the work finished, and it has to survive every later change
to a catalog price, a provider's override and the commission rate.
"""

from django.db import models

from apps.common.models import BaseModel
from apps.payments.money import Currency


class SettlementStatus(models.TextChoices):
    """A settlement's state.

    One value, deliberately. A settlement is created only for work that is already
    finished and confirmed, so there is no earlier state for it to sit in, and it
    is immutable, so there is no later one it can move to. The field exists rather
    than being inferred because a correction path is coming: a dispute resolved in
    the customer's favour writes a compensating record, which needs a state of its
    own, and adding it later must not mean teaching old rows what state they were
    always in.
    """

    PAYABLE = "PAYABLE", "Owed to the provider"


class BookingSettlement(BaseModel):
    """The money owed to a provider for one completed booking.

    Everything monetary on this row is a copy, not a reference. `gross_amount_kobo`
    comes from the booking's own agreed total rather than from the Service, and
    `commission_rate_bps` records the rate that was actually applied rather than
    leaving a reader to look up today's. Recomputing a historical settlement from
    current configuration is the mistake this model exists to make impossible.
    """

    booking = models.OneToOneField(
        "bookings.Booking",
        # A settlement is the financial record of a completed job. Losing it
        # because a booking row was tidied up would leave a payout with nothing
        # behind it, so nothing cascades here.
        on_delete=models.PROTECT,
        related_name="settlement",
    )
    provider = models.ForeignKey(
        "providers.ProviderProfile",
        on_delete=models.PROTECT,
        related_name="settlements",
    )

    gross_amount_kobo = models.BigIntegerField(
        help_text="The booking total the customer agreed to, copied at completion."
    )
    commission_amount_kobo = models.BigIntegerField(help_text="The platform's share, in kobo.")
    provider_amount_kobo = models.BigIntegerField(help_text="The provider's share, in kobo.")
    #: The rate as it was applied, so a statement can be explained years later
    #: without anyone having to reconstruct what the configuration used to say.
    commission_rate_bps = models.PositiveIntegerField()

    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.NGN)
    status = models.CharField(
        max_length=12, choices=SettlementStatus.choices, default=SettlementStatus.PAYABLE
    )

    class Meta:
        db_table = "payments_booking_settlement"
        ordering = ["-created_at"]
        constraints = [
            # The invariant, enforced by the database rather than trusted to the
            # code that writes the row. Application arithmetic can be wrong; a
            # check constraint cannot be bypassed by a shell session, a data
            # migration or a future caller nobody has written yet.
            models.CheckConstraint(
                condition=models.Q(
                    provider_amount_kobo=models.F("gross_amount_kobo")
                    - models.F("commission_amount_kobo")
                ),
                name="payments_settlement_amounts_balance",
            ),
            models.CheckConstraint(
                condition=models.Q(gross_amount_kobo__gte=0),
                name="payments_settlement_gross_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(commission_amount_kobo__gte=0),
                name="payments_settlement_commission_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(provider_amount_kobo__gte=0),
                name="payments_settlement_provider_amount_not_negative",
            ),
            # Commission is a share of the booking, never more than the whole of
            # it. Without this a misconfigured rate would silently produce a
            # negative provider amount, which the balance check above would then
            # have to catch as a symptom rather than a cause.
            models.CheckConstraint(
                condition=models.Q(commission_amount_kobo__lte=models.F("gross_amount_kobo")),
                name="payments_settlement_commission_within_gross",
            ),
            models.CheckConstraint(
                condition=models.Q(commission_rate_bps__lte=10_000),
                name="payments_settlement_rate_within_range",
            ),
        ]
        indexes = [
            # The earnings query: this provider's settlements, newest first.
            models.Index(fields=["provider", "-created_at"]),
            models.Index(fields=["provider", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.booking_id}: {self.provider_amount_kobo} kobo to {self.provider_id}"
