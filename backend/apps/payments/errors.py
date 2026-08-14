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


class PayoutNotActionable(APIError):
    """A move the payout lifecycle does not permit, or not by this actor.

    The same code covers a provider trying to mark their own payout paid and a
    provider cancelling one that has already been sent. Both are the same fact
    from the caller's side: this payout cannot be moved that way by you.
    """

    status_code = status.HTTP_409_CONFLICT
    default_code = "PAYOUT_NOT_ACTIONABLE"
    default_detail = "This payout can no longer be changed."
