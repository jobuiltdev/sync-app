"""A transfer provider that moves no money, for development and the test suite.

Deterministic, and able to reproduce the case that matters most: a submission
whose outcome we never learn. `fail_next_submit_with` makes the provider raise
`TransferError` **after** recording the transfer, which is exactly the crash
window a real timeout opens, and is the only way to test that the system
recovers from it rather than resubmitting.
"""

from typing import Any

from django.conf import settings

from apps.payments.transfers.base import (
    TransferError,
    TransferProvider,
    TransferRejected,
    TransferResult,
    TransferState,
)


class FakeTransferProvider(TransferProvider):
    name = "FAKE"

    #: reference -> what this provider will say about it.
    transfers: dict[str, TransferResult] = {}
    #: Every submit call, in order.
    submitted: list[dict[str, Any]] = []
    #: Recipients created, keyed by (bank_code, account_number).
    recipients: dict[tuple[str, str], str] = {}

    #: Set to raise on the next submit. "unknown" records the transfer first and
    #: then raises, which is the timeout-after-success window; "rejected" raises
    #: without recording anything, which is a clean refusal.
    fail_next_submit_with: str = ""

    @classmethod
    def clear(cls) -> None:
        cls.transfers = {}
        cls.submitted = []
        cls.recipients = {}
        cls.fail_next_submit_with = ""

    @classmethod
    def arrange(
        cls,
        reference: str,
        *,
        state: str = TransferState.SUCCESSFUL,
        reason: str = "",
    ) -> TransferResult:
        """States what the provider will say about a reference from now on."""
        result = TransferResult(
            reference=reference,
            state=state,
            gateway_reference=f"TRF_fake_{reference[-8:]}",
            raw_status=state.lower(),
            reason=reason,
        )
        cls.transfers[reference] = result
        return result

    def ensure_recipient(
        self,
        *,
        account_number: str,
        bank_code: str,
        account_name: str,
        existing_reference: str = "",
    ) -> str:
        if existing_reference:
            return existing_reference

        digits = "".join(character for character in account_number if character.isdigit())
        key = (bank_code, digits)
        type(self).recipients.setdefault(key, f"RCP_fake_{digits[-4:]}")
        return type(self).recipients[key]

    def submit(
        self,
        *,
        reference: str,
        amount_kobo: int,
        currency: str,
        recipient_reference: str,
        reason: str = "",
    ) -> TransferResult:
        failure = type(self).fail_next_submit_with
        type(self).fail_next_submit_with = ""

        if failure == "rejected":
            # Refused outright. Nothing was started, so there is nothing to
            # reconcile and nothing that could have moved.
            raise TransferRejected("The provider refused that transfer.")

        type(self).submitted.append(
            {
                "reference": reference,
                "amount_kobo": amount_kobo,
                "currency": currency,
                "recipient_reference": recipient_reference,
            }
        )

        # Recorded before the failure below on purpose: a transfer that reached
        # the provider and then timed out on the way back is the window this
        # whole design exists for, and a fake that did not reproduce it would
        # leave the recovery path untested.
        result = type(self).transfers.get(reference) or TransferResult(
            reference=reference,
            state=TransferState.PENDING,
            gateway_reference=f"TRF_fake_{reference[-8:]}",
            raw_status="pending",
        )
        type(self).transfers[reference] = result

        if failure == "unknown":
            raise TransferError("The connection dropped before the provider answered.")

        return result

    def fetch(self, reference: str) -> TransferResult:
        result = type(self).transfers.get(reference)
        if result is None:
            # No transfer exists under our reference, so nothing was sent under
            # it. An answer rather than an outage.
            return TransferResult(
                reference=reference,
                state=TransferState.UNKNOWN,
                raw_status="unknown",
            )
        return result

    @property
    def signing_secret(self) -> str:
        return settings.PAYMENT_GATEWAY_FAKE["SECRET"]
