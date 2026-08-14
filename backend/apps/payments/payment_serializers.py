"""How payments and payout destinations look on the wire.

Nothing here exposes a provider credential. The authorization URL is not one: it
is a single-use checkout link scoped to one transaction, which is the only thing
the app needs and the only thing it gets.
"""

from rest_framework import serializers

from apps.payments.destinations import PayoutDestination
from apps.payments.intents import PaymentIntent


class PaymentIntentSerializer(serializers.ModelSerializer):
    """A payment as its owner sees it.

    `status` is what the app branches on and is only ever written by the server
    against what the provider reported. There is no writable field on this
    serializer at all, so no request can assert an outcome.
    """

    booking_reference = serializers.CharField(source="booking.reference", read_only=True)
    is_payable = serializers.BooleanField(read_only=True)

    class Meta:
        model = PaymentIntent
        fields = [
            "id",
            "reference",
            "booking",
            "booking_reference",
            "amount_kobo",
            "currency",
            "status",
            "method",
            "authorization_url",
            "is_payable",
            "paid_at",
            "failed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PaymentInitializeSerializer(serializers.Serializer):
    """The body of a payment initialization.

    Empty of anything financial. The amount comes from the booking's own
    snapshotted total, the currency from the account's, and the booking from the
    URL, so a client has nothing to supply and nothing to influence.
    """


class PayoutDestinationVerifySerializer(serializers.Serializer):
    """The account number, supplied again so the bank can be asked about it.

    Not read from the stored row, because the row does not hold it: only a hash
    and the last four digits persist. Sending it again is also what proves the
    number being resolved is the one on file.
    """

    account_number = serializers.CharField(write_only=True, min_length=10, max_length=20)

    @staticmethod
    def validate_account_number(value: str) -> str:
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) < 10:
            raise serializers.ValidationError("Enter the full account number.")
        return digits


class BankSerializer(serializers.Serializer):
    """One institution a provider can be paid at."""

    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)


class VerifiedPayoutDestinationSerializer(serializers.ModelSerializer):
    """The destination, including what the bank said about it.

    `resolved_account_name` is the bank's answer and `account_name` is what the
    provider typed. Both are returned so the provider can see they match, which
    is the whole point of resolving an account before sending money to it.
    """

    is_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = PayoutDestination
        fields = [
            "id",
            "bank_code",
            "bank_name",
            "account_name",
            "account_number_last4",
            "verification_status",
            "resolved_account_name",
            "verified_at",
            "is_verified",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
