"""Contact verification.

The only route by which `User.phone_verified_at` or `User.email_verified_at` is
ever set. No endpoint, serializer or admin field writes either, because an account
able to declare itself verified would make the capability policy decorative.

Phone and email share one challenge model, one set of rules and one code path.
The channel differs only in where the code is sent, how long it lives, and which
timestamp a success stamps.
"""

import secrets
from collections.abc import Callable
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
    EmailAlreadyVerified,
    InvalidVerificationCode,
    PhoneAlreadyVerified,
    PhoneNotSet,
    VerificationChallengeNotFound,
    VerificationCooldown,
    VerificationExhausted,
    VerificationExpired,
)
from apps.accounts.sms.base import get_sms_provider

if TYPE_CHECKING:
    from apps.accounts.models import User

Channel = VerificationChallenge.Channel


@dataclass(frozen=True)
class ChannelPolicy:
    """Everything that differs between verifying a phone and verifying an email."""

    channel: str
    settings_key: str
    verified_field: str
    send: Callable[[str, str], None]

    def config(self) -> dict:
        """Read per call so override_settings works and an environment can tune
        the timings without a code change."""
        return getattr(settings, self.settings_key)


def _send_email_code(destination: str, code: str) -> None:
    """Sends through Django's own email framework.

    No custom provider interface here: Django's backend setting already is the
    abstraction, and adding a parallel one would be duplication. The development
    default writes to the console and sends nothing.
    """
    from django.core.mail import send_mail

    send_mail(
        subject="Your Sync verification code",
        message=(
            f"Your Sync verification code is {code}.\n\n"
            "It expires shortly. If you did not ask for this, ignore this message."
        ),
        from_email=None,
        recipient_list=[destination],
        fail_silently=False,
    )


PHONE = ChannelPolicy(
    channel=Channel.PHONE,
    settings_key="PHONE_VERIFICATION",
    verified_field="phone_verified_at",
    send=lambda destination, code: get_sms_provider().send_verification_code(destination, code),
)

EMAIL = ChannelPolicy(
    channel=Channel.EMAIL,
    settings_key="EMAIL_VERIFICATION",
    verified_field="email_verified_at",
    send=_send_email_code,
)


def config() -> dict:
    """Backwards-compatible accessor for the phone timings."""
    return PHONE.config()


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


def _active_challenges(user: User, channel: str):
    return VerificationChallenge.objects.filter(
        user=user,
        channel=channel,
        consumed_at__isnull=True,
        superseded_at__isnull=True,
    )


def supersede_challenges(user: User, channel: str) -> int:
    """Retires every live challenge on a channel.

    Called when a new one is issued and when the destination changes, so only one
    code is ever live and a code overheard earlier cannot be used later.
    """
    return _active_challenges(user, channel).update(
        superseded_at=timezone.now(), updated_at=timezone.now()
    )


def supersede_phone_challenges(user: User) -> int:
    return supersede_challenges(user, Channel.PHONE)


