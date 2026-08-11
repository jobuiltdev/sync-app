from django.urls import path

from apps.providers.views import (
    ProviderProfileCreateView,
    ProviderProfileView,
    ProviderServiceAreaDetailView,
    ProviderServiceAreaListCreateView,
    ProviderServiceDetailView,
    ProviderServiceListCreateView,
)

urlpatterns = [
    path("profile/", ProviderProfileView.as_view(), name="profile"),
    path("profile/create/", ProviderProfileCreateView.as_view(), name="profile-create"),
    path("services/", ProviderServiceListCreateView.as_view(), name="services"),
    path("services/<uuid:pk>/", ProviderServiceDetailView.as_view(), name="service-detail"),
    path("areas/", ProviderServiceAreaListCreateView.as_view(), name="areas"),
    path("areas/<uuid:pk>/", ProviderServiceAreaDetailView.as_view(), name="area-detail"),
]
