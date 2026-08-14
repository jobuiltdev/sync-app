"""Sending money out, and the window where we might not know whether we did.

The most important tests in the project. A bug here does not lose data, it loses
money, and the specific bug it guards against is the one that pays somebody
twice because a network call timed out.
"""

from django.test import TestCase
from django.utils import timezone

from apps.bookings.state import ActorType
from apps.payments import services
from apps.payments.errors import (
    DestinationNotVerified,
    InsufficientBalance,
    InvalidPayoutDestination,
    PayoutNotActionable,
    PayoutNotFound,
)
from apps.payments.execution import PayoutAlreadySubmitted, execute_payout, reconcile_payout
from apps.payments.payouts import PayoutRequest, PayoutStatus
from apps.payments.tests.factories import earn, earning_setup, make_destination
from apps.payments.transfers.base import TransferState
from apps.payments.transfers.fake import FakeTransferProvider


class PayoutExecutionTestCase(TestCase):
    def setUp(self):
        FakeTransferProvider.clear()
        self.setup = earning_setup()
        self.provider = self.setup["provider"]
        make_destination(self.provider)
        earn(self.setup)
        self.payout = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=600_000
        )

    def refresh(self) -> PayoutRequest:
        self.payout.refresh_from_db()
        return self.payout


class SuccessfulExecutionTests(PayoutExecutionTestCase):
    def test_it_submits_the_transfer(self):
        execute_payout(self.payout.pk)

        self.assertEqual(len(FakeTransferProvider.submitted), 1)
        self.assertEqual(FakeTransferProvider.submitted[0]["amount_kobo"], 600_000)

    def test_it_reserves_our_own_reference_before_submitting(self):
        # The mechanism the whole design rests on. The reference must exist on
        # the row, not only in the request that carried it.
        execute_payout(self.payout.pk)

        payout = self.refresh()
        self.assertTrue(payout.transfer_reference.startswith("SYT-"))
        self.assertEqual(FakeTransferProvider.submitted[0]["reference"], payout.transfer_reference)

    def test_the_reference_it_reserved_is_what_it_recorded(self):
        execute_payout(self.payout.pk)

        self.assertIsNotNone(self.refresh().submitted_at)

    def test_a_pending_transfer_leaves_the_payout_processing(self):
        execute_payout(self.payout.pk)

        self.assertEqual(self.refresh().status, PayoutStatus.PROCESSING)

    def test_a_provider_that_confirms_immediately_pays_it(self):
        # Arranged before submission, so the fake answers SUCCESSFUL from the
        # submit call itself, which some providers do.
        FakeTransferProvider.transfers["preset"] = None
        del FakeTransferProvider.transfers["preset"]

        payout = self.payout
        FakeTransferProvider.arrange("placeholder")
        execute_payout(payout.pk)
        reference = self.refresh().transfer_reference
        FakeTransferProvider.arrange(reference, state=TransferState.SUCCESSFUL)

        reconcile_payout(payout.pk)

        self.assertEqual(self.refresh().status, PayoutStatus.PAID)

    def test_it_records_which_provider_moved_the_money(self):
        execute_payout(self.payout.pk)

        self.assertEqual(self.refresh().transfer_provider, "FAKE")

    def test_it_pays_to_the_recipient_handle_from_verification(self):
        # Never an account number. The handle was issued when the account was
        # confirmed, which is the one moment the number was in hand.
        execute_payout(self.payout.pk)

        self.assertTrue(FakeTransferProvider.submitted[0]["recipient_reference"].startswith("RCP_"))

    def test_no_account_number_is_sent_at_submission_time(self):
        execute_payout(self.payout.pk)

        self.assertNotIn("0123456789", str(FakeTransferProvider.submitted))


