"""An identity provider that talks to nobody, for development and tests.

Deterministic and deliberately narrow. It exists so the whole provider flow can
be walked end to end on a laptop, in Expo Go, without a vendor contract and
without anybody handing real identity data to a development machine.

### It refuses real input on purpose

The authorization reference it accepts is a short synthetic token, and anything
that looks like a Nigerian NIN or BVN is rejected outright rather than processed.
That is not theatre. The most likely way real identity data ends up in a
development database is somebody typing their own NIN into a test form to see
what happens, and a fake that quietly accepts it is what makes that possible.

### It cannot approve anybody

Nothing in this module reaches `ProviderProfile`. A clean result moves an attempt
to `UNDER_REVIEW` and no further, because approval is adjudicated by a person and
that rule holds whichever adapter produced the result.
"""

import hashlib
import re

from apps.providers.identity.base import (
    CheckOutcome,
    IdentityCheckError,
    IdentityCheckRequest,
    IdentityCheckResult,
    IdentityMethod,
    IdentityProvider,
    RejectionCode,
)

#: Anything of this shape is a real government identifier and must not be handled
#: by a stand-in. NIN and BVN are both eleven digits.
LOOKS_LIKE_A_REAL_IDENTIFIER = re.compile(r"\d{11}")

#: Tokens a developer or a test can use to reach each outcome on purpose. Prefixed
#: so they cannot be confused with anything a vendor would issue.
SYNTHETIC_PREFIX = "sync-fake-"

PASS = f"{SYNTHETIC_PREFIX}pass"
FAIL_IDENTITY = f"{SYNTHETIC_PREFIX}not-found"
FAIL_FACE = f"{SYNTHETIC_PREFIX}face-mismatch"
FAIL_LIVENESS = f"{SYNTHETIC_PREFIX}liveness"
DECLINED = f"{SYNTHETIC_PREFIX}declined"
UNAVAILABLE = f"{SYNTHETIC_PREFIX}unavailable"

#: Which outcomes and rejection code each token produces, as
#: (identity, face, liveness, rejection_code).
SCRIPTS: dict[str, tuple[str, str, str, str]] = {
    PASS: (CheckOutcome.PASSED, CheckOutcome.PASSED, CheckOutcome.PASSED, ""),
    FAIL_IDENTITY: (
        CheckOutcome.FAILED,
        CheckOutcome.PENDING,
        CheckOutcome.PENDING,
        RejectionCode.NOT_FOUND,
    ),
    FAIL_FACE: (
        CheckOutcome.PASSED,
        CheckOutcome.FAILED,
        CheckOutcome.PASSED,
        RejectionCode.FACE_MISMATCH,
    ),
    FAIL_LIVENESS: (
        CheckOutcome.PASSED,
        CheckOutcome.PASSED,
        CheckOutcome.FAILED,
        RejectionCode.LIVENESS_FAILED,
    ),
    DECLINED: (
        CheckOutcome.FAILED,
        CheckOutcome.PENDING,
        CheckOutcome.PENDING,
        RejectionCode.CONSENT_DECLINED,
    ),
}


class FakeIdentityProvider(IdentityProvider):
    """Synthetic results, chosen by the token the caller supplies."""

    name = "FAKE"

    def check(self, request: IdentityCheckRequest) -> IdentityCheckResult:
        token = (request.authorization_reference or "").strip().lower()

        if LOOKS_LIKE_A_REAL_IDENTIFIER.search(token):
            # Refused rather than processed. A development database is not a place
            # for somebody's actual NIN, and the easiest way for one to arrive is
            # a person testing the form with their own.
            raise IdentityCheckError(
                "This looks like a real government identifier. The fake identity "
                "provider does not accept one. Use a sync-fake-* token."
            )

        if token == UNAVAILABLE:
            raise IdentityCheckError("The fake identity provider was asked to be unavailable.")

        if not token.startswith(SYNTHETIC_PREFIX):
            raise IdentityCheckError(
                f"Unrecognised authorization reference. Expected one of: "
                f"{', '.join(sorted(SCRIPTS))}, {UNAVAILABLE}."
            )

        identity, face, liveness, rejection = SCRIPTS.get(
            token,
            (
                CheckOutcome.FAILED,
                CheckOutcome.PENDING,
                CheckOutcome.PENDING,
                RejectionCode.NOT_FOUND,
            ),
        )

        return IdentityCheckResult(
            identity_outcome=identity,
            face_match_outcome=face,
            liveness_outcome=liveness,
            vendor=self.name,
            # Derived from the attempt *and* the token, because a reference
            # identifies one check rather than one attempt. Keying it on the
            # attempt alone made a genuine retry after a failure look like a
            # replay of the failure, and the retry was silently dropped.
            reference=self._reference(request.attempt_id, token),
            method=IdentityMethod.NIN_AUTH,
            # Synthetic, and only ever four characters.
            masked_identifier=self._masked(request.attempt_id),
            rejection_code=rejection,
            audit={"adapter": "fake", "script": token},
        )

    @staticmethod
    def _reference(attempt_id: str, token: str) -> str:
        digest = hashlib.sha256(f"fake-identity:{attempt_id}:{token}".encode()).hexdigest()
        return f"FAKE-{digest[:16].upper()}"

    @staticmethod
    def _masked(attempt_id: str) -> str:
        digest = hashlib.sha256(f"fake-mask:{attempt_id}".encode()).hexdigest()
        return "".join(character for character in digest if character.isdigit())[:4].ljust(4, "0")
