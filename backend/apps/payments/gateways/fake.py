"""A gateway that moves no money, for development and for the test suite.

Deterministic on purpose. Every payment it is asked to start stays PENDING until
a test says otherwise, so nothing succeeds by accident and a test that means to
exercise the successful path has to say so.

It signs webhooks with the same HMAC construction Paystack uses, under a key from
settings, which is what lets the whole webhook path be tested end to end without
a Paystack account: signature checking, replay, and refusal of a forged body are
all real here, and only the vendor is not.
"""

import hashlib
import hmac
from typing import Any

from django.conf import settings

from apps.payments.gateways.base import (
    GatewayEvent,
    GatewayPayment,
    InitializedPayment,
    InvalidSignature,
    PaymentGateway,
    PaymentState,
)


class FakeGateway(PaymentGateway):
    """Records what it was asked to do and answers from a script.

    State lives on the class so a test can arrange an outcome without reaching
    the instance the domain constructed, matching how `LocMemSMSProvider` works.
    """

    name = "FAKE"

    #: reference -> the payment this gateway will report when asked.
    payments: dict[str, GatewayPayment] = {}
    #: Every initialize call, in order.
    initialized: list[dict[str, Any]] = []

    @property
    def secret(self) -> str:
        return settings.PAYMENT_GATEWAY_FAKE["SECRET"]

    # --- test arrangement --------------------------------------------------

    @classmethod
    def clear(cls) -> None:
        cls.payments = {}
        cls.initialized = []

    @classmethod
    def arrange(
        cls,
        reference: str,
        *,
        state: str = PaymentState.SUCCESSFUL,
        amount_kobo: int = 0,
        currency: str = "NGN",
        method: str = "card",
    ) -> GatewayPayment:
        """States what the provider will say about a reference from now on."""
        payment = GatewayPayment(
            reference=reference,
            state=state,
            amount_kobo=amount_kobo,
            currency=currency,
            gateway_reference=f"fake-{reference}",
            raw_status=state.lower(),
            method=method,
        )
        cls.payments[reference] = payment
        return payment

    @classmethod
    def sign(cls, body: bytes) -> str:
        """The signature a caller must send for this body to be accepted."""
        return hmac.new(
            settings.PAYMENT_GATEWAY_FAKE["SECRET"].encode(), body, hashlib.sha512
        ).hexdigest()

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
        type(self).initialized.append(
            {
                "reference": reference,
                "amount_kobo": amount_kobo,
                "email": email,
                "currency": currency,
                "metadata": metadata or {},
            }
        )

        # Pending, always. A fake that reported success on initialization would
        # let a test pass while the real flow, where nothing is settled until the
        # provider confirms, was broken.
        type(self).payments.setdefault(
            reference,
            GatewayPayment(
                reference=reference,
                state=PaymentState.PENDING,
                amount_kobo=amount_kobo,
                currency=currency,
                gateway_reference=f"fake-{reference}",
                raw_status="pending",
            ),
        )

        return InitializedPayment(
            gateway_reference=f"fake-{reference}",
            authorization_url=f"https://checkout.invalid/{reference}",
            access_code=f"access-{reference}",
        )

    def fetch(self, reference: str) -> GatewayPayment:
        payment = type(self).payments.get(reference)
        if payment is None:
            # An unknown reference is a real provider answer, not an outage. The
            # domain has to cope with being told a transaction does not exist.
            return GatewayPayment(
                reference=reference,
                state=PaymentState.FAILED,
                amount_kobo=0,
                currency="",
                raw_status="unknown",
            )
        return payment

    def verify_signature(self, body: bytes, signature: str) -> None:
        expected = hmac.new(self.secret.encode(), body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(expected, signature or ""):
            raise InvalidSignature("The webhook signature did not match.")

    def parse_event(self, payload: dict[str, Any]) -> GatewayEvent:
        event_type = str(payload.get("event", ""))
        data = payload.get("data") or {}
        handle = data.get("id") or data.get("reference") or ""

        payment = None
        if data:
            raw_status = str(data.get("status", ""))
            payment = GatewayPayment(
                reference=str(data.get("reference", "")),
                state={
                    "success": PaymentState.SUCCESSFUL,
                    "pending": PaymentState.PENDING,
                }.get(raw_status.lower(), PaymentState.FAILED),
                amount_kobo=int(data.get("amount") or 0),
                currency=str(data.get("currency", "")),
                gateway_reference=str(handle),
                raw_status=raw_status,
                method=str(data.get("channel", "")),
            )

        return GatewayEvent(
            event_id=f"{event_type}:{handle}",
            event_type=event_type,
            payment=payment,
        )
