from django.db import transaction
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.generics import (
    GenericAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.serializers import BaseSerializer

from apps.accounts.address import Address
from apps.common.permissions import IsOwner, authenticated_user


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "label",
            "street_address",
            "landmark",
            "area",
            "lga",
            "state",
            "latitude",
            "longitude",
            "directions_note",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs: dict) -> dict:
        # Coordinates are meaningless one at a time, and the database refuses the
        # pair anyway. Catching it here turns a 500 into a field error.
        latitude = attrs.get("latitude", getattr(self.instance, "latitude", None))
        longitude = attrs.get("longitude", getattr(self.instance, "longitude", None))
        if (latitude is None) != (longitude is None):
            raise serializers.ValidationError(
                {"latitude": "Latitude and longitude must be provided together."}
            )
        return attrs


class OwnedAddressView(GenericAPIView):
    """Scopes every query to the requesting user.

    Another user's address is therefore a 404, not a 403. Returning 403 would
    confirm the id exists, which is a small leak but a free one to avoid.
    """

    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self) -> QuerySet[Address]:
        return Address.objects.filter(user=authenticated_user(self.request))


def clear_other_defaults(user, keep: Address | None = None) -> None:
    """Demotes any other default, so the partial unique index cannot be violated."""
    others = Address.objects.filter(user=user, is_default=True)
    if keep is not None:
        others = others.exclude(pk=keep.pk)
    others.update(is_default=False)


class AddressListCreateView(OwnedAddressView, ListCreateAPIView):
    @extend_schema(operation_id="addresses_list", summary="Your saved addresses")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(operation_id="addresses_create", summary="Save an address")
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

    @transaction.atomic
    def perform_create(self, serializer: BaseSerializer) -> None:
        user = authenticated_user(self.request)
        # The first address a customer saves is their default, because being asked
        # to nominate one when there is only one is pure friction.
        is_first = not Address.objects.filter(user=user).exists()
        is_default = serializer.validated_data.get("is_default", False) or is_first

        if is_default:
            clear_other_defaults(user)

        serializer.save(user=user, is_default=is_default)


class AddressDetailView(OwnedAddressView, RetrieveUpdateDestroyAPIView):
    # PATCH only, for the same reason as the provider profile: a full replace makes
    # every omitted field a silent reset.
    http_method_names = ["get", "patch", "delete", "head", "options"]

    @extend_schema(operation_id="addresses_read", summary="One saved address")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(operation_id="addresses_update", summary="Update a saved address")
    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    @extend_schema(operation_id="addresses_delete", summary="Delete a saved address")
    def delete(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)

    @transaction.atomic
    def perform_update(self, serializer: BaseSerializer) -> None:
        # Demote the incumbent before promoting this one. Saving first would leave
        # two defaults in flight and trip the partial unique index.
        if serializer.validated_data.get("is_default"):
            clear_other_defaults(authenticated_user(self.request), keep=serializer.instance)

        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance: Address) -> None:
        was_default = instance.is_default
        instance.delete()

        # Leaving a customer with addresses but no default would silently break the
        # "use my usual place" path in the booking flow.
        if was_default:
            replacement = Address.objects.filter(user=authenticated_user(self.request)).first()
            if replacement:
                replacement.is_default = True
                replacement.save(update_fields=["is_default", "updated_at"])
