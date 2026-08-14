"""Where a provider's money is meant to go.

The minimum a transfer provider will need later, and nothing beyond it. No card
number, no CVV, no bank password, no API secret, no vendor key: none of those are
required to pay a Nigerian provider, and none of them are stored anywhere in this
codebase.

The account number itself is not stored either. It arrives, it is used to show the
provider what they typed and to recognise a resubmission of the same account, and
what persists is a hash, the last four digits, and a slot for the token a transfer
provider will hand back. That is the same posture identity verification already
takes with NIN and BVN in `providers`, for the same reason: holding the value adds
real exposure under the NDPR and buys nothing the reference does not already give.
"""

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel


class DestinationStatus(models.TextChoices):
    """Whether anybody has confirmed this account exists.

    Submitting ten digits proves nothing. A provider who mistypes one would
    otherwise have money sent into a stranger's account with nothing having
    looked wrong, and the only check that catches it is asking the bank what name
    it holds against the number.
    """

    UNVERIFIED = "UNVERIFIED", "Not yet checked with the bank"
    VERIFIED = "VERIFIED", "Confirmed with the bank"
    FAILED = "FAILED", "The bank did not recognise it"


class PayoutDestination(BaseModel):
    """The bank account a provider is paid into.

    One per provider. Changing where you are paid is an edit to this row, not a
    second row, because a provider with two live destinations is a question about
    which one we mean at exactly the moment it matters most.
    """

    provider = models.OneToOneField(
        "providers.ProviderProfile",
        on_delete=models.CASCADE,
        related_name="payout_destination",
    )

    #: The NIBSS bank code. Not sensitive, and the value a transfer provider wants.
    bank_code = models.CharField(max_length=10)
    bank_name = models.CharField(max_length=120)
    #: The name the bank holds against the account. Shown back to the provider so
    #: they can see they typed the right account before any money moves.
    account_name = models.CharField(max_length=140)

    #: Enough to recognise the account, not enough to pay into it.
    account_number_last4 = models.CharField(max_length=4)
    #: Produced by the project's configured password hashers, so today Argon2. It
    #: exists to answer one question, "is this the same account you gave us
    #: before", and it cannot answer any other.
    account_number_hash = models.CharField(max_length=255)

    verification_status = models.CharField(
        max_length=12, choices=DestinationStatus.choices, default=DestinationStatus.UNVERIFIED
    )
    #: The name the bank holds against this account, as the bank gave it. Kept
    #: separate from `account_name`, which is what the provider claimed: showing
    #: both back is what lets somebody notice they have typed their sister's
    #: account number.
    resolved_account_name = models.CharField(max_length=140, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    #: The lookup provider's handle on the check, for support conversations.
    verification_reference = models.CharField(max_length=120, blank=True)

    #: Where a future transfer adapter records the recipient token it issues.
    #: Blank today. The reason this row can afford to forget the account number is
    #: that the adapter will be called at the moment the number is supplied, and
    #: from then on the token is what moves the money.
    provider_reference = models.CharField(max_length=120, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "payments_payout_destination"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(bank_code=""),
                name="payments_destination_bank_code_not_empty",
            ),
            models.CheckConstraint(
                condition=~models.Q(account_number_hash=""),
                name="payments_destination_account_hash_not_empty",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.bank_name} ****{self.account_number_last4}"

    def set_account_number(self, account_number: str) -> None:
        """Takes an account number and keeps only what may be kept.

        The plaintext exists on this object for the length of this call and is
        never assigned to a field, so nothing can persist it by accident.
        """
        digits = "".join(character for character in account_number if character.isdigit())
        self.account_number_last4 = digits[-4:]
        self.account_number_hash = make_password(digits)

    def matches(self, account_number: str) -> bool:
        digits = "".join(character for character in account_number if character.isdigit())
        return check_password(digits, self.account_number_hash)

    def mark_verified(self, *, account_name: str, reference: str = "") -> None:
        """Records that a bank confirmed this account."""
        self.verification_status = DestinationStatus.VERIFIED
        self.resolved_account_name = account_name[:140]
        self.verification_reference = reference[:120]
        self.verified_at = timezone.now()
        self.save(
            update_fields=[
                "verification_status",
                "resolved_account_name",
                "verification_reference",
                "verified_at",
                "updated_at",
            ]
        )

    def mark_unverified(self) -> None:
        """Throws away a previous verification.

        Called whenever the account or the bank changes. A verification is a
        statement about one number at one bank, so it says nothing at all about a
        different one, and carrying it over would be the exact mistake this check
        exists to prevent.
        """
        self.verification_status = DestinationStatus.UNVERIFIED
        self.resolved_account_name = ""
        self.verification_reference = ""
        self.verified_at = None

    @property
    def is_verified(self) -> bool:
        return self.verification_status == DestinationStatus.VERIFIED

    @property
    def is_usable(self) -> bool:
        """Whether a payout may be requested against this destination.

        Verification is part of this from M6A. Money leaving towards an account
        nobody has confirmed exists is the failure this gate is for.
        """
        return self.is_active and bool(self.account_number_hash) and self.is_verified
