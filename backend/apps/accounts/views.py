from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import verification
from apps.accounts.errors import InvalidToken
from apps.accounts.models import User
from apps.accounts.serializers import (
    AuthenticatedUserSerializer,
    LoginSerializer,
    LogoutSerializer,
    PhoneUpdateSerializer,
    PhoneVerificationConfirmSerializer,
    RefreshRequestSerializer,
    RegistrationSerializer,
    TokenPairSerializer,
    UserSerializer,
    VerificationChallengeSerializer,
)
from apps.common.permissions import authenticated_user


def issue_tokens(user: User) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def authenticated_payload(user: User) -> dict[str, Any]:
    return {"user": UserSerializer(user).data, "tokens": issue_tokens(user)}


class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = RegistrationSerializer

    @extend_schema(
        operation_id="auth_register",
        summary="Create an account",
        description=(
            "Creates an account and returns it with a token pair, so the client does "
            "not need a second call to sign in. Verification of the email and phone "
            "is separate and is not required to hold a session."
        ),
        request=RegistrationSerializer,
        responses={status.HTTP_201_CREATED: AuthenticatedUserSerializer},
        auth=[],
    )
    def post(self, request: Request) -> Response:
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(authenticated_payload(user), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    @extend_schema(
        operation_id="auth_login",
        summary="Sign in",
        request=LoginSerializer,
        responses={status.HTTP_200_OK: AuthenticatedUserSerializer},
        auth=[],
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user: User = serializer.validated_data["user"]
        return Response(authenticated_payload(user), status=status.HTTP_200_OK)


def user_for_token(token: RefreshToken) -> User:
    """Resolves the account a refresh token belongs to, or rejects the token.

    SimpleJWT validates the signature and expiry but never rechecks the user, so
    without this a deactivated account could keep minting access tokens for the
    remaining lifetime of a refresh token it already holds.
    """
    user_id = token.payload.get(jwt_settings.USER_ID_CLAIM)
    try:
        return User.objects.get(**{jwt_settings.USER_ID_FIELD: user_id}, is_active=True)
    except (User.DoesNotExist, ValidationError, ValueError) as exc:
        raise InvalidToken from exc


class RefreshView(APIView):
    """Exchanges a refresh token for a new pair.

    Not SimpleJWT's own view, because that one returns its own error body and would
    be the single endpoint whose failures do not match the API's error envelope.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = RefreshRequestSerializer

    @extend_schema(
        operation_id="auth_refresh",
        summary="Refresh the token pair",
        description=(
            "Rotation is on, so the submitted refresh token is blacklisted and a new "
            "pair is returned. A refresh token is therefore usable exactly once."
        ),
        request=RefreshRequestSerializer,
        responses={status.HTTP_200_OK: TokenPairSerializer},
        auth=[],
    )
    def post(self, request: Request) -> Response:
        serializer = RefreshRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            spent = RefreshToken(serializer.validated_data["refresh"])
        except TokenError as exc:
            raise InvalidToken from exc

        user = user_for_token(spent)

        # Blacklist first. If issuing the replacement somehow fails, the safe
        # outcome is a token that no longer works, not one that works twice.
        spent.blacklist()

        rotated = RefreshToken.for_user(user)
        return Response(
            {"access": str(rotated.access_token), "refresh": str(rotated)},
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """Blacklists a refresh token.

    Unauthenticated on purpose. Signing out must work even when the access token has
    already expired, and requiring a valid one would mean a user who left the app
    open overnight cannot log out without first refreshing. Blacklisting a token you
    already hold grants nothing.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = LogoutSerializer

    @extend_schema(
        operation_id="auth_logout",
        summary="Sign out",
        request=LogoutSerializer,
        responses={status.HTTP_204_NO_CONTENT: None},
        auth=[],
    )
    def post(self, request: Request) -> Response:
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError as exc:
            raise InvalidToken from exc

        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    @extend_schema(
        operation_id="auth_me",
        summary="The signed-in user",
        responses={status.HTTP_200_OK: UserSerializer},
    )
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data, status=status.HTTP_200_OK)


class EmailVerificationRequestThrottle(ScopedRateThrottle):
    scope = "email_verification_request"


class EmailVerificationConfirmThrottle(ScopedRateThrottle):
    scope = "email_verification_confirm"


class PhoneVerificationRequestThrottle(ScopedRateThrottle):
    scope = "phone_verification_request"


class PhoneVerificationConfirmThrottle(ScopedRateThrottle):
    scope = "phone_verification_confirm"


def _challenge_payload(challenge, limits: dict | None = None) -> dict[str, Any]:
    cooldown = (limits or settings.PHONE_VERIFICATION)["RESEND_COOLDOWN_SECONDS"]
    elapsed = (timezone.now() - challenge.last_sent_at).total_seconds()

    return {
        "challenge_id": challenge.id,
        "destination": challenge.destination,
        "expires_at": challenge.expires_at,
        "attempts_remaining": challenge.attempts_remaining,
        "resend_available_in_seconds": max(int(cooldown - elapsed), 0),
    }


class PhoneUpdateView(APIView):
    """Sets or changes the account's phone number.

    Changing it clears any existing verification, so a number that was never
    proven cannot inherit the previous one's status.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PhoneUpdateSerializer
    http_method_names = ["put", "head", "options"]

    @extend_schema(
        operation_id="auth_phone_update",
        summary="Set or change your phone number",
        request=PhoneUpdateSerializer,
        responses={status.HTTP_200_OK: UserSerializer},
    )
    def put(self, request: Request) -> Response:
        serializer = PhoneUpdateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user = verification.set_phone(
            authenticated_user(request), serializer.validated_data["phone"]
        )

        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class PhoneVerificationRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PhoneVerificationRequestThrottle]
    serializer_class = VerificationChallengeSerializer

    @extend_schema(
        operation_id="auth_phone_verification_request",
        summary="Send a verification code by SMS",
        description=(
            "Issues a one-time code and sends it to the account's phone number. The "
            "code is never returned by the API. Repeated requests are refused during "
            "the resend cooldown."
        ),
        request=None,
        responses={
            status.HTTP_201_CREATED: VerificationChallengeSerializer,
            status.HTTP_409_CONFLICT: None,
            status.HTTP_429_TOO_MANY_REQUESTS: None,
        },
    )
    def post(self, request: Request) -> Response:
        result = verification.request_phone_verification(
            authenticated_user(request), request_ip=request.META.get("REMOTE_ADDR")
        )

        return Response(_challenge_payload(result.challenge), status=status.HTTP_201_CREATED)


class PhoneVerificationConfirmView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [PhoneVerificationConfirmThrottle]
    serializer_class = PhoneVerificationConfirmSerializer

    @extend_schema(
        operation_id="auth_phone_verification_confirm",
        summary="Submit a verification code",
        description=(
            "Consumes the challenge and marks the phone verified. A challenge is "
            "single use: a second submission of the same code is refused."
        ),
        request=PhoneVerificationConfirmSerializer,
        responses={
            status.HTTP_200_OK: UserSerializer,
            status.HTTP_400_BAD_REQUEST: None,
            status.HTTP_410_GONE: None,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PhoneVerificationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = verification.confirm_phone_verification(
            authenticated_user(request),
            serializer.validated_data["challenge_id"],
            serializer.validated_data["code"],
        )

        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)


class EmailVerificationRequestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EmailVerificationRequestThrottle]
    serializer_class = VerificationChallengeSerializer

    @extend_schema(
        operation_id="auth_email_verification_request",
        summary="Send a verification code by email",
        description=(
            "Issues a one-time code and emails it to the account's address. The code "
            "is never returned by the API."
        ),
        request=None,
        responses={
            status.HTTP_201_CREATED: VerificationChallengeSerializer,
            status.HTTP_409_CONFLICT: None,
            status.HTTP_429_TOO_MANY_REQUESTS: None,
        },
    )
    def post(self, request: Request) -> Response:
        result = verification.request_email_verification(
            authenticated_user(request), request_ip=request.META.get("REMOTE_ADDR")
        )

        return Response(
            _challenge_payload(result.challenge, verification.EMAIL.config()),
            status=status.HTTP_201_CREATED,
        )


class EmailVerificationConfirmView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [EmailVerificationConfirmThrottle]
    serializer_class = PhoneVerificationConfirmSerializer

    @extend_schema(
        operation_id="auth_email_verification_confirm",
        summary="Submit an emailed verification code",
        request=PhoneVerificationConfirmSerializer,
        responses={
            status.HTTP_200_OK: UserSerializer,
            status.HTTP_400_BAD_REQUEST: None,
            status.HTTP_410_GONE: None,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PhoneVerificationConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = verification.confirm_email_verification(
            authenticated_user(request),
            serializer.validated_data["challenge_id"],
            serializer.validated_data["code"],
        )

        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)
