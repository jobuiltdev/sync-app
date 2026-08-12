from django.urls import path

from apps.bookings.offer_views import (
    ProviderOfferAcceptView,
    ProviderOfferDeclineView,
    ProviderOfferDetailView,
    ProviderOfferListView,
)

urlpatterns = [
    path("", ProviderOfferListView.as_view(), name="offers"),
    path("<uuid:pk>/", ProviderOfferDetailView.as_view(), name="offer-detail"),
    path("<uuid:pk>/accept/", ProviderOfferAcceptView.as_view(), name="offer-accept"),
    path("<uuid:pk>/decline/", ProviderOfferDeclineView.as_view(), name="offer-decline"),
]
