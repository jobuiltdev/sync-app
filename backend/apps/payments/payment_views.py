"""Payment endpoints, and the one endpoint a provider talks to us through.

Three audiences, three rules:

* **The customer** may start a payment for their own booking and ask what
  happened to it. They may not tell us what happened to it.
* **The provider of the work** may ask a bank to confirm their payout account.
* **The payment provider** posts webhooks, authenticated by signature rather
  than by a session, because it has no account here.
"""

import json
import logging

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.views import customer_bookings
from apps.common.permissions import authenticated_user
from apps.payments import payment_services, services
from apps.payments.errors import InvalidWebhookSignature
from apps.payments.gateways.base import GatewayError, InvalidSignature, get_payment_gateway
from apps.payments.intents import PaymentIntent
from apps.payments.payment_serializers import (
    BankSerializer,
    PaymentInitializeSerializer,
    PaymentIntentSerializer,
    PayoutDestinationVerifySerializer,
    VerifiedPayoutDestinationSerializer,
)
from apps.payments.views import idempotency_key
from apps.providers.views import profile_for

logger = logging.getLogger(__name__)

#: A webhook body larger than this is not one of ours. Bounded before parsing so
#: an unauthenticated caller cannot make the process chew through a huge payload.
MAX_WEBHOOK_BYTES = 256 * 1024


class CustomerPaymentListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentIntentSerializer

    def get_queryset(self) -> QuerySet[PaymentIntent]:
        return payment_services.customer_intents(authenticated_user(self.request)).select_related(
            "booking"
        )

    @extend_schema(operation_id="customer_payments_list", summary="Your payments")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CustomerPaymentDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PaymentIntentSerializer

    def get_queryset(self) -> QuerySet[PaymentIntent]:
        return payment_services.customer_intents(authenticated_user(self.request)).select_related(
            "booking"
        )

    @extend_schema(operation_id="customer_payments_read", summary="One of your payments")
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class CustomerPaymentInitializeView(APIView):
    """Starts collecting payment for one booking."""

    permission_classes = [IsAuthenticated]
    serializer_class = PaymentInitializeSerializer

    @extend_schema(
        operation_id="customer_bookings_pay",
        summary="Pay for a booking",
        description=(
            "Charges the booking's own agreed total, which was fixed when it was "
            "requested. Send an Idempotency-Key header: a retry carrying the same "
            "key returns the payment the first attempt started rather than "
            "beginning a second collection. The response carries the checkout URL "
            "to open; nothing is paid until the provider confirms it."
        ),
        request=None,
        responses={
            status.HTTP_201_CREATED: PaymentIntentSerializer,
            status.HTTP_404_NOT_FOUND: None,
            status.HTTP_409_CONFLICT: None,
        },
    )
    def post(self, request: Request, pk: str) -> Response:
        booking = get_object_or_404(customer_bookings(request), pk=pk)

        intent = payment_services.initialize_payment(
            booking=booking,
            customer=authenticated_user(request),
            idempotency_key=idempotency_key(request),
        )

        return Response(PaymentIntentSerializer(intent).data, status=status.HTTP_201_CREATED)


