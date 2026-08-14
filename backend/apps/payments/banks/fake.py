"""An account resolver that talks to no bank, for development and tests.

Deterministic, and deliberately not permissive: it resolves only numbers a test
has arranged, so a test that means to exercise a successful lookup has to say so
and one that forgets gets a refusal rather than a silent pass.
"""

from apps.payments.banks.base import BankAccountResolver, BankLookupError, ResolvedAccount

#: Enough to populate a picker in development. Real codes, so a switch to the
#: Paystack resolver does not invalidate anything a developer already typed.
DEV_BANKS = [
    {"code": "044", "name": "Access Bank"},
    {"code": "058", "name": "Guaranty Trust Bank"},
    {"code": "011", "name": "First Bank of Nigeria"},
    {"code": "033", "name": "United Bank for Africa"},
    {"code": "057", "name": "Zenith Bank"},
    {"code": "50211", "name": "Kuda Bank"},
    {"code": "999992", "name": "OPay"},
]


class FakeBankResolver(BankAccountResolver):
    name = "FAKE"

    #: (bank_code, account_number) -> the name this resolver will return.
    accounts: dict[tuple[str, str], str] = {}

    @classmethod
    def clear(cls) -> None:
        cls.accounts = {}

    @classmethod
    def arrange(cls, *, account_number: str, bank_code: str, account_name: str) -> None:
        """States what the bank will say about an account from now on."""
        cls.accounts[(bank_code, account_number)] = account_name

    def resolve(self, *, account_number: str, bank_code: str) -> ResolvedAccount:
        digits = "".join(character for character in account_number if character.isdigit())

        account_name = type(self).accounts.get((bank_code, digits))
        if account_name is None:
            raise BankLookupError("Could not resolve that account number.")

        return ResolvedAccount(
            account_name=account_name,
            bank_code=bank_code,
            account_number_last4=digits[-4:],
            reference=f"fake-{digits[-4:]}",
        )

    def banks(self) -> list[dict[str, str]]:
        return list(DEV_BANKS)
