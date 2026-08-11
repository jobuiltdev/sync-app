from django.urls import path

from apps.accounts.views import LoginView, LogoutView, MeView, RefreshView, RegisterView

# Trailing slashes throughout, matching the rest of the API and Django's default
# APPEND_SLASH behaviour.
urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
]
