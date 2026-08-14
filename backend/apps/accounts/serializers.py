from typing import Any

from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.errors import AccountInactive, InvalidCredentials
from apps.accounts.identity import normalize_email, normalize_phone
from apps.accounts.models import User


class UserSerializer(serializers.ModelSerializer):
    """The shape of a user everywhere the API returns one."""

    full_name = serializers.CharField(read_only=True)
    is_email_verified = serializers.BooleanField(read_only=True)
    is_phone_verified = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "full_name",
            "is_email_verified",
            "is_phone_verified",
            "email_verified_at",
            "phone_verified_at",
            "created_at",
        ]
        read_only_fields = fields


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)


class AuthenticatedUserSerializer(serializers.Serializer):
    """Returned by register and login.

    Both hand back the user alongside the tokens so the app can render an
    authenticated screen without a second round trip, which matters on connections
    where every request is a chance to fail.
    """

    user = UserSerializer(read_only=True)
    tokens = TokenPairSerializer(read_only=True)


class RegistrationSerializer(serializers.Serializer):
    """What it takes to open an account with an email address and a password.

    A phone number is required here, and only here. `User.phone` stays nullable
    because a Google sign-in creates an account from an ID token that carries no
    number, so the model must be able to hold an account without one. Requiring it
    is a rule about this form, not about the shape of a user.

    Requiring the number is not the same as requiring it verified. Verification
    stays progressive and is still demanded only at the first action that needs
    it. What this buys is that every account created this way has a number on
    file, so booking is one code away rather than a form away, and support has a
    way to reach the person behind an account from the moment it exists.
    """

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    phone = serializers.CharField(max_length=20)

    def validate_email(self, value: str) -> str:
        email = normalize_email(value)
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate_phone(self, value: str) -> str:
        try:
            phone = normalize_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        if User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError("An account with this phone number already exists.")
        return phone

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Run password validation against an unsaved instance so the similarity
        # validator can compare against this user's own email and name rather than
        # nothing, which is the only way that check does anything useful.
        candidate = User(
            email=attrs.get("email", ""),
            phone=attrs.get("phone"),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        try:
            password_validation.validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    def create(self, validated_data: dict[str, Any]) -> User:
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            phone=validated_data.get("phone"),
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
        )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # authenticate() runs the password hasher even when no user matches, so a
        # wrong address and a wrong password take the same time. Checking existence
        # first would leak which addresses are registered through response timing.
        user = authenticate(
            request=self.context.get("request"),
            username=normalize_email(attrs["email"]),
            password=attrs["password"],
        )

        if user is None:
            # ModelBackend returns None for an inactive user too, so distinguish the
            # two here: someone whose account was disabled needs to be told that,
            # not left retyping a password that was correct all along.
            if User.objects.filter(email=normalize_email(attrs["email"]), is_active=False).exists():
                raise AccountInactive
            raise InvalidCredentials

        attrs["user"] = user
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)


class RefreshRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)


class PhoneUpdateSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)

    def validate_phone(self, value: str) -> str:
        try:
            phone = normalize_phone(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc

        user = self.context["request"].user
        if User.objects.filter(phone=phone).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("Another account already uses this phone number.")

        return phone


class VerificationStatusSerializer(serializers.Serializer):
    """What the app needs to render the verification state of an account."""

    phone = serializers.CharField(allow_null=True)
    is_phone_verified = serializers.BooleanField()
    phone_verified_at = serializers.DateTimeField(allow_null=True)


class VerificationChallengeSerializer(serializers.Serializer):
    """The safe half of a challenge.

    Deliberately excludes the code and its hash. The client needs the id to submit
    against and the timings to render a countdown, and nothing else.
    """

    challenge_id = serializers.UUIDField(source="id")
    destination = serializers.CharField()
    expires_at = serializers.DateTimeField()
    attempts_remaining = serializers.IntegerField()
    resend_available_in_seconds = serializers.IntegerField()


class PhoneVerificationConfirmSerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    code = serializers.CharField(min_length=4, max_length=10, trim_whitespace=True)