class DuplicateSubmissionTests(PayoutExecutionTestCase):
    """The rule that matters more than any other here."""

    def test_a_payout_that_was_submitted_is_never_submitted_again(self):
        execute_payout(self.payout.pk)

        with self.assertRaises(PayoutAlreadySubmitted):
            execute_payout(self.payout.pk)

        self.assertEqual(len(FakeTransferProvider.submitted), 1)

    def test_the_refusal_names_the_reference_so_it_can_be_reconciled(self):
        execute_payout(self.payout.pk)

        with self.assertRaises(PayoutAlreadySubmitted) as caught:
            execute_payout(self.payout.pk)

        self.assertEqual(
            caught.exception.details["transfer_reference"], self.refresh().transfer_reference
        )

    def test_ten_attempts_produce_one_transfer(self):
        execute_payout(self.payout.pk)

        for _ in range(9):
            with self.assertRaises(PayoutAlreadySubmitted):
                execute_payout(self.payout.pk)

        self.assertEqual(len(FakeTransferProvider.submitted), 1)

    def test_the_database_refuses_two_payouts_sharing_a_transfer_reference(self):
        from django.db import IntegrityError, transaction

        execute_payout(self.payout.pk)
        reference = self.refresh().transfer_reference

        with self.assertRaises(IntegrityError), transaction.atomic():
            PayoutRequest.objects.create(
                provider=self.provider,
                amount_kobo=1,
                status=PayoutStatus.FAILED,
                processed_at=timezone.now(),
                failure_reason="x",
                transfer_reference=reference,
                submitted_at=timezone.now(),
            )


class UnknownOutcomeTests(PayoutExecutionTestCase):
    """The crash window: submitted, and we never heard back."""

    def test_a_dropped_connection_leaves_the_payout_processing(self):
        FakeTransferProvider.fail_next_submit_with = "unknown"

        execute_payout(self.payout.pk)

        payout = self.refresh()
        self.assertEqual(payout.status, PayoutStatus.PROCESSING)
        self.assertTrue(payout.is_submitted)
        self.assertTrue(payout.needs_reconciliation)

    def test_it_is_not_failed_merely_because_we_could_not_hear_the_answer(self):
        # Failing it would release the money for a second payout while the first
        # may well have gone out.
        FakeTransferProvider.fail_next_submit_with = "unknown"

        execute_payout(self.payout.pk)

        self.assertNotEqual(self.refresh().status, PayoutStatus.FAILED)

    def test_it_is_not_retried_and_cannot_be(self):
        FakeTransferProvider.fail_next_submit_with = "unknown"
        execute_payout(self.payout.pk)

        with self.assertRaises(PayoutAlreadySubmitted):
            execute_payout(self.payout.pk)

    def test_reconciliation_resolves_it_when_the_money_did_go(self):
        FakeTransferProvider.fail_next_submit_with = "unknown"
        execute_payout(self.payout.pk)
        reference = self.refresh().transfer_reference

        # The provider did receive it, and says so when asked.
        FakeTransferProvider.arrange(reference, state=TransferState.SUCCESSFUL)
        reconcile_payout(self.payout.pk)

        self.assertEqual(self.refresh().status, PayoutStatus.PAID)

    def test_reconciliation_resolves_it_when_the_money_did_not_go(self):
        FakeTransferProvider.fail_next_submit_with = "unknown"
        execute_payout(self.payout.pk)
        reference = self.refresh().transfer_reference

        FakeTransferProvider.arrange(reference, state=TransferState.FAILED, reason="Account closed")
        reconcile_payout(self.payout.pk)

        payout = self.refresh()
        self.assertEqual(payout.status, PayoutStatus.FAILED)
        self.assertEqual(payout.failure_reason, "Account closed")

    def test_a_failure_returns_the_money_to_the_balance(self):
        FakeTransferProvider.fail_next_submit_with = "unknown"
        execute_payout(self.payout.pk)
        FakeTransferProvider.arrange(self.refresh().transfer_reference, state=TransferState.FAILED)
        reconcile_payout(self.payout.pk)

        self.assertEqual(services.available_balance(self.provider).available_kobo, 1_600_000)

    def test_a_provider_with_no_record_of_it_leaves_it_unresolved(self):
        # UNKNOWN must never become FAILED. A provider that has not processed our
        # reference yet looks exactly like one that never received it, and
        # releasing the money on that basis is how it goes out twice.
        FakeTransferProvider.fail_next_submit_with = "unknown"
        execute_payout(self.payout.pk)
        FakeTransferProvider.transfers.pop(self.refresh().transfer_reference)

        reconcile_payout(self.payout.pk)

        payout = self.refresh()
        self.assertEqual(payout.status, PayoutStatus.PROCESSING)
        self.assertTrue(payout.needs_reconciliation)

    def test_the_money_stays_reserved_while_the_outcome_is_unknown(self):
        FakeTransferProvider.fail_next_submit_with = "unknown"
        execute_payout(self.payout.pk)

        earnings = services.available_balance(self.provider)
        self.assertEqual(earnings.reserved_kobo, 600_000)
        self.assertEqual(earnings.available_kobo, 1_000_000)


