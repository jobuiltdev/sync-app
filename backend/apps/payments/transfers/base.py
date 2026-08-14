"""The boundary between the payout domain and whoever actually moves the money.

Same shape as the payment gateway and the bank resolver: the domain depends on
this interface, one module knows a vendor, and a fake makes the whole path
testable with no account anywhere.

**This is the only outbound money movement in the system.** Everything else
either takes money in, which the customer initiates and the provider confirms, or
records what is owed. That makes it the one place where a request we sent and an
answer we did not receive is a question about real naira, and the interface is
shaped around that fact:

* `submit` takes **our** reference, chosen before the call. That is what makes an
  unanswered submission recoverable rather than a guess.
* `fetch` takes the same reference, so the question "did that transfer happen"
  can always be asked, even when we never learned the provider's own id.

A provider that cannot answer `fetch` by our reference cannot be used safely here.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string


class TransferError(Exception):
    """The provider could not be reached, or answered with something unusable.

    Raised when we do not know whether money moved. That is the whole meaning of
    it, and the caller must not treat it as a failure to transfer: a timeout on
    the way back from a successful transfer looks exactly like this.
    """


class TransferRejected(Exception):
    """The provider refused to start the transfer at all.

    Different from `TransferError` in the way that matters most: nothing was
    submitted, so there is nothing to reconcile and nothing that could have
    moved. Refusals are things like an unknown recipient or an insufficient
    balance at the provider.
    """


class TransferState:
    """What a provider says about a transfer, in our terms.

    Four, not three. `UNKNOWN` is the one that earns its place: a provider that
    has no record of our reference is telling us something quite different from a
    provider that says the transfer failed, and collapsing the two would either
    strand money or release it twice.
    """

    PENDING = "PENDING"
    SUCCESSFUL = "SUCCESSFUL"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class TransferResult:
    """A provider's account of one transfer."""

    reference: str
    state: str
    #: The provider's own handle, for support conversations and their dashboard.
    gateway_reference: str = ""
    #: The provider's own word for the state.
    raw_status: str = ""
    #: Why it failed, where the provider says. Shown to the provider being paid.
    reason: str = ""


class TransferProvider(ABC):
    """What the payout domain needs from whoever moves money out."""

    name: str

    @abstractmethod
    def submit(
        self,
        *,
        reference: str,
        amount_kobo: int,
        currency: str,
        recipient_reference: str,
        reason: str = "",
    ) -> TransferResult:
        """Starts a transfer, or raises.

        `reference` is ours and is chosen before this is called. Implementations
        must pass it to the provider as the transaction's own reference, so that
        submitting the same reference twice is one transfer at the provider
        rather than two. That is the second line of defence behind our own
        refusal to resubmit.

        Raises `TransferRejected` when the provider declined and nothing was
        started. Raises `TransferError` when the outcome is unknown.
        """

    @abstractmethod
    def fetch(self, reference: str) -> TransferResult:
        """Asks what happened to a transfer, by our own reference.

        The function reconciliation is built on. Must answer for a reference the
        provider has never seen, with `UNKNOWN`, rather than raising.
        """

    @abstractmethod
    def ensure_recipient(
        self,
        *,
        account_number: str,
        bank_code: str,
        account_name: str,
        existing_reference: str = "",
    ) -> str:
        """Returns the provider's handle for the account being paid.

        Most providers want a recipient created once and referred to afterwards,
        which is also what lets this system stop holding account numbers: the
        handle comes back here and the number does not have to be kept.
        """


def get_transfer_provider() -> TransferProvider:
    """Builds the configured provider, per call, so nothing happens at import."""
    provider_class = import_string(settings.PAYOUT_TRANSFER_PROVIDER)
    return provider_class()
