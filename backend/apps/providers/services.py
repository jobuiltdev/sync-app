"""What may happen to a provider's verification, and who is allowed to cause it.

Every state change lives here. Views call these, the admin calls these, and
nothing writes `ProviderProfile.verification_status` or `ProviderVerification.status`
anywhere else. That is the point of the module: there is one place to read to know
what the rules are, and one place a reviewer's action and a provider's action both
have to pass through.

### The invariants this file exists to hold

1. **A machine cannot approve anybody.** `apply_identity_result` can reach
   `UNDER_REVIEW` and no further. Only `approve` moves a profile to `APPROVED`,
   and only a reviewer calls it.
2. **Phone and email first.** A paid identity check is not started for somebody
   who has not confirmed how to reach them, because that is where the cheap
   failures are caught.
3. **History is append-only.** Resubmission creates a row. Nothing edits a
   terminal attempt.
4. **A result lands once.** Vendors retry, webhooks arrive twice, and a provider
   on a slow connection taps twice. The second one is a no-op rather than a second
   check.
"""

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.exceptions import APIError
from apps.providers.identity.base import (
    IdentityCheckError,
    IdentityCheckRequest,
    IdentityCheckResult,
    get_identity_provider,
)
from apps.providers.models import ProviderProfile, VerificationStatus
from apps.providers.verification import (
    CONSENT_NOTICE_VERSION,
    AttemptStatus,
    CheckStatus,
    ProviderVerification,
    sanitise_audit,
)


class ContactNotVerified(APIError):
    default_code = "CONTACT_NOT_VERIFIED"
    default_detail = (
        "Confirm your phone number and email address before starting identity verification."
    )


class VerificationAlreadyOpen(APIError):
    status_code = 409
    default_code = "VERIFICATION_ALREADY_OPEN"
    default_detail = "You already have a verification in progress."


class AlreadyApproved(APIError):
    status_code = 409
    default_code = "PROVIDER_ALREADY_APPROVED"
    default_detail = "This provider is already approved."


class NoVerificationAttempt(APIError):
    status_code = 404
    default_code = "NO_VERIFICATION_ATTEMPT"
    default_detail = "There is no verification attempt to act on."


class IdentityProviderUnavailable(APIError):
    status_code = 503
    default_code = "IDENTITY_PROVIDER_UNAVAILABLE"
    default_detail = "The identity service could not be reached. Try again shortly."


class AttemptNotReviewable(APIError):
    status_code = 409
    default_code = "ATTEMPT_NOT_REVIEWABLE"
    default_detail = "This attempt is not waiting for review."


# --------------------------------------------------------------------------
# the checklist
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ChecklistItem:
    key: str
    label: str
    complete: bool
    #: What the provider does next, when anything. Empty when the item is done or
    #: when it is somebody else's turn.
    action: str = ""


@dataclass(frozen=True)
class VerificationChecklist:
    """What the server says is left to do.

    Computed here and sent whole, so the app never infers progress from a
    collection of booleans and never disagrees with the server about whether
    somebody may start.
    """

    items: tuple[ChecklistItem, ...]
    can_start_identity_check: bool
    blocked_reason: str

    @property
    def complete(self) -> bool:
        return all(item.complete for item in self.items)