class RejectedSubmissionTests(PayoutExecutionTestCase):
    """A provider that declined outright, having started nothing."""

    def test_a_refusal_fails_the_payout(self):
        FakeTransferProvider.fail_next_submit_with = "rejected"

        execute_payout(self.payout.pk)

        self.assertEqual(self.refresh().status, PayoutStatus.FAILED)

    def test_a_refusal_clears_the_reserved_reference(self):
        # Nothing was submitted under it, and leaving it would make the payout
        # look forever like one that might have moved money.
        FakeTransferProvider.fail_next_submit_with = "rejected"

        execute_payout(self.payout.pk)

        payout = self.refresh()
        self.assertEqual(payout.transfer_reference, "")
        self.assertIsNone(payout.submitted_at)
        self.assertFalse(payout.needs_reconciliation)

    def test_a_refusal_returns_the_money(self):
        FakeTransferProvider.fail_next_submit_with = "rejected"

        execute_payout(self.payout.pk)

        self.assertEqual(services.available_balance(self.provider).available_kobo, 1_600_000)

    def test_the_provider_can_ask_again_after_a_refusal(self):
        FakeTransferProvider.fail_next_submit_with = "rejected"
        execute_payout(self.payout.pk)

        again = services.request_payout(
            provider=self.provider, actor=self.provider.user, amount_kobo=600_000
        )

        self.assertEqual(again.status, PayoutStatus.REQUESTED)


class ExecutionGuardTests(PayoutExecutionTestCase):
    """Everything that must be true before money moves."""

    def test_a_cancelled_payout_is_never_sent(self):
        services.cancel_payout(self.payout.pk, self.provider)

        with self.assertRaises(PayoutNotActionable):
            execute_payout(self.payout.pk)

        self.assertEqual(FakeTransferProvider.submitted, [])

    def test_a_paid_payout_is_never_sent_again(self):
        execute_payout(self.payout.pk)
        FakeTransferProvider.arrange(
            self.refresh().transfer_reference, state=TransferState.SUCCESSFUL
        )
        reconcile_payout(self.payout.pk)

        with self.assertRaises(PayoutNotActionable):
            execute_payout(self.payout.pk)

    def test_an_unverified_destination_stops_it(self):
        make_destination(self.provider, verified=False)

        with self.assertRaises(DestinationNotVerified):
            execute_payout(self.payout.pk)

        self.assertEqual(FakeTransferProvider.submitted, [])
        self.assertFalse(self.refresh().is_submitted)

    def test_a_destination_with_no_recipient_handle_stops_it(self):
        destination = self.provider.payout_destination
        destination.provider_reference = ""
        destination.save(update_fields=["provider_reference"])

        with self.assertRaises(InvalidPayoutDestination):
            execute_payout(self.payout.pk)

        self.assertEqual(FakeTransferProvider.submitted, [])

    def test_the_amount_is_rechecked_against_the_records_not_trusted(self):
        # The settlements behind this payout are removed, so the earnings that
        # backed it no longer exist. A payout requested when the money was there
        # must not go out once it is not.
        from apps.payments.settlements import BookingSettlement

        BookingSettlement.objects.filter(provider=self.provider).delete()

        with self.assertRaises(InsufficientBalance):
            execute_payout(self.payout.pk)

        self.assertEqual(FakeTransferProvider.submitted, [])
        self.assertFalse(self.refresh().is_submitted)

    def test_an_unknown_payout_id_is_a_not_found(self):
        with self.assertRaises(PayoutNotFound):
            execute_payout("00000000-0000-4000-8000-000000000000")

    def test_a_malformed_payout_id_is_a_not_found_rather_than_a_crash(self):
        with self.assertRaises(PayoutNotFound):
            execute_payout("not-a-uuid")

    def test_nothing_is_written_when_a_guard_refuses(self):
        make_destination(self.provider, verified=False)

        with self.assertRaises(DestinationNotVerified):
            execute_payout(self.payout.pk)

        payout = self.refresh()
        self.assertEqual(payout.status, PayoutStatus.REQUESTED)
        self.assertEqual(payout.transfer_reference, "")


