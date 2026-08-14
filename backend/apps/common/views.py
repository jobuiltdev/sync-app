"""Health, in the two senses an orchestrator needs them.

**Liveness** answers "is this process alive". It touches nothing else, because a
liveness probe that checks the database restarts a perfectly good web process
every time PostgreSQL hiccups, turning a brief database problem into an outage.

**Readiness** answers "can this process serve traffic correctly". It checks the
things a request genuinely cannot proceed without: the database, the cache, and
whether the configuration is coherent. A failing readiness probe takes one
instance out of a load balancer, which is the correct response to an instance
that cannot serve.

**No third-party API is checked.** Paystack being slow must not take this
marketplace off the internet: browsing, booking, offers and job progress all work
without it, and payment failures are already handled as payment failures.

Nothing here reveals a connection string, a driver message, a hostname or a
credential. The endpoints are unauthenticated, so every failure is reported as a
bare word and the detail goes to the logs.
"""

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


class LivenessSerializer(serializers.Serializer):
    status = serializers.CharField()


class ReadinessChecksSerializer(serializers.Serializer):
    database = serializers.CharField()
    cache = serializers.CharField()
    configuration = serializers.CharField()


class ReadinessSerializer(serializers.Serializer):
    status = serializers.CharField()
    checks = ReadinessChecksSerializer()


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


def check_configuration() -> str:
    """Whether this process is configured coherently for what it is.

    Runs the same production checks that refuse to let it start, so an instance
    whose configuration drifted after boot, through a settings reload or a
    rebuilt secret, reports itself unready rather than serving with a fake
    payment gateway.

    Outside production there is nothing to check and this is always ok, which
    keeps the endpoint useful locally rather than permanently red.
    """
    from django.core.checks import Error, run_checks

    try:
        messages = run_checks(tags=["sync.production"])
    except Exception:
        logger.exception("Readiness check could not evaluate configuration")
        return STATUS_ERROR

    failures = [message for message in messages if isinstance(message, Error)]
    if failures:
        # The ids only. The messages name settings and would tell an
        # unauthenticated caller which provider this deployment uses.
        logger.error(
            "Readiness check found configuration errors",
            extra={"check_ids": [message.id for message in failures]},
        )
        return STATUS_ERROR

    return STATUS_OK


class HealthView(APIView):
    """Reports whether the service and its dependencies are usable.

    The original endpoint, unchanged in contract. Everything deployed against it,
    including the README's device connectivity step, keeps working exactly as it
    did; readiness is a new endpoint rather than a new shape for this one.
    """

    authentication_classes: list = []
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


class LivenessView(APIView):
    """Is this process running.

    Touches nothing. A liveness probe exists to decide whether to restart the
    process, and restarting a healthy web process because a database is briefly
    unreachable turns a small problem into a large one.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    serializer_class = LivenessSerializer

    @extend_schema(
        operation_id="health_live",
        summary="Liveness",
        description=(
            "Returns 200 whenever the process can answer. Checks no dependency, so "
            "an orchestrator does not restart a healthy process because something "
            "downstream is briefly unavailable."
        ),
        responses={status.HTTP_200_OK: LivenessSerializer},
        auth=[],
    )
    def get(self, request: Request) -> Response:
        return Response({"status": STATUS_OK}, status=status.HTTP_200_OK)


class ReadinessView(APIView):
    """Can this process serve traffic correctly.

    Checks what a request cannot proceed without, and deliberately nothing else.
    A failure here should remove one instance from a load balancer, not restart
    it: an instance that cannot reach PostgreSQL will not be fixed by restarting.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    serializer_class = ReadinessSerializer

    @extend_schema(
        operation_id="health_ready",
        summary="Readiness",
        description=(
            "Returns 200 when this instance can serve requests, and 503 when it "
            "cannot: the database or cache is unreachable, or the configuration is "
            "not valid for production. No third-party API is checked, so a payment "
            "provider being slow does not take the marketplace offline."
        ),
        responses={
            status.HTTP_200_OK: ReadinessSerializer,
            status.HTTP_503_SERVICE_UNAVAILABLE: ReadinessSerializer,
        },
        auth=[],
    )
    def get(self, request: Request) -> Response:
        checks = {
            "database": check_database(),
            "cache": check_cache(),
            "configuration": check_configuration(),
        }
        ready = all(result == STATUS_OK for result in checks.values())

        return Response(
            {"status": STATUS_OK if ready else STATUS_DEGRADED, "checks": checks},
            status=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
