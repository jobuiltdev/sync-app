"""Phone verification.

The only route by which `User.phone_verified_at` is ever set. There is no endpoint,
serializer or admin field that writes it directly, because a customer being able to
declare their own phone verified would make the M3 booking gate decorative.
"""

import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.challenges import VerificationChallenge
from apps.accounts.errors import (
    InvalidVerificationCode,
    PhoneAlreadyVerified,
    PhoneNotSet,
    VerificationChallengeNotFound,
    VerificationCooldown,
    VerificationExhausted,
    VerificationExpired,
)
from apps.accounts.sms.base import SMSDeliveryError, get_sms_provider

if TYPE_CHECKING:
    from apps.accounts.models import User


def config() -> dict:
    """All timing and limit values, in one place.

    Read per call rather than at import so override_settings works in tests and so
    an environment can tune them without a code change.
    """
    return settings.PHONE_VERIFICATION


def generate_code(length: int) -> str:
    """A cryptographically secure numeric code.

    `secrets` rather than `random`: the latter is a Mersenne Twister seeded from
    system state, and observing a handful of its outputs is enough to predict the
    rest. Built digit by digit so a leading zero survives, which slicing an integer
    would quietly drop and shrink the keyspace.
    """
    return "".join(secrets.choice("0123456789") for _ in range(length))


@dataclass(frozen=True)
class VerificationRequest:
    """What the caller may know about a challenge. Never includes the code."""

    challenge: VerificationChallenge
    already_verified: bool = False


def _active_challenges(user: User):
    return VerificationChallenge.objects.filter(
        user=user,
        channel=VerificationChallenge.Channel.PHONE,
        consumed_at__isnull=True,
        superseded_at__isnull=True,
    )


def supersede_phone_challenges(user: User) -> int:
    """Retires every live phone challenge for a user.

    Called when a new one is issued and when the phone number changes. Only one
    code is ever live, so a code overheard earlier cannot be used later.
    """
    return _active_challenges(user).update(superseded_at=timezone.now(), updated_at=timezone.now())


@transaction.atomic
def request_phone_verification(user: User, *, request_ip: str | None = None) -> VerificationRequest:
    """Issues a code and sends it.

    Nothing is persisted if the provider refuses the message: a challenge left
    behind after a failed send would tell the customer to enter a code that was
    never delivered, and would burn their cooldown for nothing.
    """
    if not user.phone:
        raise PhoneNotSet

    if user.phone_verified_at is not None:
        # Idempotent rather than an error. Asking to verify something already
        # verified is a stale client, not a problem, and sending another message
        # would cost money and confuse the customer.
        raise PhoneAlreadyVerified

    settings_ = config()
    now = timezone.now()

    # Cooldown is per destination, so changing your number lets you request a code
    # for the new one straight away while still preventing one number being spammed.
    recent = (
        VerificationChallenge.objects.filter(
            user=user,
            channel=VerificationChallenge.Channel.PHONE,
            destination=user.phone,
        )
        .order_by("-last_sent_at")
        .first()
    )

    if recent is not None:
        cooldown = timedelta(seconds=settings_["RESEND_COOLDOWN_SECONDS"])
        if now - recent.last_sent_at < cooldown:
            retry_after = int((recent.last_sent_at + cooldown - now).total_seconds()) + 1
            raise VerificationCooldown(retry_after=retry_after)

    # The window is per account rather than per destination, so rotating numbers
    # is not a way around the limit.
    window_start = now - timedelta(seconds=settings_["SEND_WINDOW_SECONDS"])
    sends_in_window = VerificationChallenge.objects.filter(
        user=user,
        channel=VerificationChallenge.Channel.PHONE,
        last_sent_at__gte=window_start,
    ).count()

    if sends_in_window >= settings_["MAX_SENDS_PER_WINDOW"]:
        raise VerificationCooldown(retry_after=settings_["SEND_WINDOW_SECONDS"])

    supersede_phone_challenges(user)

    code = generate_code(settings_["CODE_LENGTH"])
    challenge = VerificationChallenge.objects.create(
        user=user,
        channel=VerificationChallenge.Channel.PHONE,
        destination=user.phone,
        # Hashed with the project's configured password hashers, so the stored
        # value is useless on its own.
        code_hash=make_password(code),
        expires_at=now + timedelta(seconds=settings_["TTL_SECONDS"]),
        max_attempts=settings_["MAX_ATTEMPTS"],
        last_sent_at=now,
        request_ip=request_ip,
    )

    try:
        get_sms_provider().send_verification_code(user.phone, code)
    except SMSDeliveryError:
        # Rolls the challenge back with the transaction.
        raise

    return VerificationRequest(challenge=challenge)


def confirm_phone_verification(user: User, challenge_id, code: str) -> User:
    """Checks a code and, if it is right, marks the phone verified.

    The failure is raised after the transaction commits, never inside it. A wrong
    guess must increment the attempt counter durably, and raising from inside the
    atomic block would roll that increment back and hand an attacker unlimited
    tries at no cost.
    """
    if not user.phone:
        raise PhoneNotSet

    error: Exception | None = None

    with transaction.atomic():
        try:
            challenge = (
                VerificationChallenge.objects.select_for_update()
                .filter(
                    pk=challenge_id,
                    # Scoped to the user, so another account's challenge id is
                    # simply not found rather than producing an authorization
                    # error that would confirm it exists.
                    user=user,
                    channel=VerificationChallenge.Channel.PHONE,
                )
                .get()
            )
        except VerificationChallenge.DoesNotExist, DjangoValidationError, ValueError, TypeError:
            # Nothing was written, so raising here is safe.
            raise VerificationChallengeNotFound from None

        # The challenge is bound to the number it was sent to. If the account's
        # phone moved on, this code proves nothing about the number now claimed.
        unusable = (
            challenge.is_consumed or challenge.is_superseded or challenge.destination != user.phone
        )
        if unusable:
            raise VerificationChallengeNotFound
        if challenge.is_expired:
            raise VerificationExpired
        if challenge.is_exhausted:
            raise VerificationExhausted

        if check_password(code, challenge.code_hash):
            now = timezone.now()
            challenge.consumed_at = now
            challenge.attempt_count += 1
            challenge.save(update_fields=["consumed_at", "attempt_count", "updated_at"])

            user.phone_verified_at = now
            user.save(update_fields=["phone_verified_at", "updated_at"])
        else:
            challenge.attempt_count += 1
            challenge.save(update_fields=["attempt_count", "updated_at"])

            error = (
                VerificationExhausted()
                if challenge.is_exhausted
                else InvalidVerificationCode(attempts_remaining=challenge.attempts_remaining)
            )

    if error is not None:
        raise error

    return user


@transaction.atomic
def set_phone(user: User, phone: str) -> User:
    """Sets or changes the account's phone number.

    Normalisation is M1's, not a second implementation. Changing the number clears
    any existing verification and retires live challenges, so the new number
    starts unproven no matter how the old one was verified.
    """
    from apps.accounts.identity import normalize_phone

    normalized = normalize_phone(phone)

    if normalized == user.phone:
        return user

    user.phone = normalized
    # The User model clears phone_verified_at itself when the number changes, so
    # the invariant holds for the admin and the shell too, not only this path.
    user.save(update_fields=["phone", "phone_verified_at", "updated_at"])

    supersede_phone_challenges(user)

    return user
