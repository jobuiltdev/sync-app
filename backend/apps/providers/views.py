from django.db import IntegrityError
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import (
    CreateAPIView,
    ListCreateAPIView,
    RetrieveDestroyAPIView,
    RetrieveUpdateAPIView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.serializers import BaseSerializer

from apps.common.exceptions import APIError
from apps.common.permissions import authenticated_user
from apps.providers.models import ProviderProfile, ProviderService, ProviderServiceArea
from apps.providers.serializers import (
    ProviderProfileSerializer,
    ProviderServiceAreaSerializer,
    ProviderServiceSerializer,
)


class ProviderProfileExists(APIError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "PROVIDER_PROFILE_EXISTS"
    default_detail = "This account already has a provider profile."


class NotAProvider(APIError):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "PROVIDER_PROFILE_NOT_FOUND"
    default_detail = "This account does not have a provider profile yet."


class DuplicateProviderService(APIError):
    default_code = "SERVICE_ALREADY_OFFERED"
    default_detail = "You already offer this service."


class DuplicateServiceArea(APIError):
    default_code = "AREA_ALREADY_COVERED"
    default_detail = "You already cover this area."


def profile_for(request: Request) -> ProviderProfile:
    try:
        return authenticated_user(request).provider_profile
    except ProviderProfile.DoesNotExist as exc:
        raise NotAProvider from exc


class ProviderProfileCreateView(CreateAPIView):
    """Turns an existing account into a provider.

    Becoming a provider is not a separate signup. The account already exists; this
    adds the provider side of it, which is what lets one person be both.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ProviderProfileSerializer

    @extend_schema(
        operation_id="provider_profile_create",
        summary="Create your provider profile",
        responses={
            status.HTTP_201_CREATED: ProviderProfileSerializer,
            status.HTTP_409_CONFLICT: None,
        },
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer: BaseSerializer) -> None:
        try:
            serializer.save(user=self.request.user)
        except IntegrityError as exc:
            # The one-to-one is the authority. Checking first and then saving would
            # leave a window where two concurrent requests both pass the check.
            raise ProviderProfileExists from exc


class ProviderProfileView(RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProviderProfileSerializer
    # PATCH only. A full replace would require the client to resend every field to
    # change one, and any it forgot would be silently reset.
    http_method_names = ["get", "patch", "head", "options"]

    def get_object(self) -> ProviderProfile:
        return profile_for(self.request)

    @extend_schema(operation_id="provider_profile_read", summary="Your provider profile")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(operation_id="provider_profile_update", summary="Update your provider profile")
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)


class ProviderServiceListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProviderServiceSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[ProviderService]:
        return ProviderService.objects.filter(provider=profile_for(self.request)).select_related(
            "service"
        )

    @extend_schema(operation_id="provider_services_list", summary="Services you offer")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(operation_id="provider_services_add", summary="Offer a service")
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer: BaseSerializer) -> None:
        try:
            serializer.save(provider=profile_for(self.request))
        except IntegrityError as exc:
            raise DuplicateProviderService from exc


class ProviderServiceDetailView(RetrieveDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProviderServiceSerializer

    def get_queryset(self) -> QuerySet[ProviderService]:
        return ProviderService.objects.filter(provider=profile_for(self.request))

    @extend_schema(operation_id="provider_services_read", summary="One service you offer")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(operation_id="provider_services_remove", summary="Stop offering a service")
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)


class ProviderServiceAreaListCreateView(ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProviderServiceAreaSerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[ProviderServiceArea]:
        return ProviderServiceArea.objects.filter(provider=profile_for(self.request))

    @extend_schema(operation_id="provider_areas_list", summary="Areas you cover")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(operation_id="provider_areas_add", summary="Cover an area")
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    def perform_create(self, serializer: BaseSerializer) -> None:
        try:
            serializer.save(provider=profile_for(self.request))
        except IntegrityError as exc:
            raise DuplicateServiceArea from exc


class ProviderServiceAreaDetailView(RetrieveDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProviderServiceAreaSerializer

    def get_queryset(self) -> QuerySet[ProviderServiceArea]:
        return ProviderServiceArea.objects.filter(provider=profile_for(self.request))

    @extend_schema(operation_id="provider_areas_read", summary="One area you cover")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(operation_id="provider_areas_remove", summary="Stop covering an area")
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)
