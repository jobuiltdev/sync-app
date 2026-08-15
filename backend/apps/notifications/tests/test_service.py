"""Recording a notification: once, safely, and never at the domain's expense.

The three properties this file exists to hold:

* a notification is recorded exactly once, enforced by the database
* nothing is queued for a transaction that rolled back
* nothing in this app can break the thing that called it
"""

from unittest.mock import patch

from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase

from apps.notifications.events import Channel, EventType
from apps.notifications.models import DeliveryStatus, Notification
from apps.notifications.service import dedupe_key, destination_for, notify
from apps.notifications.tests.factories import make_reachable, make_unreachable, verify_channels

SUBJECT_ID = "0f2a2c8e-6e5f-4a5f-9a2a-2c8e6e5f4a5f"


class RecordingTests(TestCase):
    def setUp(self):
        self.user = make_reachable()

    def test_one_row_per_routed_channel(self):
        created = notify(
            event_type=EventType.OFFER_RECEIVED,
            recipient=self.user,
            subject_id=SUBJECT_ID,
        )

        self.assertEqual({item.channel for item in created}, {Channel.SMS, Channel.EMAIL})

    def test_an_event_with_one_channel_records_one_row(self):
        created = notify(
            event_type=EventType.BOOKING_CREATED,
            recipient=self.user,
            subject_id=SUBJECT_ID,
        )

        self.assertEqual([item.channel for item in created], [Channel.EMAIL])

    def test_a_row_starts_pending_with_no_attempts(self):
        [notification] = notify(
            event_type=EventType.BOOKING_CREATED,
            recipient=self.user,
            subject_id=SUBJECT_ID,
        )

        self.assertEqual(notification.status, DeliveryStatus.PENDING)
        self.assertEqual(notification.attempts, 0)
        self.assertIsNone(notification.delivered_at)
        self.assertEqual(notification.failure_reason, "")

    def test_no_message_text_is_stored(self):
        """The design decision, asserted rather than trusted to review.

        A rendered message carries an address, a provider's name and an amount.
        A column for it would build a second copy of exactly what the rest of the
        system is careful with.
        """
        fields = {field.name for field in Notification._meta.get_fields()}

        self.assertNotIn("body", fields)
        self.assertNotIn("message", fields)
        self.assertNotIn("subject", fields)
        self.assertNotIn("destination", fields)

    def test_the_context_is_not_stored_either(self):
        notify(
            event_type=EventType.BOOKING_CREATED,
            recipient=self.user,
            subject_id=SUBJECT_ID,
            context={"street_address": "14 Adeola Odeku Street"},
        )
        row = Notification.objects.get()

        self.assertNotIn("Adeola", str(row.__dict__))