@transaction.atomic
def request_verification(
    user: User,
    policy: ChannelPolicy,
    destination: str,
    *,
    request_ip: str | None = None,
) -> VerificationRequest:
    """Issues a code and sends it.

    Nothing is persisted if delivery fails: a challenge left behind after a failed
    send would ask for a code that never arrived, and would burn the cooldown for
    nothing.
    """
    limits = policy.config()
    now = timezone.now()

    # Cooldown is per destination, so changing the address or number lets a fresh
    # code be requested straight away while one destination cannot be spammed.
    recent = (
        VerificationChallenge.objects.filter(
            user=user, channel=policy.channel, destination=destination
        )
        .order_by("-last_sent_at")
        .first()
    )

    if recent is not None:
        cooldown = timedelta(seconds=limits["RESEND_COOLDOWN_SECONDS"])
        if now - recent.last_sent_at < cooldown:
            retry_after = int((recent.last_sent_at + cooldown - now).total_seconds()) + 1
            raise VerificationCooldown(retry_after=retry_after, channel=policy.channel)

    # The window is per account rather than per destination, so rotating
    # destinations is not a way around the limit.
    window_start = now - timedelta(seconds=limits["SEND_WINDOW_SECONDS"])
    sends_in_window = VerificationChallenge.objects.filter(
        user=user, channel=policy.channel, last_sent_at__gte=window_start
    ).count()

    if sends_in_window >= limits["MAX_SENDS_PER_WINDOW"]:
        raise VerificationCooldown(
            retry_after=limits["SEND_WINDOW_SECONDS"], channel=policy.channel
        )

    supersede_challenges(user, policy.channel)

    code = generate_code(limits["CODE_LENGTH"])
    challenge = VerificationChallenge.objects.create(
        user=user,
        channel=policy.channel,
        destination=destination,
        # Hashed with the project's configured password hashers, so the stored
        # value is useless on its own.
        code_hash=make_password(code),
        expires_at=now + timedelta(seconds=limits["TTL_SECONDS"]),
        max_attempts=limits["MAX_ATTEMPTS"],
        last_sent_at=now,
        request_ip=request_ip,
    )

    # Raising rolls the challenge back with the transaction.
    policy.send(destination, code)

    return VerificationRequest(challenge=challenge)


def confirm_verification(
    user: User, policy: ChannelPolicy, destination: str, challenge_id, code: str
) -> User:
    """Checks a code and, if it is right, stamps the channel verified.

    The failure is raised after the transaction commits, never inside it. A wrong
    guess must increment the attempt counter durably, and raising from inside the
    atomic block would roll that increment back and hand an attacker unlimited
    tries at no cost.
    """
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
                    channel=policy.channel,
                )
                .get()
            )
        except VerificationChallenge.DoesNotExist, DjangoValidationError, ValueError, TypeError:
            raise VerificationChallengeNotFound from None

        # A challenge is bound to the destination it was sent to. If the account's
        # address or number moved on, this code proves nothing about the new one.
        unusable = (
            challenge.is_consumed or challenge.is_superseded or challenge.destination != destination
        )
        if unusable:
            raise VerificationChallengeNotFound
        if challenge.is_expired:
            raise VerificationExpired(policy.channel)
        if challenge.is_exhausted:
            raise VerificationExhausted(policy.channel)

        if check_password(code, challenge.code_hash):
            now = timezone.now()
            challenge.consumed_at = now
            challenge.attempt_count += 1
            challenge.save(update_fields=["consumed_at", "attempt_count", "updated_at"])

            setattr(user, policy.verified_field, now)
            user.save(update_fields=[policy.verified_field, "updated_at"])
        else:
            challenge.attempt_count += 1
            challenge.save(update_fields=["attempt_count", "updated_at"])

            error = (
                VerificationExhausted(policy.channel)
                if challenge.is_exhausted
                else InvalidVerificationCode(
                    attempts_remaining=challenge.attempts_remaining, channel=policy.channel
                )
            )

    if error is not None:
        raise error

    return user


# --- phone -----------------------------------------------------------------


def request_phone_verification(user: User, *, request_ip: str | None = None) -> VerificationRequest:
    if not user.phone:
        raise PhoneNotSet
    if user.phone_verified_at is not None:
        # Not an error condition so much as a stale client. Sending another
        # message would cost money and confuse the recipient.
        raise PhoneAlreadyVerified

    return request_verification(user, PHONE, user.phone, request_ip=request_ip)


def confirm_phone_verification(user: User, challenge_id, code: str) -> User:
    if not user.phone:
        raise PhoneNotSet

    return confirm_verification(user, PHONE, user.phone, challenge_id, code)


# --- email -----------------------------------------------------------------


def request_email_verification(user: User, *, request_ip: str | None = None) -> VerificationRequest:
    if user.email_verified_at is not None:
        raise EmailAlreadyVerified

    return request_verification(user, EMAIL, user.email, request_ip=request_ip)


def confirm_email_verification(user: User, challenge_id, code: str) -> User:
    return confirm_verification(user, EMAIL, user.email, challenge_id, code)


# --- destination changes ---------------------------------------------------


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

    supersede_challenges(user, Channel.PHONE)

    return user