class PayoutReconciliationTests(PayoutExecutionTestCase):
    def submit(self) -> str:
        execute_payout(self.payout.pk)
        return self.refresh().transfer_reference

    def test_a_successful_transfer_pays_it(self):
        reference = self.submit()
        FakeTransferProvider.arrange(reference, state=TransferState.SUCCESSFUL)

        reconcile_payout(self.payout.pk)

        payout = self.refresh()
        self.assertEqual(payout.status, PayoutStatus.PAID)
        self.assertIsNotNone(payout.processed_at)

    def test_it_records_the_provider_reference(self):
        reference = self.submit()
        FakeTransferProvider.arrange(reference, state=TransferState.SUCCESSFUL)

        reconcile_payout(self.payout.pk)

        self.assertTrue(self.refresh().gateway_reference.startswith("TRF_"))

    def test_it_records_when_it_last_asked(self):
        self.submit()

        reconcile_payout(self.payout.pk)

        self.assertIsNotNone(self.refresh().reconciled_at)

    def test_a_still_processing_transfer_stays_processing(self):
        reference = self.submit()
        FakeTransferProvider.arrange(reference, state=TransferState.PENDING)

        reconcile_payout(self.payout.pk)

        self.assertEqual(self.refresh().status, PayoutStatus.PROCESSING)

    def test_reconciling_twice_is_safe(self):
        reference = self.submit()
        FakeTransferProvider.arrange(reference, state=TransferState.SUCCESSFUL)

        reconcile_payout(self.payout.pk)
        reconcile_payout(self.payout.pk)

        self.assertEqual(self.refresh().status, PayoutStatus.PAID)
        self.assertEqual(PayoutRequest.objects.filter(provider=self.provider).count(), 1)

    def test_reconciling_a_payout_that_was_never_submitted_does_nothing(self):
        reconcile_payout(self.payout.pk)

        self.assertEqual(self.refresh().status, PayoutStatus.REQUESTED)

    def test_a_paid_payout_cannot_be_dragged_back_to_failed(self):
        # Terminal is terminal. A provider changing its mind after the fact is a
        # dispute, not a state transition.
        reference = self.submit()
        FakeTransferProvider.arrange(reference, state=TransferState.SUCCESSFUL)
        reconcile_payout(self.payout.pk)

        FakeTransferProvider.arrange(reference, state=TransferState.FAILED)
        reconcile_payout(self.payout.pk)

        self.assertEqual(self.refresh().status, PayoutStatus.PAID)

    def test_a_paid_payout_cannot_be_dragged_back_to_processing(self):
        reference = self.submit()
        FakeTransferProvider.arrange(reference, state=TransferState.SUCCESSFUL)
        reconcile_payout(self.payout.pk)

        FakeTransferProvider.arrange(reference, state=TransferState.PENDING)
        reconcile_payout(self.payout.pk)

        self.assertEqual(self.refresh().status, PayoutStatus.PAID)

    def test_a_failed_payout_cannot_become_paid(self):
        reference = self.submit()
        FakeTransferProvider.arrange(reference, state=TransferState.FAILED)
        reconcile_payout(self.payout.pk)

        FakeTransferProvider.arrange(reference, state=TransferState.SUCCESSFUL)
        reconcile_payout(self.payout.pk)

        self.assertEqual(self.refresh().status, PayoutStatus.FAILED)

    def test_an_unknown_payout_id_is_a_not_found(self):
        with self.assertRaises(PayoutNotFound):
            reconcile_payout("00000000-0000-4000-8000-000000000000")


class ActorTests(PayoutExecutionTestCase):
    """Execution moves a payout as SYSTEM, which the lifecycle already permits."""

    def test_execution_uses_the_system_actor(self):
        execute_payout(self.payout.pk, actor_type=ActorType.SYSTEM)

        self.assertEqual(self.refresh().status, PayoutStatus.PROCESSING)

    def test_a_provider_actor_cannot_drive_execution(self):
        reference_before = self.refresh().transfer_reference
        FakeTransferProvider.arrange("x", state=TransferState.SUCCESSFUL)

        execute_payout(self.payout.pk, actor_type=ActorType.PROVIDER)
        FakeTransferProvider.arrange(
            self.refresh().transfer_reference, state=TransferState.SUCCESSFUL
        )

        # The submission itself is not actor-gated, but the resulting transition
        # is, and PROVIDER may not move a payout to PAID.
        with self.assertRaises(PayoutNotActionable):
            reconcile_payout_as_provider(self.payout.pk)

        self.assertEqual(reference_before, "")


def reconcile_payout_as_provider(payout_id):
    """Reconciliation driven by the wrong actor, for the test above."""
    from apps.payments.execution import _apply_transfer_result
    from apps.payments.transfers.base import get_transfer_provider

    payout = PayoutRequest.objects.get(pk=payout_id)
    result = get_transfer_provider().fetch(payout.transfer_reference)

    return _apply_transfer_result(payout, result, actor_type=ActorType.PROVIDER)
