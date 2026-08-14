"""The provider's financial endpoints.

Every queryset is scoped to the requesting provider, which is what makes another
provider's payout a 404 rather than a 403: the row is not absent from their view
because we refused, it is absent because it was never theirs. That is the same
pattern addresses, bookings and offers already follow, and it is what stops the
API confirming that a given payout id exists.

There is no endpoint here that accepts a status. Moving a payout to PROCESSING or
PAID is not something this module offers by any route, to anybody.
"""

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import authenticated_user
from apps.payments import services
from apps.payments.destinations import PayoutDestination
from apps.payments.payouts import PayoutRequest
from apps.payments.serializers import (
    EarningsSerializer,
    PayoutDestinationSerializer,
    PayoutRequestSerializer,
    PayoutSerializer,
    SettlementSerializer,
)
from apps.payments.settlements import BookingSettlement
from apps.providers.views import profile_for

#: Header the mobile client already sends on anything that moves money. The
#: server half of it lands here rather than in a new mechanism.
IDEMPOTENCY_HEADER = "HTTP_IDEMPOTENCY_KEY"


def idempotency_key(request: Request) -> str:
    return str(request.META.get(IDEMPOTENCY_HEADER, ""))[:100]


class ProviderEarningsView(APIView):
    """What this provider has earned and what they may withdraw.

    Computed on every request from the settlements and payouts themselves. There
    is no balance column to read, so there is nothing here that can be stale.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = EarningsSerializer

    @extend_schema(
        operation_id="provider_earnings_read",
        summary="Your earnings",
        description=(
            "Derived from your completed bookings and your payouts. Money in a "
            "requested or processing payout is counted as reserved, not available."
        ),
        responses={status.HTTP_200_OK: EarningsSerializer},
    )
    def get(self, request: Request) -> Response:
        earnings = services.available_balance(profile_for(request))
        return Response(EarningsSerializer(earnings).data, status=status.HTTP_200_OK)


class ProviderSettlementListView(ListAPIView):
    """The completed jobs behind the balance."""

    permission_classes = [IsAuthenticated]
    serializer_class = SettlementSerializer

    def get_queryset(self) -> QuerySet[BookingSettlement]:
        return BookingSettlement.objects.filter(provider=profile_for(self.request)).select_related(
            "booking", "booking__service"
        )

    @extend_schema(
        operation_id="provider_settlements_list",
        summary="What each completed job earned you",
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProviderPayoutListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PayoutSerializer

    def get_queryset(self) -> QuerySet[PayoutRequest]:
        return services.provider_payouts(profile_for(self.request))

    @extend_schema(operation_id="provider_payouts_list", summary="Your payouts")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProviderPayoutDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PayoutSerializer

    def get_queryset(self) -> QuerySet[PayoutRequest]:
        return services.provider_payouts(profile_for(self.request))

    @extend_schema(operation_id="provider_payouts_read", summary="One of your payouts")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProviderPayoutRequestView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PayoutRequestSerializer

    @extend_schema(
        operation_id="provider_payouts_request",
        summary="Ask to be paid",
        description=(
            "Requires a verified phone and email, a payout destination on file, "
            "and enough available balance. Send an Idempotency-Key header: a retry "
            "carrying the same key returns the payout the first attempt created "
            "rather than making a second one."
        ),
        request=PayoutRequestSerializer,
        responses={
            status.HTTP_201_CREATED: PayoutSerializer,
            status.HTTP_403_FORBIDDEN: None,
            status.HTTP_409_CONFLICT: None,
            status.HTTP_422_UNPROCESSABLE_ENTITY: None,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PayoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payout = services.request_payout(
            provider=profile_for(request),
            actor=authenticated_user(request),
            amount_kobo=serializer.validated_data["amount_kobo"],
            idempotency_key=idempotency_key(request),
        )

        return Response(PayoutSerializer(payout).data, status=status.HTTP_201_CREATED)


class ProviderPayoutCancelView(APIView):
    """The one lifecycle move a provider may make on their own payout.

    Cancelling releases money back to them and takes nothing from anyone, which is
    what makes it theirs to do. Every other transition belongs to the trusted path.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PayoutSerializer

    @extend_schema(
        operation_id="provider_payouts_cancel",
        summary="Cancel a payout you asked for",
        description="Only while it is still REQUESTED. Once it is being processed it is "
        "out of your hands.",
        request=None,
        responses={
            status.HTTP_200_OK: PayoutSerializer,
            status.HTTP_404_NOT_FOUND: None,
            status.HTTP_409_CONFLICT: None,
        },
    )
    def post(self, request: Request, pk: str) -> Response:
        payout = services.cancel_payout(pk, profile_for(request))
        return Response(PayoutSerializer(payout).data, status=status.HTTP_200_OK)


class ProviderPayoutDestinationView(APIView):
    """Where this provider is paid.

    A PUT rather than a PATCH. The account number cannot be read back, so a
    partial update would have no way to leave it alone, and an account changed one
    field at a time is an account that is briefly half of two different ones.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PayoutDestinationSerializer

    @extend_schema(
        operation_id="provider_payout_destination_read",
        summary="Your payout destination",
        responses={
            status.HTTP_200_OK: PayoutDestinationSerializer,
            status.HTTP_404_NOT_FOUND: None,
        },
    )
    def get(self, request: Request) -> Response:
        destination = PayoutDestination.objects.filter(provider=profile_for(request)).first()
        if destination is None:
            from apps.payments.errors import InvalidPayoutDestination

            raise InvalidPayoutDestination

        return Response(PayoutDestinationSerializer(destination).data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="provider_payout_destination_set",
        summary="Set where you are paid",
        description=(
            "The account number is hashed on the way in. Only its last four digits "
            "come back, and nothing stores the number itself."
        ),
        request=PayoutDestinationSerializer,
        responses={status.HTTP_200_OK: PayoutDestinationSerializer},
    )
    def put(self, request: Request) -> Response:
        serializer = PayoutDestinationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        destination = services.set_destination(
            profile_for(request),
            bank_code=data["bank_code"],
            bank_name=data["bank_name"],
            account_name=data["account_name"],
            account_number=data["account_number"],
        )

        return Response(PayoutDestinationSerializer(destination).data, status=status.HTTP_200_OK)
