"""Paystack, behind the gateway interface.

The only module in the codebase that knows what Paystack's API looks like. It
translates in both directions and makes no domain decisions: whether an amount is
right, whether a payment may be accepted and what that means for a booking are all
settled by `apps.payments.services` against our own records.

Credentials come from settings, which read them from the environment. Nothing here
has a default key, and constructing this class without one fails immediately
rather than at the first request.
"""

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings

from apps.payments.gateways.base import (
    GatewayError,
    GatewayEvent,
    GatewayPayment,
    InitializedPayment,
    InvalidSignature,
    PaymentGateway,
    PaymentState,
)

API_ROOT = "https://api.paystack.co"
TIMEOUT_SECONDS = 20

#: Paystack's transaction statuses, mapped onto the three the domain acts on.
#: Anything unrecognised is treated as FAILED rather than as pending, because
#: leaving a payment open on a status we do not understand is the failure mode
#: that ends with a provider paid for work nobody paid for.
STATUS_MAP = {
    "success": PaymentState.SUCCESSFUL,
    "pending": PaymentState.PENDING,
    "ongoing": PaymentState.PENDING,
    "processing": PaymentState.PENDING,
    "queued": PaymentState.PENDING,
    "failed": PaymentState.FAILED,
    "abandoned": PaymentState.FAILED,
    "reversed": PaymentState.FAILED,
}


class PaystackGateway(PaymentGateway):
    name = "PAYSTACK"

    def __init__(self) -> None:
        config = settings.PAYSTACK
        self.secret_key = config["SECRET_KEY"]
        self.api_root = config.get("API_ROOT", API_ROOT)
        self.timeout = config.get("TIMEOUT_SECONDS", TIMEOUT_SECONDS)

        if not self.secret_key:
            # Fails here rather than at the first payment, so a misconfigured
            # deployment is obvious the moment anything tries to take money.
            raise GatewayError(
                "PAYSTACK_SECRET_KEY is not set. Paystack cannot be used without it."
            )

    # --- transport ---------------------------------------------------------

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict:
        """One HTTP call to Paystack.

        Uses urllib rather than adding a dependency: two endpoints and a fixed
        payload shape do not justify one, and the surface here is small enough
        that the standard library is not the awkward choice.
        """
        request = urllib.request.Request(
            f"{self.api_root}{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.secret_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            # The body may explain the refusal, and it does not contain our key.
            detail = exc.read().decode(errors="replace")[:500]
            raise GatewayError(f"Paystack returned {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            # Never interpolate the exception's request object, which carries the
            # Authorization header.
            raise GatewayError(f"Could not reach Paystack: {type(exc).__name__}") from exc

        if not payload.get("status"):
            raise GatewayError(f"Paystack refused the request: {payload.get('message', '')}")

        return payload.get("data") or {}

    # --- gateway interface -------------------------------------------------

    def initialize(
        self,
        *,
        reference: str,
        amount_kobo: int,
        email: str,
        currency: str,
        metadata: dict[str, Any] | None = None,
    ) -> InitializedPayment:
        # Paystack counts in the currency's minor unit, which for NGN is kobo, so
        # the amount crosses this boundary unconverted and no rounding happens.
        data = self._request(
            "POST",
            "/transaction/initialize",
            {
                "reference": reference,
                "amount": amount_kobo,
                "email": email,
                "currency": currency,
                "metadata": metadata or {},
            },
        )

        return InitializedPayment(
            gateway_reference=str(data.get("reference", reference)),
            authorization_url=str(data.get("authorization_url", "")),
            access_code=str(data.get("access_code", "")),
        )

    def fetch(self, reference: str) -> GatewayPayment:
        data = self._request("GET", f"/transaction/verify/{reference}")
        return self._to_payment(data, fallback_reference=reference)

    def verify_signature(self, body: bytes, signature: str) -> None:
        """Paystack signs the raw body with HMAC SHA512 under the secret key.

        Computed over the bytes exactly as received. Re-serialising parsed JSON
        first would change whitespace and key order and never match.
        """
        expected = hmac.new(self.secret_key.encode(), body, hashlib.sha512).hexdigest()

        # Constant time, so a wrong signature cannot be refined a character at a
        # time by measuring how long the comparison took.
        if not hmac.compare_digest(expected, signature or ""):
            raise InvalidSignature("The webhook signature did not match.")

    def parse_event(self, payload: dict[str, Any]) -> GatewayEvent:
        event_type = str(payload.get("event", ""))
        data = payload.get("data") or {}

        return GatewayEvent(
            event_id=self._event_id(event_type, data),
            event_type=event_type,
            payment=self._to_payment(data) if data else None,
        )

    # --- translation -------------------------------------------------------

    @staticmethod
    def _event_id(event_type: str, data: dict[str, Any]) -> str:
        """A stable id for deduplication.

        Paystack does not put an event id on the envelope, so one is built from
        the event type and the transaction it concerns. Redelivery of the same
        event produces the same string, which is what deduplication needs, while
        two different events about one transaction stay distinct.
        """
        handle = data.get("id") or data.get("reference") or ""
        return f"{event_type}:{handle}"

    @staticmethod
    def _to_payment(data: dict[str, Any], fallback_reference: str = "") -> GatewayPayment:
        raw_status = str(data.get("status", ""))

        return GatewayPayment(
            reference=str(data.get("reference", fallback_reference)),
            state=STATUS_MAP.get(raw_status.lower(), PaymentState.FAILED),
            # Paystack reports the minor unit, so this is already kobo for NGN.
            amount_kobo=int(data.get("amount") or 0),
            currency=str(data.get("currency", "")),
            gateway_reference=str(data.get("id") or data.get("reference") or ""),
            raw_status=raw_status,
            method=str(data.get("channel", "")),
        )
