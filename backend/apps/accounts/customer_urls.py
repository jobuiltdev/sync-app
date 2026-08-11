from django.urls import path

from apps.accounts.address_api import AddressDetailView, AddressListCreateView

urlpatterns = [
    path("addresses/", AddressListCreateView.as_view(), name="addresses"),
    path("addresses/<uuid:pk>/", AddressDetailView.as_view(), name="address-detail"),
]
