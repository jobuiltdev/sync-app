"""The boundary between the verification domain and whoever proves identity.

The domain depends on this interface and never on a vendor. Prembly, Youverify
and VerifyMe all expose broadly the same shape through wildly different payloads;
the point of this module is that the shape is ours and the payloads never get
past here.

### What crosses this boundary, and what does not

**In:** a consent record and whatever the vendor needs to identify the person.
**Out:** three outcomes, a vendor reference, a method, and four digits.

What deliberately does not come back is anything that would be a liability to
hold. No full NIN, no portrait, no selfie, no biometric template, no
authorization code, no PKCE verifier, no raw vendor response. An adapter that
wants to log its raw payload for debugging must do so inside its own module and
must not put it in the result, because everything in `IdentityCheckResult` is
written to a row that outlives the request.

That is not caution for its own sake. Under NDPR, holding a full NIN or a
biometric template turns a marketplace into a processor of sensitive personal
data with obligations to match, and the reference already answers every support
question the full value would.

### Why three outcomes rather than one

A vendor can confirm the number is real, that the face in front of the camera
matches the record, and that the face is a live human, and these fail
independently and for different reasons. Collapsing them into one boolean loses
the only information that tells a provider what to fix, and it makes the
adjudication rule ("all three must pass") unstateable.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string


class IdentityCheckError(Exception):
    """The vendor could not complete the check.

    A transport or vendor-side failure, not a negative result. The distinction
    matters: a refusal is an outcome worth recording against the attempt, and an
    outage is not, because retrying it later may well succeed.
    """


class CheckOutcome:
    """How one of the three checks came out.

    Deliberately not a Django `TextChoices`: this is the vendor-facing vocabulary
    and it must not acquire a database dependency. `verification.py` mirrors it
    for storage.
    """

    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"

    ALL = (PENDING, PASSED, FAILED, UNAVAILABLE)


class IdentityMethod:
    """How the person proved who they were.

    NINAuth is the consent-based flow: the holder authorises the check at the
    identity provider and Sync never handles the number. The others exist because
    a vendor may fall back to them, and knowing which was used changes how much
    the result is worth.
    """

    NIN_AUTH = "NIN_AUTH"
    NIN_LOOKUP = "NIN_LOOKUP"
    BVN_LOOKUP = "BVN_LOOKUP"

    ALL = (NIN_AUTH, NIN_LOOKUP, BVN_LOOKUP)


#: Rejection codes an adapter may return. A closed set on purpose: these reach a
#: provider's screen, and a vendor's own message would leak both their vocabulary
#: and, occasionally, details of somebody's record.
class RejectionCode:
    NOT_FOUND = "IDENTITY_NOT_FOUND"
    MISMATCH = "IDENTITY_MISMATCH"
    FACE_MISMATCH = "FACE_MISMATCH"
    LIVENESS_FAILED = "LIVENESS_FAILED"
    CONSENT_DECLINED = "CONSENT_DECLINED"
    EXPIRED = "AUTHORIZATION_EXPIRED"
    ALREADY_USED = "IDENTITY_ALREADY_USED"
    VENDOR_UNAVAILABLE = "VENDOR_UNAVAILABLE"

    ALL = (
        NOT_FOUND,
        MISMATCH,
        FACE_MISMATCH,
        LIVENESS_FAILED,
        CONSENT_DECLINED,
        EXPIRED,
        ALREADY_USED,
        VENDOR_UNAVAILABLE,
    )


@dataclass(frozen=True)
class IdentityCheckResult:
    """Everything the domain is willing to keep from an identity check.

    Frozen because it is a record of what happened rather than a working value,
    and because an adapter handing back something mutable invites a caller to
    edit a vendor's answer before it is stored.

    `masked_identifier` is the last four characters and nothing else. It exists so
    support can say "the one ending 4821" to somebody on the phone, which is the
    entire legitimate use for any part of the number.
    """

    identity_outcome: str
    face_match_outcome: str
    liveness_outcome: str

    vendor: str
    reference: str
    method: str

    masked_identifier: str = ""
    rejection_code: str = ""
    #: Non-identifying detail for audit: vendor status strings, score bands,
    #: timings. Never raw personal data. `verification.py` re-validates this.
    audit: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, value in (
            ("identity_outcome", self.identity_outcome),
            ("face_match_outcome", self.face_match_outcome),
            ("liveness_outcome", self.liveness_outcome),
        ):
            if value not in CheckOutcome.ALL:
                raise ValueError(f"{name} must be one of {CheckOutcome.ALL}, got {value!r}")

        if self.method not in IdentityMethod.ALL:
            raise ValueError(f"method must be one of {IdentityMethod.ALL}, got {self.method!r}")

        if self.rejection_code and self.rejection_code not in RejectionCode.ALL:
            raise ValueError(f"rejection_code {self.rejection_code!r} is not a known code")

        if len(self.masked_identifier) > 4:
            raise ValueError(
                "masked_identifier carries the last four characters at most. "
                "Anything longer is the identifier itself."
            )

        if not self.reference:
            raise ValueError("reference is required: it is the only handle support has")

    @property
    def all_passed(self) -> bool:
        """Whether every check came back clean.

        The rule the domain adjudicates on. All three, not two of three and not a
        weighted score, because a provider enters a stranger's home.
        """
        return (
            self.identity_outcome == CheckOutcome.PASSED
            and self.face_match_outcome == CheckOutcome.PASSED
            and self.liveness_outcome == CheckOutcome.PASSED
        )


@dataclass(frozen=True)
class IdentityCheckRequest:
    """What the domain hands a vendor to start a check.

    Carries no identifier. Under NINAuth the holder authorises at the identity
    provider and returns an authorization reference; Sync never sees the number,
    so there is nowhere in this codebase that one could be logged, dumped in a
    traceback or written to a row by accident.
    """

    provider_id: str
    attempt_id: str
    #: What the holder came back with from the identity provider's consent screen.
    #: Opaque to the domain and never stored.
    authorization_reference: str
    #: Which notice the provider agreed to. Stored on the attempt so a change of
    #: wording later does not rewrite what somebody actually consented to.
    consent_notice_version: str


class IdentityProvider(ABC):
    """One way to establish that a person is who they say they are."""

    #: Recorded on the attempt so a result can be traced to the vendor that gave
    #: it, years later, after the settings have changed twice.
    name: str = "UNKNOWN"

    @abstractmethod
    def check(self, request: IdentityCheckRequest) -> IdentityCheckResult:
        """Run one identity check and return only what may be kept.

        Raises `IdentityCheckError` when the vendor could not be reached or would
        not answer. A negative answer is not an error: it comes back as a result
        with failing outcomes and a rejection code, because that is a fact about
        the attempt worth recording.
        """

    def supports_method(self, method: str) -> bool:
        return method in IdentityMethod.ALL


def get_identity_provider() -> IdentityProvider:
    """Builds the configured provider.

    Resolved per call rather than cached at import, so tests and settings
    overrides take effect without reaching into module state. Same arrangement as
    the SMS and bank boundaries.
    """
    provider_class = import_string(settings.IDENTITY_PROVIDER)
    return provider_class()
