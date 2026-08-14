from django.urls import path

from apps.payments.payment_views import (
    CustomerPaymentDetailView,
    CustomerPaymentListView,
    CustomerPaymentVerifyView,
)

urlpatterns = [
    path("", CustomerPaymentListView.as_view(), name="payments"),
    path("<uuid:pk>/", CustomerPaymentDetailView.as_view(), name="payment-detail"),
    path("<uuid:pk>/verify/", CustomerPaymentVerifyView.as_view(), name="payment-verify"),
]
