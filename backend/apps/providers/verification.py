"""One provider's attempt to prove who they are.

A row per submission, never overwritten. A provider who is rejected and tries
again gets a new attempt, and the rejected one stays exactly as it was: what was
wrong, who decided, and when. Overwriting would make the one question that
matters after an incident, "what did we know and when", unanswerable.

### What is stored, and what is refused

Stored: outcomes, the vendor and its reference, the method, timestamps, which
consent notice was agreed to, four masked digits, a safe rejection code, and
non-identifying audit metadata.

Refused, by construction rather than by convention: full NIN or BVN, selfies,
portraits, biometric templates, authorization codes, PKCE verifiers and raw
vendor payloads. There is no field to put them in, `masked_identifier` is
constrained to four characters at the database level, and the audit blob is
filtered on the way in.

### Why this does not decide approval

`ProviderProfile.verification_status` is the lifecycle and it already exists.
This model records what an external check said; it never writes that field. A
clean external result moves the attempt to `UNDER_REVIEW`, which is a request for
a human to look, and nothing in this file or the services above it can produce
`APPROVED`.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db import models

from apps.common.models import BaseModel
from apps.providers.identity.base import CheckOutcome, IdentityMethod, RejectionCode
from apps.providers.models import ProviderProfile


class CheckStatus(models.TextChoices):
    """The storage mirror of `identity.base.CheckOutcome`.

    Two enums for one idea, on purpose. The vendor-facing vocabulary must not
    depend on Django, and the stored one must not change shape because an adapter
    was rewritten. A test asserts they stay in step.
    """

    PENDING = CheckOutcome.PENDING, "Not yet run"
    PASSED = CheckOutcome.PASSED, "Passed"
    FAILED = CheckOutcome.FAILED, "Failed"
    UNAVAILABLE = CheckOutcome.UNAVAILABLE, "Could not be checked"


class AttemptStatus(models.TextChoices):
    """Where one submission has got to.

    Distinct from `ProviderProfile.verification_status`, which is the provider's
    standing. An attempt is a thing that happened; the profile is what is true
    now. A provider with three rejected attempts and one approved one has one
    standing and four rows.
    """

    DRAFT = "DRAFT", "Started, not yet checked"
    CHECKING = "CHECKING", "Waiting on the identity provider"
    CHECK_FAILED = "CHECK_FAILED", "The identity check did not pass"
    UNDER_REVIEW = "UNDER_REVIEW", "Passed checks, waiting for a reviewer"
    APPROVED = "APPROVED", "Approved by a reviewer"
    REJECTED = "REJECTED", "Rejected by a reviewer"


#: The only legal moves for an attempt. Same arrangement as the profile lifecycle
#: next door: data rather than scattered conditionals, so the whole thing can be
#: read and tested in one place.
ATTEMPT_TRANSITIONS: dict[str, set[str]] = {
    AttemptStatus.DRAFT: {AttemptStatus.CHECKING},
    AttemptStatus.CHECKING: {AttemptStatus.CHECK_FAILED, AttemptStatus.UNDER_REVIEW},
    # A failed check is retried on the same attempt: the provider has not
    # submitted anything for a person to look at yet.
    AttemptStatus.CHECK_FAILED: {AttemptStatus.CHECKING},
    AttemptStatus.UNDER_REVIEW: {AttemptStatus.APPROVED, AttemptStatus.REJECTED},
    # Terminal. A provider who wants another go gets a new row.
    AttemptStatus.APPROVED: set(),
    AttemptStatus.REJECTED: set(),
}

#: Attempts that are finished with. Nothing may write to one of these again, which
#: is what makes the history immutable in practice rather than in intention.
TERMINAL_ATTEMPT_STATUSES = frozenset({AttemptStatus.APPROVED, AttemptStatus.REJECTED})

#: An attempt in one of these is still the provider's current business.
#:
#: A tuple in a fixed order rather than a set, because it is also the condition of
#: a partial unique index. A set iterates in whatever order it likes, so the
#: generated constraint differed between runs and `makemigrations` reported a
#: pending change on every invocation, for ever.
OPEN_ATTEMPT_STATUSES: tuple[str, ...] = (
    AttemptStatus.DRAFT,
    AttemptStatus.CHECKING,
    AttemptStatus.CHECK_FAILED,
    AttemptStatus.UNDER_REVIEW,
)

#: The wording a provider agreed to. Bumped when the notice changes, so an old
#: attempt keeps saying what was actually shown rather than what is shown now.
CONSENT_NOTICE_VERSION = "2026-08-v1"

#: Keys an adapter may put in `audit`. A closed set, because this column is the
#: one place a vendor payload could get in wholesale, and "we will remember not
#: to" is not a control.
ALLOWED_AUDIT_KEYS = frozenset(
    {"adapter", "script", "vendor_status", "score_band", "latency_ms", "attempted_at", "channel"}
)

#: Anything longer than this in an audit value is a payload rather than metadata.
MAX_AUDIT_VALUE_LENGTH = 120


class IllegalAttemptTransition(ValidationError):
    def __init__(self, current: str, target: str) -> None:
        allowed = ", ".join(sorted(ATTEMPT_TRANSITIONS.get(current, set()))) or "nothing"
        super().__init__(
            f"Cannot move this verification attempt from {current} to {target}. "
            f"Allowed from {current}: {allowed}.",
            code="illegal_attempt_transition",
        )


def can_transition_attempt(current: str, target: str) -> bool:
    return target in ATTEMPT_TRANSITIONS.get(current, set())


def sanitise_audit(audit: dict | None) -> dict:
    """Keeps only the metadata this model is willing to store.

    Unknown keys are dropped rather than rejected, so a vendor adding a field to
    its response does not break a check that was otherwise fine. Long values are
    truncated, because the failure this guards against is a whole payload arriving
    under a plausible key.
    """
    if not audit:
        return {}

    clean: dict[str, str] = {}
    for key, value in audit.items():
        if key not in ALLOWED_AUDIT_KEYS:
            continue
        text = str(value)
        clean[key] = text[:MAX_AUDIT_VALUE_LENGTH]
    return clean


class ProviderVerification(BaseModel):
    """One submission, and everything it is safe to remember about it."""

    provider = models.ForeignKey(
        ProviderProfile,
        on_delete=models.CASCADE,
        related_name="verification_attempts",
    )

    status = models.CharField(
        max_length=20, choices=AttemptStatus.choices, default=AttemptStatus.DRAFT
    )

    #: When the provider asked for the check, not when the row was made.
    submitted_at = models.DateTimeField(null=True, blank=True)

    # --- what the identity provider said ------------------------------------
    identity_check_status = models.CharField(
        max_length=12, choices=CheckStatus.choices, default=CheckStatus.PENDING
    )
    face_match_status = models.CharField(
        max_length=12, choices=CheckStatus.choices, default=CheckStatus.PENDING
    )
    liveness_status = models.CharField(
        max_length=12, choices=CheckStatus.choices, default=CheckStatus.PENDING
    )

    identity_vendor = models.CharField(max_length=40, blank=True)
    #: The vendor's handle for this check. The only thing support can quote back
    #: to them, and the reason a full identifier is never needed.
    identity_reference = models.CharField(max_length=120, blank=True)
    identity_method = models.CharField(
        max_length=20,
        blank=True,
        choices=[(value, value.replace("_", " ").title()) for value in IdentityMethod.ALL],
    )
    identity_checked_at = models.DateTimeField(null=True, blank=True)

    #: Last four characters. The database constraint is the real control here; the
    #: validator is for forms and the admin.
    masked_identifier = models.CharField(
        max_length=4, blank=True, validators=[MaxLengthValidator(4)]
    )

    #: Why the external check refused, from a closed set. Never a vendor's own
    #: message, which would leak their vocabulary and sometimes somebody's record.
    rejection_code = models.CharField(
        max_length=40,
        blank=True,
        choices=[(value, value.replace("_", " ").title()) for value in RejectionCode.ALL],
    )

    #: Non-identifying detail only. Filtered by `sanitise_audit` on the way in.
    audit = models.JSONField(default=dict, blank=True)

    #: Which notice was shown. Frozen per attempt so changing the wording later
    #: does not rewrite what somebody agreed to.
    consent_notice_version = models.CharField(max_length=20, blank=True)
    consented_at = models.DateTimeField(null=True, blank=True)

    # --- what a person decided ----------------------------------------------
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provider_verifications_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    #: A reviewer's words, shown to the provider. Free text because the reasons a
    #: human rejects somebody do not fit a closed set.
    review_note = models.TextField(blank=True, max_length=1000)

    class Meta:
        db_table = "providers_verification"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["provider", "-created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["identity_reference"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(masked_identifier="")
                | models.Q(masked_identifier__regex=r"^.{1,4}$"),
                name="providers_verification_masked_identifier_is_short",
            ),
            # One open attempt per provider. Without it, two taps on a slow
            # connection make two submissions and a reviewer sees the same person
            # twice.
            models.UniqueConstraint(
                fields=["provider"],
                condition=models.Q(status__in=OPEN_ATTEMPT_STATUSES),
                name="providers_verification_one_open_attempt",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.provider.display_name}: {self.status}"

    # --- reading -------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_ATTEMPT_STATUSES

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_ATTEMPT_STATUSES

    @property
    def all_checks_passed(self) -> bool:
        """Every one of the three, which is the bar for reaching a reviewer."""
        return (
            self.identity_check_status == CheckStatus.PASSED
            and self.face_match_status == CheckStatus.PASSED
            and self.liveness_status == CheckStatus.PASSED
        )

    @property
    def failed_checks(self) -> list[str]:
        """Which checks are the reason this did not get through."""
        failures = []
        for name, value in (
            ("identity", self.identity_check_status),
            ("face_match", self.face_match_status),
            ("liveness", self.liveness_status),
        ):
            if value in {CheckStatus.FAILED, CheckStatus.UNAVAILABLE}:
                failures.append(name)
        return failures

    # --- writing -------------------------------------------------------------

    def transition(self, target: str, *, update_fields: list[str] | None = None) -> None:
        """Moves the attempt, refusing anything the lifecycle disallows.

        Every status change goes through here. A terminal attempt refuses
        everything, which is what makes the history immutable rather than merely
        conventional.
        """
        if not can_transition_attempt(self.status, target):
            raise IllegalAttemptTransition(self.status, target)

        self.status = target
        fields = ["status", "updated_at", *(update_fields or [])]
        self.save(update_fields=sorted(set(fields)))
