"""Paystack Transfers, behind the transfer interface.

Two calls and a lookup: create a transfer recipient, start a transfer against it,
and ask what happened. Shares transport with the payment gateway rather than
reimplementing it, so there is one place a request to Paystack is built.

**Paystack treats the transfer reference as idempotent.** Submitting the same
reference twice returns the existing transfer rather than starting a second one,
which is what makes reserving our reference before the call worth doing. It is
the second line of defence: the first is that this system refuses to resubmit a
payout that already carries one.
"""

from typing import Any

from apps.payments.gateways.base import GatewayError
from apps.payments.gateways.paystack import PaystackGateway
from apps.payments.transfers.base import (
    TransferError,
    TransferProvider,
    TransferRejected,
    TransferResult,
    TransferState,
)

#: Paystack's transfer statuses, mapped onto the four the domain acts on.
#:
#: Anything unrecognised becomes UNKNOWN rather than FAILED, which is the
#: opposite of the payment gateway's rule and deliberately so. A payment we
#: cannot interpret should not be treated as money received; a transfer we
#: cannot interpret must not be treated as money not sent, because the safe
#: assumption there is that it may well have gone.
STATUS_MAP = {
    "success": TransferState.SUCCESSFUL,
    "pending": TransferState.PENDING,
    "processing": TransferState.PENDING,
    "received": TransferState.PENDING,
    "otp": TransferState.PENDING,
    "failed": TransferState.FAILED,
    "abandoned": TransferState.FAILED,
    "reversed": TransferState.FAILED,
}


class PaystackTransferProvider(TransferProvider):
    name = "PAYSTACK"

    def __init__(self) -> None:
        try:
            self._transport = PaystackGateway()
        except GatewayError as exc:
            raise TransferRejected(str(exc)) from exc

    def ensure_recipient(
        self,
        *,
        account_number: str,
        bank_code: str,
        account_name: str,
        existing_reference: str = "",
    ) -> str:
        if existing_reference:
            # Already created. Paystack recipients are stable, and creating a
            # second one for the same account would leave two handles for one
            # destination and no rule about which is current.
            return existing_reference

        digits = "".join(character for character in account_number if character.isdigit())

        try:
            data = self._transport._request(
                "POST",
                "/transferrecipient",
                {
                    "type": "nuban",
                    "name": account_name,
                    "account_number": digits,
                    "bank_code": bank_code,
                    "currency": "NGN",
                },
            )
        except GatewayError as exc:
            raise TransferRejected(f"Paystack would not accept that account: {exc}") from exc

        recipient = str(data.get("recipient_code", ""))
        if not recipient:
            raise TransferRejected("Paystack did not return a recipient code.")

        return recipient

    def submit(
        self,
        *,
        reference: str,
        amount_kobo: int,
        currency: str,
        recipient_reference: str,
        reason: str = "",
    ) -> TransferResult:
        try:
            data = self._transport._request(
                "POST",
                "/transfer",
                {
                    "source": "balance",
                    "reference": reference,
                    "amount": amount_kobo,
                    "recipient": recipient_reference,
                    "currency": currency,
                    "reason": reason[:100] or "Sync payout",
                },
            )
        except GatewayError as exc:
            # This is the case the whole design turns on. The request may have
            # arrived and been acted on before the connection dropped, so this
            # is not a failure to transfer: it is not knowing. It travels as
            # TransferError, and the caller must leave the payout unresolved for
            # reconciliation rather than retrying or failing it.
            raise TransferError(str(exc)) from exc

        return self._to_result(data, fallback_reference=reference)

    def fetch(self, reference: str) -> TransferResult:
        try:
            data = self._transport._request("GET", f"/transfer/verify/{reference}")
        except GatewayError as exc:
            # Paystack answers an unknown reference with a refusal, which the
            # transport turns into a GatewayError. Unknown is an answer here, and
            # a useful one: it means no transfer with our reference exists, so
            # nothing was sent under it.
            return TransferResult(
                reference=reference,
                state=TransferState.UNKNOWN,
                raw_status="unknown",
                reason=str(exc)[:200],
            )

        return self._to_result(data, fallback_reference=reference)

    @staticmethod
    def _to_result(data: dict[str, Any], fallback_reference: str = "") -> TransferResult:
        raw_status = str(data.get("status", ""))

        return TransferResult(
            reference=str(data.get("reference", fallback_reference)),
            state=STATUS_MAP.get(raw_status.lower(), TransferState.UNKNOWN),
            gateway_reference=str(data.get("transfer_code") or data.get("id") or ""),
            raw_status=raw_status,
            reason=str(data.get("failure_reason") or data.get("gateway_response") or "")[:200],
        )
