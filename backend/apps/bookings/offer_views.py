from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings import dispatch
from apps.bookings.offer_serializers import (
    OfferDeclineSerializer,
    OfferDetailSerializer,
    OfferSummarySerializer,
)
from apps.bookings.offers import Offer, OfferStatus
from apps.bookings.serializers import BookingDetailSerializer
from apps.common.permissions import authenticated_user
from apps.providers.views import profile_for


def provider_offers(request: Request) -> QuerySet[Offer]:
    """Scoped to the requesting provider, so another provider's offer is a 404.

    A 403 would confirm the id exists and belongs to somebody, which is exactly
    the information a competitor should not be able to probe for.
    """
    return Offer.objects.filter(provider=profile_for(request)).select_related(
        "booking", "booking__service"
    )


class ProviderOfferListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OfferSummarySerializer

    def get_queryset(self) -> QuerySet[Offer]:
        queryset = provider_offers(self.request)

        # Default to the inbox. Everything else is history and is asked for
        # explicitly, so a provider opening the app sees only what needs an answer.
        if self.request.query_params.get("status") == "all":
            return queryset

        return queryset.filter(status=OfferStatus.PENDING)

    @extend_schema(
        operation_id="provider_offers_list",
        summary="Jobs offered to you",
        description=(
            "Pending offers by default. Pass status=all for the full history, "
            "including declined and superseded ones."
        ),
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProviderOfferDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OfferDetailSerializer

    def get_queryset(self) -> QuerySet[Offer]:
        return provider_offers(self.request)

    @extend_schema(operation_id="provider_offers_read", summary="One job offered to you")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProviderOfferAcceptView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OfferDetailSerializer

    @extend_schema(
        operation_id="provider_offers_accept",
        summary="Accept a job",
        description=(
            "Requires a verified phone and email. Exactly one provider can win a "
            "booking: the rest are told the job is no longer available."
        ),
        request=None,
        responses={
            status.HTTP_200_OK: BookingDetailSerializer,
            status.HTTP_403_FORBIDDEN: None,
            status.HTTP_409_CONFLICT: None,
            status.HTTP_410_GONE: None,
        },
    )
    def post(self, request: Request, pk: str) -> Response:
        booking = dispatch.accept_offer(pk, profile_for(request), authenticated_user(request))

        return Response(BookingDetailSerializer(booking).data, status=status.HTTP_200_OK)


class ProviderOfferDeclineView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OfferDeclineSerializer

    @extend_schema(
        operation_id="provider_offers_decline",
        summary="Decline a job",
        description="Touches only your own offer. Other providers keep theirs.",
        request=OfferDeclineSerializer,
        responses={
            status.HTTP_200_OK: OfferDetailSerializer,
            status.HTTP_409_CONFLICT: None,
        },
    )
    def post(self, request: Request, pk: str) -> Response:
        serializer = OfferDeclineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        offer = dispatch.decline_offer(
            pk,
            profile_for(request),
            authenticated_user(request),
            reason=serializer.validated_data.get("reason", ""),
        )

        return Response(OfferDetailSerializer(offer).data, status=status.HTTP_200_OK)
