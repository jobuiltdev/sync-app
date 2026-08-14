"""The boundary between payout destinations and whoever can confirm one exists.

Resolving an account number to the name the bank holds against it is the only
check that distinguishes an account somebody owns from ten digits they typed. It
cannot be done locally: no amount of validation proves an account is real, and a
provider who mistypes one digit would otherwise have money sent into a stranger's
account with nothing having looked wrong.

Same shape as the payment gateway boundary. The domain depends on this interface,
one module knows a vendor, and the result is provider-neutral.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string


class BankLookupError(Exception):
    """The provider could not be reached, or answered with something unusable.

    Distinct from a resolution that failed. A bank saying "no such account" is an
    answer and leaves the destination refused; not reaching the bank at all leaves
    the destination as it was, and the provider should try again rather than be
    told their account is wrong.
    """


@dataclass(frozen=True)
class ResolvedAccount:
    """What a bank says about an account number.

    Carries the name and nothing else it might have offered. A resolution reply
    can include a customer identifier at the bank, and holding one buys nothing
    the account itself does not already give us while adding something to leak.
    """

    account_name: str
    bank_code: str
    #: Enough to tie the answer to the question. Never the full number.
    account_number_last4: str
    #: The provider's handle on this lookup, for support conversations.
    reference: str = ""


class BankAccountResolver(ABC):
    """What the payout domain needs from whoever can look up an account."""

    name: str

    @abstractmethod
    def resolve(self, *, account_number: str, bank_code: str) -> ResolvedAccount:
        """Returns the name the bank holds, or raises BankLookupError.

        Implementations must not log or persist the account number. It arrives,
        it is used, and it goes no further.
        """

    @abstractmethod
    def banks(self) -> list[dict[str, str]]:
        """The institutions this provider can pay into.

        The app needs a list to choose from, and a hardcoded one goes stale every
        time a bank merges or a new one is licensed.
        """


def get_bank_resolver() -> BankAccountResolver:
    """Builds the configured resolver, per call, so nothing happens at import."""
    resolver_class = import_string(settings.BANK_RESOLVER)
    return resolver_class()
