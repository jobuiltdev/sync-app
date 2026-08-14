from django.urls import path

from apps.payments.payment_views import PaymentWebhookView

# One route per provider rather than one generic endpoint. Each provider signs
# differently, and a shared entry point would have to guess which scheme applies
# before it had authenticated anything.
urlpatterns = [
    path("paystack/", PaymentWebhookView.as_view(), name="paystack-webhook"),
]
