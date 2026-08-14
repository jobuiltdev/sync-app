from django.urls import path

from apps.bookings.views import (
    CustomerBookingDetailView,
    CustomerBookingListCreateView,
    CustomerCancelBookingView,
    CustomerConfirmCompletionView,
)
from apps.payments.payment_views import CustomerPaymentInitializeView

urlpatterns = [
    path("", CustomerBookingListCreateView.as_view(), name="bookings"),
    path("<uuid:pk>/", CustomerBookingDetailView.as_view(), name="booking-detail"),
    path("<uuid:pk>/cancel/", CustomerCancelBookingView.as_view(), name="booking-cancel"),
    path("<uuid:pk>/confirm/", CustomerConfirmCompletionView.as_view(), name="booking-confirm"),
    path("<uuid:pk>/pay/", CustomerPaymentInitializeView.as_view(), name="booking-pay"),
]