def build_checklist(profile: ProviderProfile) -> VerificationChecklist:
    """The whole state of one provider's verification, from the server's view."""
    user = profile.user
    latest = latest_attempt(profile)

    phone_done = user.is_phone_verified
    email_done = user.is_email_verified
    contacts_done = phone_done and email_done

    identity_done = bool(latest and latest.identity_check_status == CheckStatus.PASSED)
    biometrics_done = bool(
        latest
        and latest.face_match_status == CheckStatus.PASSED
        and latest.liveness_status == CheckStatus.PASSED
    )
    review_done = profile.verification_status == VerificationStatus.APPROVED

    items = (
        ChecklistItem(
            key="phone",
            label="Phone number confirmed",
            complete=phone_done,
            action="" if phone_done else "VERIFY_PHONE",
        ),
        ChecklistItem(
            key="email",
            label="Email address confirmed",
            complete=email_done,
            action="" if email_done else "VERIFY_EMAIL",
        ),
        ChecklistItem(
            key="identity",
            label="Identity confirmed with NIMC",
            complete=identity_done,
            action="" if identity_done or not contacts_done else "START_IDENTITY",
        ),
        ChecklistItem(
            key="biometrics",
            label="Face match and liveness",
            complete=biometrics_done,
            action="" if biometrics_done or not contacts_done else "START_IDENTITY",
        ),
        ChecklistItem(
            key="review",
            # Named for what it is. A provider waiting on a person should be told
            # they are waiting on a person.
            label="Reviewed by the Sync team",
            complete=review_done,
        ),
    )

    blocked = ""
    if not contacts_done:
        blocked = "CONTACT_NOT_VERIFIED"
    elif profile.verification_status == VerificationStatus.APPROVED:
        blocked = "ALREADY_APPROVED"
    elif profile.verification_status == VerificationStatus.SUSPENDED:
        blocked = "SUSPENDED"
    elif latest is not None and latest.status == AttemptStatus.UNDER_REVIEW:
        blocked = "AWAITING_REVIEW"

    return VerificationChecklist(
        items=items,
        can_start_identity_check=not blocked,
        blocked_reason=blocked,
    )


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------


def latest_attempt(profile: ProviderProfile) -> ProviderVerification | None:
    return profile.verification_attempts.order_by("-created_at").first()


def open_attempt(profile: ProviderProfile) -> ProviderVerification | None:
    return (
        profile.verification_attempts.filter(status__in=list(AttemptStatus))
        .exclude(status__in=[AttemptStatus.APPROVED, AttemptStatus.REJECTED])
        .order_by("-created_at")
        .first()
    )


def attempt_history(profile: ProviderProfile):
    """Every attempt, newest first. Nothing is filtered out.

    A rejection a provider would rather forget is exactly the thing a reviewer
    needs to see on the next submission.
    """
    return profile.verification_attempts.select_related("reviewed_by").order_by("-created_at")


# --------------------------------------------------------------------------
# the provider's actions
# --------------------------------------------------------------------------


@transaction.atomic
def start_verification(profile: ProviderProfile) -> ProviderVerification:
    """Opens an attempt, or hands back the one already open.

    Idempotent on purpose. Two taps on a slow connection must not produce two
    submissions, and the database constraint that guarantees that would otherwise
    surface as a 500.
    """
    if profile.verification_status == VerificationStatus.APPROVED:
        raise AlreadyApproved

    checklist = build_checklist(profile)
    if not (checklist.items[0].complete and checklist.items[1].complete):
        raise ContactNotVerified

    existing = open_attempt(profile)
    if existing is not None:
        if existing.status == AttemptStatus.UNDER_REVIEW:
            raise VerificationAlreadyOpen
        return existing

    try:
        return ProviderVerification.objects.create(
            provider=profile,
            status=AttemptStatus.DRAFT,
            consent_notice_version=CONSENT_NOTICE_VERSION,
        )
    except IntegrityError as exc:
        # The unique partial index fired, which means a concurrent request won.
        # Hand back theirs rather than failing this one.
        existing = open_attempt(profile)
        if existing is None:
            raise VerificationAlreadyOpen from exc
        return existing