class CustomerPaymentVerifyView(APIView):
    """Asks the provider what happened to a payment, and records the answer.

    The request body is ignored entirely. A client sending `{"status": "success"}`
    changes nothing, because the only input to this endpoint is what the payment
    provider says when asked directly.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PaymentIntentSerializer

    @extend_schema(
        operation_id="customer_payments_verify",
        summary="Check whether a payment went through",
        description=(
            "Asks the payment provider directly. Nothing in the request body is "
            "read, so a client cannot assert an outcome."
        ),
        request=None,
        responses={
            status.HTTP_200_OK: PaymentIntentSerializer,
            status.HTTP_404_NOT_FOUND: None,
            status.HTTP_409_CONFLICT: None,
        },
    )
    def post(self, request: Request, pk: str) -> Response:
        outcome = payment_services.verify_payment(pk, authenticated_user(request))
        return Response(PaymentIntentSerializer(outcome.intent).data, status=status.HTTP_200_OK)


class PaymentWebhookView(APIView):
    """Where the payment provider tells us what happened.

    `AllowAny` because the caller has no account here. Authentication is the
    signature over the exact bytes received, checked before the body is parsed or
    anything is written, and a body that fails it is refused without being read
    as JSON at all.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []
    serializer_class = None

    @extend_schema(
        operation_id="payments_webhook",
        summary="Payment provider webhook",
        description=(
            "Authenticated by signature, not by session. Safe to receive the same "
            "event any number of times: events are deduplicated by provider event "
            "id, and one that arrives after a payment has resolved changes nothing."
        ),
        request=None,
        responses={status.HTTP_200_OK: None, status.HTTP_401_UNAUTHORIZED: None},
    )
    def post(self, request: Request) -> Response:
        body: bytes = request.body

        if len(body) > MAX_WEBHOOK_BYTES:
            raise InvalidWebhookSignature

        gateway = get_payment_gateway()

        # Signature first, over the raw bytes. Parsing and re-serialising would
        # change whitespace and key order and never match, and doing any work
        # before this point would be doing work for an unauthenticated caller.
        try:
            gateway.verify_signature(body, self._signature(request))
        except InvalidSignature:
            # Deliberately no detail, here or in the log. The only thing worth
            # recording is that something was refused.
            logger.warning("Rejected a payment webhook with an invalid signature.")
            raise InvalidWebhookSignature from None

        try:
            payload = json.loads(body.decode())
            if not isinstance(payload, dict):
                raise ValueError
        except ValueError, UnicodeDecodeError:
            # Signed by the provider but not readable. Answered 200 so they stop
            # redelivering something we will never be able to act on.
            logger.warning("A signed payment webhook was not valid JSON.")
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        try:
            event = gateway.parse_event(payload)
        except KeyError, TypeError, ValueError, GatewayError:
            logger.warning("A signed payment webhook had an unrecognised shape.")
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        outcome = payment_services.apply_webhook_event(event, gateway_name=gateway.name, body=body)

        # Always 200 once the signature checks out. A provider that receives
        # anything else retries, and retrying will not change an event about a
        # reference we do not know or a payment that already resolved.
        return Response({"status": outcome}, status=status.HTTP_200_OK)

    @staticmethod
    def _signature(request: Request) -> str:
        # Paystack sends x-paystack-signature. The header name is the one piece of
        # vendor detail that has to live outside the adapter, because the adapter
        # is chosen after the header is read.
        return str(
            request.META.get("HTTP_X_PAYSTACK_SIGNATURE")
            or request.META.get("HTTP_X_WEBHOOK_SIGNATURE")
            or ""
        )


class ProviderBankListView(APIView):
    """The banks a provider can be paid at."""

    permission_classes = [IsAuthenticated]
    serializer_class = BankSerializer

    @extend_schema(
        operation_id="provider_banks_list",
        summary="Banks you can be paid at",
        responses={status.HTTP_200_OK: BankSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        from apps.payments.banks.base import BankLookupError, get_bank_resolver

        # Confirms the caller is a provider before anything else happens.
        profile_for(request)

        try:
            banks = get_bank_resolver().banks()
        except BankLookupError:
            banks = []

        return Response(BankSerializer(banks, many=True).data, status=status.HTTP_200_OK)


class ProviderDestinationVerifyView(APIView):
    """Asks the bank to confirm the account on file.

    Submitting an account number does not make it verified, which is why this is
    a separate step rather than something the save endpoint does on the quiet: it
    reaches a third party, it can fail for reasons that are nobody's fault, and
    the provider needs to see the name the bank returned.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PayoutDestinationVerifySerializer

    @extend_schema(
        operation_id="provider_payout_destination_verify",
        summary="Confirm your bank account",
        description=(
            "Resolves the account with the bank and records the name it holds. "
            "The account number is sent again because nothing stores it. A payout "
            "cannot be requested until this succeeds."
        ),
        request=PayoutDestinationVerifySerializer,
        responses={
            status.HTTP_200_OK: VerifiedPayoutDestinationSerializer,
            status.HTTP_422_UNPROCESSABLE_ENTITY: None,
        },
    )
    def post(self, request: Request) -> Response:
        serializer = PayoutDestinationVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        destination = services.verify_destination(
            profile_for(request), serializer.validated_data["account_number"]
        )

        return Response(
            VerifiedPayoutDestinationSerializer(destination).data, status=status.HTTP_200_OK
        )
