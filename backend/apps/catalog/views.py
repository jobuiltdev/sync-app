from django.db.models import Prefetch, QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from apps.catalog.models import Service, ServiceCategory
from apps.catalog.serializers import (
    ServiceCategorySerializer,
    ServiceDetailSerializer,
    ServiceSummarySerializer,
)


class CategoryListView(ListAPIView):
    """The catalog, open to everyone.

    Browsing is unauthenticated on purpose. Someone deciding whether Sync is worth
    installing an account for should be able to see what it offers and what it
    costs first.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = ServiceCategorySerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet[ServiceCategory]:
        return (
            ServiceCategory.objects.filter(is_active=True)
            .prefetch_related(Prefetch("services", queryset=Service.objects.filter(is_active=True)))
            .order_by("sort_order", "name")
        )

    @extend_schema(
        operation_id="catalog_categories",
        summary="Browse categories and their services",
        auth=[],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ServiceListView(ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = ServiceSummarySerializer

    def get_queryset(self) -> QuerySet[Service]:
        queryset = Service.objects.filter(is_active=True).select_related("category")

        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category__slug=category)

        return queryset.order_by("sort_order", "name")

    @extend_schema(
        operation_id="catalog_services",
        summary="List services, optionally within one category",
        auth=[],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class ServiceDetailView(RetrieveAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = ServiceDetailSerializer
    lookup_field = "slug"

    def get_queryset(self) -> QuerySet[Service]:
        return (
            Service.objects.filter(is_active=True)
            .select_related("category")
            .prefetch_related(Prefetch("options"))
        )

    @extend_schema(
        operation_id="catalog_service",
        summary="One service, with its options and request field schema",
        auth=[],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)
