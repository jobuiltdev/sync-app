"""Routes mounted under /api/v1/.

Domain apps add their own include() here as they land, so this module stays the
single place that describes the shape of version 1 of the API.
"""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

app_name = "v1"

urlpatterns = [
    path("", include("apps.common.urls")),
    path("auth/", include("apps.accounts.urls")),
    path("catalog/", include("apps.catalog.urls")),
    path("customer/", include("apps.accounts.customer_urls")),
    path("customer/bookings/", include("apps.bookings.customer_urls")),
    path("provider/", include("apps.providers.urls")),
    path("provider/bookings/", include("apps.bookings.provider_urls")),
    path("provider/offers/", include("apps.bookings.offer_urls")),
    path("provider/", include("apps.payments.provider_urls")),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="v1:schema"), name="docs"),
]
