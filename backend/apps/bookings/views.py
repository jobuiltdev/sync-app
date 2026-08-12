from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings import services
from apps.bookings.models import Booking
from apps.bookings.serializers import (
    BookingCreateSerializer,
    BookingDetailSerializer,
    BookingSummarySerializer,
    BookingTransitionSerializer,
)
from apps.bookings.state import ActorType, BookingStatus
from apps.common.permissions import authenticated_user
from apps.providers.views import profile_for


def customer_bookings(request: Request) -> QuerySet[Booking]:
    """Scoped so another customer's booking is a 404, matching the M2 pattern."""
    return Booking.objects.filter(customer=authenticated_user(request)).select_related(
        "service", "provider"
    )


def provider_bookings(request: Request) -> QuerySet[Booking]:
    return Booking.objects.filter(provider=profile_for(request)).select_related(
        "service", "provider", "customer"
    )


class CustomerBookingListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_queryset(self) -> QuerySet[Booking]:
        return customer_bookings(self.request)

    def get_serializer_class(self):
        return (
            BookingCreateSerializer if self.request.method == "POST" else BookingSummarySerializer
        )

    @extend_schema(
        operation_id="customer_bookings_list",
        summary="Your bookings",
        responses={status.HTTP_200_OK: BookingSummarySerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        operation_id="customer_bookings_create",
        summary="Book a service",
        description=(
            "Requires a verified phone number. Without one the request is refused "
            "with PHONE_VERIFICATION_REQUIRED and nothing is created."
        ),
        request=BookingCreateSerializer,
        responses={
            status.HTTP_201_CREATED: BookingDetailSerializer,
            status.HTTP_403_FORBIDDEN: None,
        },
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        serializer = BookingCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        booking = services.create_booking(
            customer=authenticated_user(request),
            service=data["service_slug"],
            provider=data["provider_id"],
            address=data["address_id"],
            details=data["details"],
            scheduled_for=data.get("scheduled_for"),
        )

        return Response(
            BookingDetailSerializer(booking).data,
            status=status.HTTP_201_CREATED,
        )


class CustomerBookingDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BookingDetailSerializer

    def get_queryset(self) -> QuerySet[Booking]:
        return customer_bookings(self.request).prefetch_related("events")

    @extend_schema(operation_id="customer_bookings_read", summary="One of your bookings")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BookingActionView(APIView):
    """Base for the guarded lifecycle actions.

    Each subclass fixes one target status. The client never names a status, so
    there is no path by which an arbitrary one can be requested.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BookingTransitionSerializer
    target_status: str
    actor_type: str

    def get_booking(self, request: Request, pk: str) -> Booking:
        raise NotImplementedError

    def actor_id(self, request: Request):
        return authenticated_user(request).id

    def post(self, request: Request, pk: str) -> Response:
        serializer = BookingTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        booking = self.get_booking(request, pk)
        services.transition(
            booking,
            self.target_status,
            actor_type=self.actor_type,
            actor_id=self.actor_id(request),
            reason=serializer.validated_data.get("reason", ""),
        )

        return Response(BookingDetailSerializer(booking).data, status=status.HTTP_200_OK)


class CustomerBookingActionView(BookingActionView):
    actor_type = ActorType.CUSTOMER

    def get_booking(self, request: Request, pk: str) -> Booking:
        from django.shortcuts import get_object_or_404

        return get_object_or_404(customer_bookings(request), pk=pk)


class ProviderBookingActionView(BookingActionView):
    actor_type = ActorType.PROVIDER

    def get_booking(self, request: Request, pk: str) -> Booking:
        from django.shortcuts import get_object_or_404

        return get_object_or_404(provider_bookings(request), pk=pk)


class CustomerCancelBookingView(CustomerBookingActionView):
    target_status = BookingStatus.CANCELLED

    @extend_schema(
        operation_id="customer_bookings_cancel",
        summary="Cancel a booking",
        request=BookingTransitionSerializer,
        responses={status.HTTP_200_OK: BookingDetailSerializer},
    )
    def post(self, request, pk):
        return super().post(request, pk)


class CustomerConfirmCompletionView(CustomerBookingActionView):
    target_status = BookingStatus.COMPLETED

    @extend_schema(
        operation_id="customer_bookings_confirm",
        summary="Confirm the work is done",
        description="Only the customer closes a booking, and only once the provider has "
        "marked the work finished.",
        request=BookingTransitionSerializer,
        responses={status.HTTP_200_OK: BookingDetailSerializer},
    )
    def post(self, request, pk):
        return super().post(request, pk)


class ProviderBookingListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BookingSummarySerializer

    def get_queryset(self) -> QuerySet[Booking]:
        return provider_bookings(self.request)

    @extend_schema(operation_id="provider_bookings_list", summary="Jobs assigned to you")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProviderBookingDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BookingDetailSerializer

    def get_queryset(self) -> QuerySet[Booking]:
        return provider_bookings(self.request).prefetch_related("events")

    @extend_schema(operation_id="provider_bookings_read", summary="One of your jobs")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ProviderEnRouteView(ProviderBookingActionView):
    target_status = BookingStatus.EN_ROUTE

    @extend_schema(
        operation_id="provider_bookings_en_route",
        summary="Mark yourself on the way",
        request=BookingTransitionSerializer,
        responses={status.HTTP_200_OK: BookingDetailSerializer},
    )
    def post(self, request, pk):
        return super().post(request, pk)


class ProviderStartView(ProviderBookingActionView):
    target_status = BookingStatus.IN_PROGRESS

    @extend_schema(
        operation_id="provider_bookings_start",
        summary="Start the job",
        request=BookingTransitionSerializer,
        responses={status.HTTP_200_OK: BookingDetailSerializer},
    )
    def post(self, request, pk):
        return super().post(request, pk)


class ProviderFinishView(ProviderBookingActionView):
    target_status = BookingStatus.AWAITING_CONFIRMATION

    @extend_schema(
        operation_id="provider_bookings_finish",
        summary="Mark the work finished",
        description="Hands the booking to the customer to confirm. The provider does not "
        "close it themselves.",
        request=BookingTransitionSerializer,
        responses={status.HTTP_200_OK: BookingDetailSerializer},
    )
    def post(self, request, pk):
        return super().post(request, pk)


class ProviderCancelBookingView(ProviderBookingActionView):
    target_status = BookingStatus.CANCELLED

    @extend_schema(
        operation_id="provider_bookings_cancel",
        summary="Cancel a job",
        request=BookingTransitionSerializer,
        responses={status.HTTP_200_OK: BookingDetailSerializer},
    )
    def post(self, request, pk):
        return super().post(request, pk)
