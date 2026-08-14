from django.urls import path

from apps.payments.payment_views import ProviderBankListView, ProviderDestinationVerifyView
from apps.payments.views import (
    ProviderEarningsView,
    ProviderPayoutCancelView,
    ProviderPayoutDestinationView,
    ProviderPayoutDetailView,
    ProviderPayoutListView,
    ProviderPayoutRequestView,
    ProviderSettlementListView,
)

urlpatterns = [
    path("earnings/", ProviderEarningsView.as_view(), name="earnings"),
    path("earnings/settlements/", ProviderSettlementListView.as_view(), name="settlements"),
    path("payouts/", ProviderPayoutListView.as_view(), name="payouts"),
    # Before the detail route, so "request" is never read as an id.
    path("payouts/request/", ProviderPayoutRequestView.as_view(), name="payout-request"),
    path("payouts/<uuid:pk>/", ProviderPayoutDetailView.as_view(), name="payout-detail"),
    path("payouts/<uuid:pk>/cancel/", ProviderPayoutCancelView.as_view(), name="payout-cancel"),
    path(
        "payout-destination/",
        ProviderPayoutDestinationView.as_view(),
        name="payout-destination",
    ),
    path(
        "payout-destination/verify/",
        ProviderDestinationVerifyView.as_view(),
        name="payout-destination-verify",
    ),
    path("banks/", ProviderBankListView.as_view(), name="banks"),
]