def run_identity_check(
    profile: ProviderProfile,
    *,
    authorization_reference: str,
    consented: bool,
) -> ProviderVerification:
    """Records consent, asks the configured provider, and applies the answer.

    Consent is recorded before the call and against the attempt, so a check that
    errors still leaves evidence of what the person agreed to. The notice version
    is whatever was frozen when the attempt opened.

    **Deliberately not one transaction.** Wrapping the whole function meant that
    raising on a vendor outage rolled back the attempt, the consent record and the
    failure marking along with it, so a provider who hit an outage was left with
    no trace that they had tried. The pieces that must be atomic are atomic on
    their own: `start_verification` and `apply_identity_result`.
    """
    if not consented:
        raise ContactNotVerified(
            "Identity verification needs your consent before it can start.",
            code="CONSENT_REQUIRED",
        )

    attempt = start_verification(profile)

    if attempt.status == AttemptStatus.UNDER_REVIEW:
        raise VerificationAlreadyOpen

    attempt.consented_at = timezone.now()
    attempt.submitted_at = attempt.submitted_at or timezone.now()
    attempt.save(update_fields=["consented_at", "submitted_at", "updated_at"])

    if attempt.status in {AttemptStatus.DRAFT, AttemptStatus.CHECK_FAILED}:
        attempt.transition(AttemptStatus.CHECKING)

    provider = get_identity_provider()
    try:
        result = provider.check(
            IdentityCheckRequest(
                provider_id=str(profile.id),
                attempt_id=str(attempt.id),
                authorization_reference=authorization_reference,
                consent_notice_version=attempt.consent_notice_version,
            )
        )
    except IdentityCheckError as exc:
        # An outage is not an outcome. The attempt goes back to failed-check so it
        # can be retried, and nothing is recorded against the person.
        attempt.transition(AttemptStatus.CHECK_FAILED)
        raise IdentityProviderUnavailable from exc

    return apply_identity_result(attempt, result)


@transaction.atomic
def apply_identity_result(
    attempt: ProviderVerification, result: IdentityCheckResult
) -> ProviderVerification:
    """Writes one external result onto an attempt, at most once.

    The replay guard is the vendor reference. A vendor retrying a webhook, a
    client retrying a request and a worker picking a job up twice all arrive here
    with the same reference, and only the first one is a check.

    **This can reach `UNDER_REVIEW` and nothing beyond it.** There is no branch in
    this function that produces an approved provider, which is the invariant the
    whole design rests on.
    """
    attempt = ProviderVerification.objects.select_for_update().get(pk=attempt.pk)

    if attempt.is_terminal:
        # A reviewer has already decided. A late vendor answer does not reopen it.
        return attempt

    already_applied = (
        attempt.identity_reference
        and attempt.identity_reference == result.reference
        and attempt.identity_checked_at is not None
    )
    if already_applied:
        return attempt

    attempt.identity_check_status = result.identity_outcome
    attempt.face_match_status = result.face_match_outcome
    attempt.liveness_status = result.liveness_outcome
    attempt.identity_vendor = result.vendor
    attempt.identity_reference = result.reference
    attempt.identity_method = result.method
    attempt.masked_identifier = result.masked_identifier[-4:]
    attempt.rejection_code = result.rejection_code
    attempt.audit = sanitise_audit(result.audit)
    attempt.identity_checked_at = timezone.now()
    attempt.save(
        update_fields=[
            "identity_check_status",
            "face_match_status",
            "liveness_status",
            "identity_vendor",
            "identity_reference",
            "identity_method",
            "masked_identifier",
            "rejection_code",
            "audit",
            "identity_checked_at",
            "updated_at",
        ]
    )

    if attempt.status != AttemptStatus.CHECKING:
        return attempt

    if result.all_passed:
        attempt.transition(AttemptStatus.UNDER_REVIEW)
        _move_profile_under_review(attempt.provider)
    else:
        attempt.transition(AttemptStatus.CHECK_FAILED)

    return attempt


def _move_profile_under_review(profile: ProviderProfile) -> None:
    """Puts the profile in the reviewer's queue, if it is not already there.

    Tolerant of a profile that is already under review, because a provider whose
    second attempt passes should not fail on a transition that changes nothing.
    """
    if profile.verification_status == VerificationStatus.UNDER_REVIEW:
        return
    profile.transition_verification(VerificationStatus.UNDER_REVIEW)


