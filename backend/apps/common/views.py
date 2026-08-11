import logging

from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_DEGRADED = "degraded"

CACHE_PROBE_KEY = "health:probe"


class HealthChecksSerializer(serializers.Serializer):
    database = serializers.CharField()
    cache = serializers.CharField()


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField()
    checks = HealthChecksSerializer()


def check_database() -> str:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Health check failed to reach the database")
        return STATUS_ERROR
    return STATUS_OK


def check_cache() -> str:
    try:
        cache.set(CACHE_PROBE_KEY, "1", timeout=5)
        if cache.get(CACHE_PROBE_KEY) != "1":
            logger.error("Health check wrote to the cache but read back a different value")
            return STATUS_ERROR
    except Exception:
        logger.exception("Health check failed to reach the cache")
        return STATUS_ERROR
    return STATUS_OK


class HealthView(APIView):
    """Reports whether the service and its dependencies are usable.

    Failures are reported as a bare "error" per dependency. The underlying
    exception goes to the logs and never into the response, because this endpoint
    is unauthenticated and a driver error string readily names hosts and users.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = HealthSerializer

    @extend_schema(
        operation_id="health",
        summary="Service health",
        description=(
            "Returns 200 when the application and every dependency are healthy, "
            "and 503 when any dependency check fails."
        ),
        responses={
            status.HTTP_200_OK: HealthSerializer,
            status.HTTP_503_SERVICE_UNAVAILABLE: HealthSerializer,
        },
        auth=[],
    )
    def get(self, request: Request) -> Response:
        checks = {"database": check_database(), "cache": check_cache()}
        healthy = all(result == STATUS_OK for result in checks.values())

        return Response(
            {"status": STATUS_OK if healthy else STATUS_DEGRADED, "checks": checks},
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
