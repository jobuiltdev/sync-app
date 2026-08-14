from django.urls import path

from apps.common.views import HealthView, LivenessView, ReadinessView

urlpatterns = [
    # The original endpoint, contract unchanged.
    path("health/", HealthView.as_view(), name="health"),
    # Liveness and readiness are separate because they answer different
    # questions and an orchestrator does different things with the answers.
    path("health/live/", LivenessView.as_view(), name="health-live"),
    path("health/ready/", ReadinessView.as_view(), name="health-ready"),
]