@transaction.atomic
def resubmit(profile: ProviderProfile) -> ProviderVerification:
    """Starts a fresh attempt after a rejection.

    A new row every time. The rejected one keeps its reviewer, its note and its
    timestamps, which is the whole reason attempts are separate from the profile.
    """
    if profile.verification_status == VerificationStatus.APPROVED:
        raise AlreadyApproved

    if open_attempt(profile) is not None:
        raise VerificationAlreadyOpen

    checklist = build_checklist(profile)
    if not (checklist.items[0].complete and checklist.items[1].complete):
        raise ContactNotVerified

    return ProviderVerification.objects.create(
        provider=profile,
        status=AttemptStatus.DRAFT,
        consent_notice_version=CONSENT_NOTICE_VERSION,
    )


# --------------------------------------------------------------------------
# the reviewer's actions
# --------------------------------------------------------------------------


@transaction.atomic
def approve(attempt: ProviderVerification, *, reviewer, note: str = "") -> ProviderVerification:
    """A person decides this provider may work.

    The only path to `APPROVED` in the codebase. It takes a reviewer because an
    approval with nobody's name on it is not an adjudication.
    """
    attempt = ProviderVerification.objects.select_for_update().get(pk=attempt.pk)

    if attempt.status != AttemptStatus.UNDER_REVIEW:
        raise AttemptNotReviewable

    if not attempt.all_checks_passed:
        # Belt and braces. Reaching `UNDER_REVIEW` already required this, and a
        # reviewer should not be the last thing standing between a failed check
        # and an approved provider.
        raise AttemptNotReviewable(
            "Every identity check must pass before this attempt can be approved.",
            code="CHECKS_NOT_PASSED",
        )

    attempt.reviewed_by = reviewer
    attempt.reviewed_at = timezone.now()
    attempt.review_note = note
    attempt.transition(
        AttemptStatus.APPROVED, update_fields=["reviewed_by", "reviewed_at", "review_note"]
    )

    profile = attempt.provider
    if profile.verification_status != VerificationStatus.APPROVED:
        profile.transition_verification(VerificationStatus.APPROVED)

    return attempt


@transaction.atomic
def reject(attempt: ProviderVerification, *, reviewer, note: str) -> ProviderVerification:
    """A person decides this submission does not stand.

    The note is required. A rejection a provider cannot act on is a support
    ticket, and the provider is the one who has to fix whatever it was.
    """
    if not note.strip():
        raise AttemptNotReviewable(
            "A rejection needs a reason the provider can act on.",
            code="REVIEW_NOTE_REQUIRED",
        )

    attempt = ProviderVerification.objects.select_for_update().get(pk=attempt.pk)

    if attempt.status != AttemptStatus.UNDER_REVIEW:
        raise AttemptNotReviewable

    attempt.reviewed_by = reviewer
    attempt.reviewed_at = timezone.now()
    attempt.review_note = note
    attempt.transition(
        AttemptStatus.REJECTED, update_fields=["reviewed_by", "reviewed_at", "review_note"]
    )

    profile = attempt.provider
    if profile.verification_status == VerificationStatus.UNDER_REVIEW:
        profile.transition_verification(VerificationStatus.REJECTED)

    return attempt


@transaction.atomic
def suspend(profile: ProviderProfile, *, reviewer, note: str = "") -> ProviderProfile:
    """Takes an approved provider off the platform without deleting anything.

    Also clears their own switch. Reinstating somebody should not silently put
    them back on call the same second.
    """
    profile.transition_verification(VerificationStatus.SUSPENDED)

    if profile.is_accepting_jobs:
        profile.is_accepting_jobs = False
        profile.save(update_fields=["is_accepting_jobs", "updated_at"])

    return profile


@transaction.atomic
def reinstate(profile: ProviderProfile, *, reviewer, note: str = "") -> ProviderProfile:
    """Puts a suspended provider back, still switched off.

    They turn themselves back on. Anything else means a suspension lifted at
    midnight starts sending offers at midnight.
    """
    profile.transition_verification(VerificationStatus.APPROVED)
    return profile
