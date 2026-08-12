from django.urls import path

from apps.accounts.views import (
    EmailVerificationConfirmView,
    EmailVerificationRequestView,
    LoginView,
    LogoutView,
    MeView,
    PhoneUpdateView,
    PhoneVerificationConfirmView,
    PhoneVerificationRequestView,
    RefreshView,
    RegisterView,
)

# Trailing slashes throughout, matching the rest of the API and Django's default
# APPEND_SLASH behaviour.
urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("phone/", PhoneUpdateView.as_view(), name="phone"),
    path(
        "email/verification/request/",
        EmailVerificationRequestView.as_view(),
        name="email-verification-request",
    ),
    path(
        "email/verification/confirm/",
        EmailVerificationConfirmView.as_view(),
        name="email-verification-confirm",
    ),
    path(
        "phone/verification/request/",
        PhoneVerificationRequestView.as_view(),
        name="phone-verification-request",
    ),
    path(
        "phone/verification/confirm/",
        PhoneVerificationConfirmView.as_view(),
        name="phone-verification-confirm",
    ),
]
