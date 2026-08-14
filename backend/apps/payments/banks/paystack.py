"""Paystack's account resolution, behind the resolver interface.

Paystack exposes `/bank/resolve`, which takes an account number and a NIBSS bank
code and returns the name the bank holds. That is exactly the check this boundary
exists for, so no separate vendor is needed for it.

Shares transport with the payment gateway rather than reimplementing it: same
credentials, same host, same error handling, and one place where a request to
Paystack is constructed.
"""

from typing import Any

from django.conf import settings

from apps.payments.banks.base import BankAccountResolver, BankLookupError, ResolvedAccount
from apps.payments.gateways.base import GatewayError
from apps.payments.gateways.paystack import PaystackGateway


class PaystackBankResolver(BankAccountResolver):
    name = "PAYSTACK"

    def __init__(self) -> None:
        try:
            self._transport = PaystackGateway()
        except GatewayError as exc:
            raise BankLookupError(str(exc)) from exc

    def resolve(self, *, account_number: str, bank_code: str) -> ResolvedAccount:
        digits = "".join(character for character in account_number if character.isdigit())

        try:
            data: dict[str, Any] = self._transport._request(
                "GET",
                f"/bank/resolve?account_number={digits}&bank_code={bank_code}",
            )
        except GatewayError as exc:
            # Paystack answers a bad account with a refusal rather than a
            # transport failure, and the transport turns any refusal into a
            # GatewayError. Both arrive here, and the caller is told the lookup
            # did not resolve rather than being told which of the two it was:
            # from the provider's side the next step is the same, check the
            # number and try again.
            raise BankLookupError(str(exc)) from exc

        account_name = str(data.get("account_name", "")).strip()
        if not account_name:
            raise BankLookupError("The bank did not return a name for that account.")

        return ResolvedAccount(
            account_name=account_name,
            bank_code=bank_code,
            account_number_last4=digits[-4:],
            reference=str(data.get("account_number", ""))[-4:],
        )

    def banks(self) -> list[dict[str, str]]:
        currency = settings.PAYSTACK.get("CURRENCY", "NGN")

        try:
            data = self._transport._request("GET", f"/bank?currency={currency}")
        except GatewayError as exc:
            raise BankLookupError(str(exc)) from exc

        # Paystack returns a list here rather than an object, which the shared
        # transport passes through unchanged.
        rows: list[dict[str, Any]] = data if isinstance(data, list) else []

        return [
            {"code": str(row.get("code", "")), "name": str(row.get("name", ""))}
            for row in rows
            if row.get("code") and row.get("name")
        ]
