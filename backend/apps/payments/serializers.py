"""How financial records look on the wire.

Money is an integer number of kobo in a field whose name ends in `_kobo`, exactly
as it is in the catalog and on a booking, and the currency travels beside it on
every record that stores one. Nothing here formats a naira string: the app owns
presentation through one formatter, and a server that also formatted would give
it a second opinion to disagree with.
"""

from rest_framework import serializers

from apps.payments.destinations import PayoutDestination
from apps.payments.payouts import PayoutRequest, targets_from
from apps.payments.settlements import BookingSettlement


class SettlementSerializer(serializers.ModelSerializer):
    """One completed booking's earnings, from the provider's side."""

    booking_reference = serializers.CharField(source="booking.reference", read_only=True)
    service_name = serializers.CharField(source="booking.service.name", read_only=True)
    completed_at = serializers.DateTimeField(source="booking.completed_at", read_only=True)

    class Meta:
        model = BookingSettlement
        fields = [
            "id",
            "booking_reference",
            "service_name",
            "gross_amount_kobo",
            "commission_amount_kobo",
            "provider_amount_kobo",
            "commission_rate_bps",
            "currency",
            "status",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields


class EarningsSerializer(serializers.Serializer):
    """The derived position, not a stored row.

    Every figure is recomputed from settlements and payouts on each request, which
    is why there is no model behind this serializer to drift away from them.
    """

    currency = serializers.CharField(read_only=True)
    settlement_count = serializers.IntegerField(read_only=True)
    gross_earned_kobo = serializers.IntegerField(read_only=True)
    commission_kobo = serializers.IntegerField(read_only=True)
    net_earned_kobo = serializers.IntegerField(read_only=True)
    reserved_kobo = serializers.IntegerField(read_only=True)
    paid_out_kobo = serializers.IntegerField(read_only=True)
    available_kobo = serializers.IntegerField(read_only=True)


class PayoutSerializer(serializers.ModelSerializer):
    """A payout as its owner sees it.

    `is_cancellable` and `allowed_transitions` are computed server-side and sent
    down rather than being worked out in the app. The lifecycle rules live in one
    place, and a client reimplementing them is a client that eventually disagrees
    with the server about which button to show.
    """

    is_cancellable = serializers.BooleanField(read_only=True)
    allowed_transitions = serializers.SerializerMethodField()

    class Meta:
        model = PayoutRequest
        fields = [
            "id",
            "amount_kobo",
            "currency",
            "status",
            "requested_at",
            "processed_at",
            "failure_reason",
            "is_cancellable",
            "allowed_transitions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @staticmethod
    def get_allowed_transitions(payout: PayoutRequest) -> list[str]:
        """What could happen to this payout next, whoever is entitled to do it.

        Advisory. Whether this caller may cause one is decided by the action
        endpoints, which check the actor as well as the edge.
        """
        return sorted(targets_from(payout.status))


class PayoutRequestSerializer(serializers.Serializer):
    """The body of a payout request.

    An amount and nothing else. The provider is the authenticated caller, the
    currency is the one their earnings are in, and the status is fixed by the
    endpoint, so none of the three can be supplied by a client.
    """

    amount_kobo = serializers.IntegerField(min_value=1)


class PayoutDestinationSerializer(serializers.ModelSerializer):
    """The bank account, minus the part that must not be kept.

    `account_number` is write-only and is never a field on the model. It is hashed
    and reduced to its last four digits on the way in, so a response can say which
    account this is without being able to say what it is.
    """

    account_number = serializers.CharField(write_only=True, min_length=10, max_length=20)

    class Meta:
        model = PayoutDestination
        fields = [
            "id",
            "bank_code",
            "bank_name",
            "account_name",
            "account_number",
            "account_number_last4",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "account_number_last4", "is_active", "created_at", "updated_at"]

    @staticmethod
    def validate_account_number(value: str) -> str:
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) < 10:
            raise serializers.ValidationError("Enter the full account number.")
        return digits
