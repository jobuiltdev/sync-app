from django.urls import path

from apps.providers.verification_views import (
    ResubmitVerificationView,
    StartVerificationView,
    VerificationChecklistView,
    VerificationHistoryView,
    VerificationStatusView,
)
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
    # Verification. No path carries a provider identifier: every one of these is
    # scoped to the authenticated caller's own profile, so there is nothing to
    # tamper with.
    path(
        "verification/checklist/",
        VerificationChecklistView.as_view(),
        name="verification-checklist",
    ),
    path("verification/", VerificationStatusView.as_view(), name="verification-status"),
    path("verification/history/", VerificationHistoryView.as_view(), name="verification-history"),
    path("verification/start/", StartVerificationView.as_view(), name="verification-start"),
    path(
        "verification/resubmit/",
        ResubmitVerificationView.as_view(),
        name="verification-resubmit",
    ),
]
