from django.urls import path

from apps.bookings.views import (
    ProviderBookingDetailView,
    ProviderBookingListView,
    ProviderCancelBookingView,
    ProviderEnRouteView,
    ProviderFinishView,
    ProviderStartView,
)

urlpatterns = [
    path("", ProviderBookingListView.as_view(), name="jobs"),
    path("<uuid:pk>/", ProviderBookingDetailView.as_view(), name="job-detail"),
    path("<uuid:pk>/en-route/", ProviderEnRouteView.as_view(), name="job-en-route"),
    path("<uuid:pk>/start/", ProviderStartView.as_view(), name="job-start"),
    path("<uuid:pk>/finish/", ProviderFinishView.as_view(), name="job-finish"),
    path("<uuid:pk>/cancel/", ProviderCancelBookingView.as_view(), name="job-cancel"),
]
