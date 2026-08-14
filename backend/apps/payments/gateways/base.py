"""The boundary between the payment domain and whoever moves the money.

The domain depends on this interface and never on a vendor. Nothing outside this
package imports Paystack, mentions Paystack, or knows what shape a Paystack
payload has. Swapping provider is a settings change plus one new subclass.

The types below are the provider-neutral vocabulary. A gateway's job is to
translate its own API into these and nothing more: it makes no decision about
whether a payment is acceptable, because that decision needs our record of what
was supposed to be paid, which a gateway does not have.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string


class GatewayError(Exception):
    """The provider could not be reached, or answered with something unusable.

    Deliberately not split into a taxonomy of provider failures. From the domain's
    side there are two outcomes that matter, "the provider told us about a
    payment" and "the provider did not", and inventing categories for the second
    would be guessing at which ones callers will branch on.
    """


class InvalidSignature(Exception):
    """A webhook body that did not come from the provider, or was altered.

    Separate from GatewayError because it is not a failure to reach anybody. It is
    an unauthenticated request pretending to be one, and the only correct response
    is to refuse it without processing a byte of the payload.
    """


class PaymentState:
    """What a provider says about a transaction, in our terms.

    Three states, because three is what the domain acts on. A provider reporting
    something it calls "reversed" or "abandoned" maps onto FAILED here, and the
    original wording travels in `raw_status` for support to read.
    """

    PENDING = "PENDING"
    SUCCESSFUL = "SUCCESSFUL"
    FAILED = "FAILED"


@dataclass(frozen=True)
class InitializedPayment:
    """What comes back from asking a provider to start a payment."""

    #: The provider's own handle on this transaction, if it issues one now.
    gateway_reference: str
    #: Where the customer completes the payment. This is what the app opens.
    authorization_url: str
    #: Short-lived token some providers use for an embedded checkout.
    access_code: str = ""


@dataclass(frozen=True)
class GatewayPayment:
    """A provider's account of one transaction.

    Carries the amount and currency as the provider has them, because verifying a
    payment means comparing those against what we expected. A gateway that only
    returned a status would leave the domain unable to tell a correct payment from
    one for the wrong sum.
    """

    reference: str
    state: str
    amount_kobo: int
    currency: str
    gateway_reference: str = ""
    #: The provider's own word for the state, kept for support conversations.
    raw_status: str = ""
    #: How the customer paid, where the provider says. Card, transfer, USSD.
    method: str = ""


@dataclass(frozen=True)
class GatewayEvent:
    """A webhook, translated out of the provider's shape into ours.

    `event_id` is what deduplication runs on and must be stable for the same event
    redelivered. `payment` is present when the event concerns a transaction, which
    is every event this milestone handles.
    """

    event_id: str
    event_type: str
    payment: GatewayPayment | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class PaymentGateway(ABC):
    """What the payment domain needs from a provider, and nothing more."""

    #: Stored on every record this gateway produces, so a payment taken through
    #: one provider is still identifiable after the setting changes.
    name: str

    @abstractmethod
    def initialize(
        self,
        *,
        reference: str,
        amount_kobo: int,
        email: str,
        currency: str,
        metadata: dict[str, Any] | None = None,
    ) -> InitializedPayment:
        """Asks the provider to start a payment and tell us where to send the payer."""

    @abstractmethod
    def fetch(self, reference: str) -> GatewayPayment:
        """Asks the provider what actually happened to a transaction.

        The authority on whether money moved. Never the client, and never a
        webhook body on its own.
        """

    @abstractmethod
    def verify_signature(self, body: bytes, signature: str) -> None:
        """Raises InvalidSignature unless this body came from the provider."""

    @abstractmethod
    def parse_event(self, payload: dict[str, Any]) -> GatewayEvent:
        """Turns a provider payload into a provider-neutral event."""


def get_payment_gateway() -> PaymentGateway:
    """Builds the configured gateway.

    Resolved per call rather than cached at import, so tests and settings
    overrides take effect without reaching into module state, and so importing
    Django never constructs a client or touches the network.
    """
    gateway_class = import_string(settings.PAYMENT_GATEWAY)
    return gateway_class()