class DeduplicationTests(TestCase):
    def setUp(self):
        self.user = make_reachable()

    def test_the_same_event_twice_records_once(self):
        notify(event_type=EventType.PAYOUT_PAID, recipient=self.user, subject_id=SUBJECT_ID)
        again = notify(event_type=EventType.PAYOUT_PAID, recipient=self.user, subject_id=SUBJECT_ID)

        self.assertEqual(again, [])
        self.assertEqual(Notification.objects.count(), 2)

    def test_a_different_recipient_is_a_different_message(self):
        other = make_reachable()

        notify(event_type=EventType.OFFER_RECEIVED, recipient=self.user, subject_id=SUBJECT_ID)
        created = notify(
            event_type=EventType.OFFER_RECEIVED, recipient=other, subject_id=SUBJECT_ID
        )

        self.assertEqual(len(created), 2)

    def test_a_different_event_on_the_same_subject_is_a_different_message(self):
        """A booking moving through its lifecycle, which is the common case."""
        notify(event_type=EventType.BOOKING_EN_ROUTE, recipient=self.user, subject_id=SUBJECT_ID)
        created = notify(
            event_type=EventType.BOOKING_IN_PROGRESS, recipient=self.user, subject_id=SUBJECT_ID
        )

        self.assertEqual(len(created), 1)

    def test_the_key_separates_channel_and_recipient(self):
        first = dedupe_key(EventType.OFFER_RECEIVED, SUBJECT_ID, Channel.SMS, "user-a")
        by_channel = dedupe_key(EventType.OFFER_RECEIVED, SUBJECT_ID, Channel.EMAIL, "user-a")
        by_recipient = dedupe_key(EventType.OFFER_RECEIVED, SUBJECT_ID, Channel.SMS, "user-b")

        self.assertNotEqual(first, by_channel)
        self.assertNotEqual(first, by_recipient)

    def test_the_database_refuses_a_duplicate_key(self):
        """The constraint is the guarantee, not the application check above it."""
        [notification] = notify(
            event_type=EventType.BOOKING_CREATED, recipient=self.user, subject_id=SUBJECT_ID
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Notification.objects.create(
                event_type=EventType.BOOKING_CREATED,
                channel=Channel.EMAIL,
                recipient=self.user,
                dedupe_key=notification.dedupe_key,
            )


class TransactionSafetyTests(TestCase):
    def setUp(self):
        self.user = make_reachable()

    def test_a_rolled_back_transaction_records_nothing(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            notify(
                event_type=EventType.BOOKING_CREATED,
                recipient=self.user,
                subject_id=SUBJECT_ID,
            )
            raise RuntimeError("the booking failed after this point")

        self.assertEqual(Notification.objects.count(), 0)

    def test_a_rolled_back_transaction_queues_nothing(self):
        """The reason delivery is scheduled with on_commit.

        Without it, a booking that failed after this point would still have told
        the customer it had succeeded.
        """
        with (
            patch("apps.notifications.tasks.deliver_notification.delay") as delay,
            self.captureOnCommitCallbacks(execute=True),
            self.assertRaises(RuntimeError),
            transaction.atomic(),
        ):
            notify(
                event_type=EventType.BOOKING_CREATED,
                recipient=self.user,
                subject_id=SUBJECT_ID,
            )
            raise RuntimeError("rolled back")

        delay.assert_not_called()

    def test_a_committed_notification_is_queued(self):
        with (
            patch("apps.notifications.tasks.deliver_notification.delay") as delay,
            self.captureOnCommitCallbacks(execute=True),
        ):
            notify(
                event_type=EventType.BOOKING_CREATED,
                recipient=self.user,
                subject_id=SUBJECT_ID,
            )

        delay.assert_called_once()

    def test_the_queued_task_carries_the_context_rather_than_the_row(self):
        with (
            patch("apps.notifications.tasks.deliver_notification.delay") as delay,
            self.captureOnCommitCallbacks(execute=True),
        ):
            notify(
                event_type=EventType.BOOKING_CREATED,
                recipient=self.user,
                subject_id=SUBJECT_ID,
                context={"reference": "SY-8F3K2A"},
            )

        notification_id, payload = delay.call_args[0]

        self.assertEqual(str(Notification.objects.get().pk), notification_id)
        self.assertEqual(payload, {"reference": "SY-8F3K2A"})


class FailureIsolationTests(TestCase):
    """Nothing in this app may raise into the caller.

    Every one of these would, without the guards, fail a booking or a payout for
    a reason that has nothing to do with either.
    """

    def setUp(self):
        self.user = make_reachable()

    def test_a_database_failure_while_recording_is_swallowed(self):
        with patch(
            "apps.notifications.models.Notification.objects.create",
            side_effect=DatabaseError("the notifications table is gone"),
        ):
            created = notify(
                event_type=EventType.BOOKING_CREATED,
                recipient=self.user,
                subject_id=SUBJECT_ID,
            )

        self.assertEqual(created, [])

    def test_a_broker_that_is_down_is_swallowed(self):
        """The dangerous one.

        This runs in an `on_commit` callback, after the caller's transaction has
        committed but still on their stack. An exception here would surface inside
        booking code that has already succeeded.
        """
        with (
            patch(
                "apps.notifications.tasks.deliver_notification.delay",
                side_effect=OSError("connection refused"),
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            notify(
                event_type=EventType.BOOKING_CREATED,
                recipient=self.user,
                subject_id=SUBJECT_ID,
            )

        # Recorded, and visibly undelivered, rather than lost.
        self.assertEqual(Notification.objects.get().status, DeliveryStatus.PENDING)

    def test_an_unroutable_event_records_nothing_and_raises_nothing(self):
        created = notify(event_type="NO_SUCH_EVENT", recipient=self.user, subject_id=SUBJECT_ID)

        self.assertEqual(created, [])
        self.assertEqual(Notification.objects.count(), 0)


class DestinationTests(TestCase):
    """A channel is only used when that channel has been proven.

    An unverified number is a number somebody typed, and it may well be somebody
    else's. Sending a customer's address or a provider's name to it would hand a
    stranger the details of a real booking.
    """

    def test_a_verified_phone_is_usable(self):
        user = make_reachable()

        self.assertEqual(destination_for(user, Channel.SMS), user.phone)

    def test_an_unverified_phone_is_not(self):
        user = make_unreachable()

        self.assertEqual(destination_for(user, Channel.SMS), "")

    def test_a_verified_email_is_usable(self):
        user = make_reachable()

        self.assertEqual(destination_for(user, Channel.EMAIL), user.email)

    def test_an_unverified_email_is_not(self):
        user = make_unreachable()

        self.assertEqual(destination_for(user, Channel.EMAIL), "")

    def test_removing_a_number_removes_the_channel(self):
        """The account model clears verification whenever the number changes.

        Worth asserting from here as well, because this app depends on it: a
        number that changed hands must not keep an old verification and go on
        receiving somebody else's booking details.
        """
        user = make_reachable()
        user.phone = None
        user.save(update_fields=["phone"])

        self.assertEqual(destination_for(user, Channel.SMS), "")

    def test_one_channel_being_proven_does_not_prove_the_other(self):
        user = verify_channels(make_reachable(), phone=True, email=False)

        self.assertNotEqual(destination_for(user, Channel.SMS), "")
        self.assertEqual(destination_for(user, Channel.EMAIL), "")

    def test_an_unknown_channel_has_no_destination(self):
        self.assertEqual(destination_for(make_reachable(), "CARRIER_PIGEON"), "")
