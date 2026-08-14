"""Financial errors, as stable machine codes.

Same contract as the rest of the API: the code is what the app branches on and
cannot change, the message is for a person and can be reworded freely.

None of these say anything about money that is not the caller's own. A provider
who is refused learns what they may do about it and nothing about anybody else.
"""

from rest_framework import status

from apps.common.exceptions import APIError


class SettlementUnavailable(APIError):
    """Asked to settle a booking that has not earned anything.

    A booking that was cancelled, or one still in progress, has no amount owed to
    anybody. Raised by the domain rather than the API, since the only caller today
    is booking completion.
    """

    status_code = status.HTTP_409_CONFLICT
    default_code = "SETTLEMENT_UNAVAILABLE"
    default_detail = "This booking has not been completed, so there is nothing to settle."


class PayoutNotFound(APIError):
    """Not this provider's payout, or no such payout.

    One code for both, and a 404 for both, matching how offers and bookings
    already treat somebody else's row. A 403 would confirm the id belongs to
    someone, and the amount a competitor is withdrawing is not a fact this API
    should help anybody establish.
    """

    status_code = status.HTTP_404_NOT_FOUND
    default_code = "PAYOUT_NOT_FOUND"
    default_detail = "That payout could not be found."


class InvalidPayoutAmount(APIError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "INVALID_PAYOUT_AMOUNT"
    default_detail = "Enter an amount greater than zero."


class InsufficientBalance(APIError):
    """More was asked for than has been earned and not yet claimed.

    The details carry the caller's own available balance, which they can already
    read from the earnings endpoint, so telling them here saves a round trip
    without disclosing anything new.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "INSUFFICIENT_BALANCE"
    default_detail = "That is more than your available balance."

    def __init__(self, available_kobo: int, requested_kobo: int) -> None:
        super().__init__(
            details={"available_kobo": available_kobo, "requested_kobo": requested_kobo}
        )


class PayoutAlreadyRequested(APIError):
    """A payout is already in flight for this provider.

    One at a time, so that what is being withdrawn is never a question. This is
    also what the losing side of two simultaneous requests is told.
    """

    status_code = status.HTTP_409_CONFLICT
    default_code = "PAYOUT_ALREADY_REQUESTED"
    default_detail = "You already have a payout in progress. Wait for it to finish."


class InvalidPayoutDestination(APIError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "INVALID_PAYOUT_DESTINATION"
    default_detail = "Add the bank account you want to be paid into first."


class BookingNotPayable(APIError):
    """Nothing to pay for, or no longer anything to pay for."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "BOOKING_NOT_PAYABLE"
    default_detail = "This booking cannot be paid for."


class PaymentNotFound(APIError):
    """Not this customer's payment, or no such payment.

    One code and a 404 for both, matching how bookings, offers and payouts
    already treat somebody else's row.
    """

    status_code = status.HTTP_404_NOT_FOUND
    default_code = "PAYMENT_NOT_FOUND"
    default_detail = "That payment could not be found."


class PaymentAmountMismatch(APIError):
    """A provider reported a payment for a sum that is not the one we asked for.

    Refused rather than accepted at whatever figure arrived. This is the check
    that stops a booking being marked paid by a transaction for one naira, and
    the one a hostile webhook would be aiming at.

    The details carry the caller's own booking amount, which they can already
    read, and never the figure the provider reported: that belongs to whatever
    other transaction produced it.
    """

    status_code = status.HTTP_409_CONFLICT
    default_code = "PAYMENT_AMOUNT_MISMATCH"
    default_detail = "That payment does not match the amount for this booking."

    def __init__(
        self, *, expected_kobo: int, reported_kobo: int, message: str | None = None
    ) -> None:
        super().__init__(message, details={"expected_kobo": expected_kobo})
        # Kept off the wire but available to a caller that has the exception, so
        # the webhook path can log the discrepancy without exposing it.
        self.reported_kobo = reported_kobo


class InvalidWebhookSignature(APIError):
    """A webhook body that did not come from the provider.

    401 rather than 400. The request is not malformed, it is unauthenticated, and
    the response says nothing else: an attacker probing the endpoint learns only
    that they were refused.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "INVALID_WEBHOOK_SIGNATURE"
    default_detail = "Rejected."


class BankLookupFailed(APIError):
    """The bank did not recognise the account, or could not be asked.

    One code for both. From the provider's side the next step is the same: check
    the number and the bank and try again.
    """

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "BANK_ACCOUNT_NOT_RESOLVED"
    default_detail = "We could not confirm that account with the bank. Check the details."


class DestinationNotVerified(APIError):
    """A payout was asked for against an account nobody has confirmed."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "PAYOUT_DESTINATION_NOT_VERIFIED"
    default_detail = "Confirm your bank account before requesting a payout."


class PayoutNotActionable(APIError):
    """A move the payout lifecycle does not permit, or not by this actor.

    The same code covers a provider trying to mark their own payout paid and a
    provider cancelling one that has already been sent. Both are the same fact
    from the caller's side: this payout cannot be moved that way by you.
    """

    status_code = status.HTTP_409_CONFLICT
    default_code = "PAYOUT_NOT_ACTIONABLE"
    default_detail = "This payout can no longer be changed."
