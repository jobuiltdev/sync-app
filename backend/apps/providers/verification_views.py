"""The provider-facing verification API.

Four endpoints, all authenticated, all scoped to the caller's own profile. There
is no path parameter identifying a provider anywhere in this module, which is the
simplest way to make a broken-object-authorization bug impossible: there is no
identifier to tamper with.

**Nothing here writes a result, a review field or an approval.** Every write goes
through `services`, and the only service a provider can reach is
`run_identity_check`, which tops out at `UNDER_REVIEW`.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.providers.services import (
    NoVerificationAttempt,
    attempt_history,
    build_checklist,
    latest_attempt,
    resubmit,
    run_identity_check,
)
from apps.providers.verification_serializers import (
    ProviderVerificationSerializer,
    StartVerificationSerializer,
    VerificationChecklistSerializer,
)
from apps.providers.views import profile_for


class VerificationChecklistView(APIView):
    """Where this provider is up to, decided by the server.

    The app renders this rather than working it out. A client computing its own
    progress is a client that eventually disagrees with the server about whether
    somebody may start a paid check.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=VerificationChecklistSerializer)
    def get(self, request: Request) -> Response:
        profile = profile_for(request)
        checklist = build_checklist(profile)
        return Response(
            VerificationChecklistSerializer(
                checklist,
                context={"verification_status": profile.verification_status},
            ).data
        )


class VerificationStatusView(APIView):
    """The current attempt, if there is one."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ProviderVerificationSerializer)
    def get(self, request: Request) -> Response:
        profile = profile_for(request)
        attempt = latest_attempt(profile)
        if attempt is None:
            raise NoVerificationAttempt
        return Response(ProviderVerificationSerializer(attempt).data)


class VerificationHistoryView(ListAPIView):
    """Every attempt this provider has made, newest first.

    Nothing is hidden. A provider is entitled to see the rejections on their own
    record, and a support conversation goes better when both sides can see the
    same list.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ProviderVerificationSerializer
    pagination_class = None

    def get_queryset(self):
        return attempt_history(profile_for(self.request))


class StartVerificationView(APIView):
    """Begins an identity check, or retries a failed one.

    Returns the attempt as it stands after the check, so the app does not have to
    poll a second endpoint to learn what happened.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=StartVerificationSerializer,
        responses={status.HTTP_200_OK: ProviderVerificationSerializer},
    )
    def post(self, request: Request) -> Response:
        profile = profile_for(request)

        payload = StartVerificationSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        attempt = run_identity_check(
            profile,
            authorization_reference=payload.validated_data["authorization_reference"],
            consented=payload.validated_data["consent"],
        )
        return Response(ProviderVerificationSerializer(attempt).data)


class ResubmitVerificationView(APIView):
    """Opens a fresh attempt after a rejection.

    A new row. The rejected one keeps its reviewer, note and timestamps, which is
    the whole point of attempts being separate from the profile.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None, responses={status.HTTP_201_CREATED: ProviderVerificationSerializer}
    )
    def post(self, request: Request) -> Response:
        attempt = resubmit(profile_for(request))
        return Response(
            ProviderVerificationSerializer(attempt).data, status=status.HTTP_201_CREATED
        )
