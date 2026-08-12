from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.models import BaseModel


class VerificationChallenge(BaseModel):
    """A one-time code sent to prove an account owns a contact channel.

    The code itself is never here: only a hash. A challenge is a live credential
    while it stands, and a database dump should not hand an attacker working codes.

    `destination` is the normalised number the code was sent to, snapshotted at
    creation. It is the reason a challenge cannot be redirected: if the account's
    phone changes before the code is submitted, the challenge no longer matches
    the number being claimed and cannot verify it.

    The model carries `channel` so email verification is a new row rather than a
    second verification architecture. Only PHONE is wired up today.
    """

    class Channel(models.TextChoices):
        PHONE = "PHONE", "Phone"
        EMAIL = "EMAIL", "Email"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="verification_challenges",
    )

    channel = models.CharField(max_length=10, choices=Channel.choices)
    destination = models.CharField(
        max_length=254,
        help_text="The normalised address or number this code was sent to.",
    )

    code_hash = models.CharField(max_length=255, editable=False)

    expires_at = models.DateTimeField()
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField()

    #: Set once, on the attempt that succeeds. A consumed challenge is finished:
    #: there is no path back to usable, which is what makes it one-time.
    consumed_at = models.DateTimeField(null=True, blank=True)
    #: Set when a newer challenge supersedes this one, or the destination changes.
    superseded_at = models.DateTimeField(null=True, blank=True)

    last_sent_at = models.DateTimeField(default=timezone.now)
    request_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "accounts_verification_challenge"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(destination=""),
                name="accounts_challenge_destination_not_empty",
            ),
            models.CheckConstraint(
                condition=models.Q(max_attempts__gt=0),
                name="accounts_challenge_max_attempts_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "channel", "-created_at"]),
            models.Index(fields=["destination", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.channel} challenge for {self.destination}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def is_superseded(self) -> bool:
        return self.superseded_at is not None

    @property
    def is_exhausted(self) -> bool:
        return self.attempt_count >= self.max_attempts

    @property
    def is_usable(self) -> bool:
        """Whether this challenge could still verify something."""
        return not (self.is_consumed or self.is_superseded or self.is_expired or self.is_exhausted)

    @property
    def attempts_remaining(self) -> int:
        return max(self.max_attempts - self.attempt_count, 0)
