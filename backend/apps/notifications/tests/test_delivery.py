"""Getting one message out, and what happens when that does not work.

The distinction these tests protect is between a provider being unreachable and a
provider refusing. Treating both as retryable fills the queue with work that will
never succeed and pays for each attempt; treating both as final loses messages
over a thirty second outage.
"""

from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from apps.accounts.sms.base import SMSDeliveryError
from apps.accounts.sms.locmem import LocMemSMSProvider
from apps.notifications.delivery import (
    PermanentDeliveryFailure,
    TemporaryDeliveryFailure,
    classify,
    deliver,
    record_permanent_failure,
)
from apps.notifications.events import Channel, EventType
from apps.notifications.models import DeliveryStatus, Notification
from apps.notifications.tasks import MAX_ATTEMPTS, deliver_notification
from apps.notifications.tests.factories import make_reachable, make_unreachable

CONTEXT = {
    "reference": "SY-8F3K2A",
    "service_name": "Standard clean",
    "provider_name": "Ada Cleaning Services",
    "area": "Victoria Island",
    "amount_kobo": 1_600_000,
}


def make_notification(recipient, *, channel=Channel.SMS, event=EventType.OFFER_RECEIVED):
    return Notification.objects.create(
        event_type=event,
        channel=channel,
        recipient=recipient,
        subject_type="Offer",
        subject_reference="SY-8F3K2A",
        dedupe_key=f"{event}:{channel}:{recipient.pk}",
    )


@override_settings(
    SMS_BACKEND="apps.accounts.sms.locmem.LocMemSMSProvider",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class DeliveryTests(TestCase):
    def setUp(self):
        LocMemSMSProvider.clear()
        mail.outbox = []
        self.user = make_reachable()

    def test_an_sms_reaches_the_provider_interface(self):
        notification = make_notification(self.user)

        deliver_notification(str(notification.pk), CONTEXT)
        notification.refresh_from_db()

        self.assertEqual(notification.status, DeliveryStatus.SENT)
        self.assertIsNotNone(notification.delivered_at)
        self.assertEqual(notification.attempts, 1)
        self.assertEqual(LocMemSMSProvider.messages[0].phone, self.user.phone)

    def test_an_email_reaches_the_email_backend(self):
        notification = make_notification(self.user, channel=Channel.EMAIL)

        deliver_notification(str(notification.pk), CONTEXT)
        notification.refresh_from_db()

        self.assertEqual(notification.status, DeliveryStatus.SENT)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertTrue(mail.outbox[0].subject)

    def test_the_message_is_rendered_from_the_context(self):
        notification = make_notification(self.user)

        deliver_notification(str(notification.pk), CONTEXT)

        self.assertIn("Victoria Island", LocMemSMSProvider.messages[0].body)

    def test_no_verified_destination_is_skipped_rather_than_failed(self):
        """Nothing went wrong. There was simply nobody it could safely go to."""
        notification = make_notification(make_unreachable())

        deliver_notification(str(notification.pk), CONTEXT)
        notification.refresh_from_db()

        self.assertEqual(notification.status, DeliveryStatus.SKIPPED)
        self.assertEqual(LocMemSMSProvider.messages, [])
        self.assertTrue(notification.failure_reason)

    def test_a_skipped_message_is_not_marked_delivered(self):
        notification = make_notification(make_unreachable())

        deliver_notification(str(notification.pk), CONTEXT)
        notification.refresh_from_db()

        self.assertIsNone(notification.delivered_at)

    def test_a_channel_with_no_sender_is_permanent_and_not_a_skip(self):
        """A channel nothing can send on is a deployment problem.

        Distinct from having nobody to send to, and recorded as a failure rather
        than a skip so it is visible instead of looking like an ordinary
        unverified recipient.
        """
        notification = make_notification(self.user)
        # Not saved: the point is what `deliver` does with a channel it has no
        # sender for, not what the column allows.
        notification.channel = "PIGEON"

        with self.assertRaises(PermanentDeliveryFailure):
            deliver(notification, CONTEXT)

    def test_only_an_unverified_destination_becomes_a_skip(self):
        """Skipped and failed are different answers to a support question.

        Skipped means we chose not to send. Failed means we tried and could not,
        and only one of those is somebody's own account settings.
        """
        failed = make_notification(self.user, event=EventType.OFFER_EXPIRED)
        skipped = make_notification(self.user, event=EventType.OFFER_ACCEPTED)

        record_permanent_failure(failed, "There is no way to send on PIGEON.")
        record_permanent_failure(
            skipped, "No verified destination for this channel. Nothing was sent."
        )

        self.assertEqual(failed.status, DeliveryStatus.FAILED)
        self.assertEqual(skipped.status, DeliveryStatus.SKIPPED)


class ClassificationTests(TestCase):
    def test_a_refusal_is_permanent(self):
        for text in [
            "The number is invalid",
            "Recipient blacklisted",
            "Termii rejected the message",
            "No such mailbox",
            "Destination does not exist",
            "Malformed address",
        ]:
            with self.subTest(text=text):
                self.assertIsInstance(classify(SMSDeliveryError(text)), PermanentDeliveryFailure)

    def test_being_unreachable_is_temporary(self):
        for text in [
            "Could not reach Termii: TimeoutError",
            "Termii returned 503: service unavailable",
            "connection reset by peer",
        ]:
            with self.subTest(text=text):
                self.assertIsInstance(classify(SMSDeliveryError(text)), TemporaryDeliveryFailure)

    def test_an_unrecognised_failure_is_treated_as_temporary(self):
        """The safer default.

        Retrying something final wastes a handful of attempts and then stops.
        Abandoning something transient loses the message for good.
        """
        self.assertIsInstance(classify(RuntimeError("something odd")), TemporaryDeliveryFailure)


@override_settings(SMS_BACKEND="apps.accounts.sms.locmem.LocMemSMSProvider")
class RetryTests(TestCase):
    def setUp(self):
        LocMemSMSProvider.clear()
        self.user = make_reachable()
        self.notification = make_notification(self.user)

    def test_a_temporary_failure_is_retried(self):
        with (
            patch(
                "apps.notifications.delivery._send_sms",
                side_effect=TemporaryDeliveryFailure("provider unreachable"),
            ),
            self.assertRaises(TemporaryDeliveryFailure),
        ):
            deliver_notification(str(self.notification.pk), CONTEXT)

        self.notification.refresh_from_db()

        self.assertEqual(self.notification.status, DeliveryStatus.PENDING)
        self.assertEqual(self.notification.attempts, 1)

    def test_a_permanent_failure_is_not_retried(self):
        with patch(
            "apps.notifications.delivery._send_sms",
            side_effect=PermanentDeliveryFailure("the number is invalid"),
        ):
            # Returns rather than raising: there is nothing for Celery to do with
            # a decided outcome, and raising would leave a task in the failed
            # queue that nobody should ever look at again.
            result = deliver_notification(str(self.notification.pk), CONTEXT)

        self.notification.refresh_from_db()

        self.assertEqual(result, "not deliverable")
        self.assertEqual(self.notification.status, DeliveryStatus.FAILED)

    def test_attempts_are_bounded(self):
        self.notification.attempts = MAX_ATTEMPTS - 1
        self.notification.save(update_fields=["attempts"])

        with patch(
            "apps.notifications.delivery._send_sms",
            side_effect=TemporaryDeliveryFailure("still unreachable"),
        ):
            result = deliver_notification(str(self.notification.pk), CONTEXT)

        self.notification.refresh_from_db()

        self.assertEqual(result, "gave up")
        self.assertEqual(self.notification.status, DeliveryStatus.FAILED)
        self.assertEqual(self.notification.attempts, MAX_ATTEMPTS)

    def test_an_exhausted_message_carries_no_provider_text(self):
        """An operator needs to know it did not arrive, not what a vendor said."""
        self.notification.attempts = MAX_ATTEMPTS - 1
        self.notification.save(update_fields=["attempts"])

        with patch(
            "apps.notifications.delivery._send_sms",
            side_effect=TemporaryDeliveryFailure("Termii returned 500: api_key=live_abc123"),
        ):
            deliver_notification(str(self.notification.pk), CONTEXT)

        self.notification.refresh_from_db()

        self.assertNotIn("live_abc123", self.notification.failure_reason)

    def test_a_provider_raising_something_unexpected_does_not_escape(self):
        """It must fail on our terms rather than Celery's default ones."""
        with (
            patch.object(LocMemSMSProvider, "send", side_effect=RuntimeError("boom")),
            self.assertRaises(TemporaryDeliveryFailure),
        ):
            deliver_notification(str(self.notification.pk), CONTEXT)


@override_settings(SMS_BACKEND="apps.accounts.sms.locmem.LocMemSMSProvider")
class IdempotencyTests(TestCase):
    """Sending is an external write, so the task must be safe run twice."""

    def setUp(self):
        LocMemSMSProvider.clear()
        self.user = make_reachable()
        self.notification = make_notification(self.user)

    def test_a_redelivered_task_sends_nothing(self):
        deliver_notification(str(self.notification.pk), CONTEXT)
        result = deliver_notification(str(self.notification.pk), CONTEXT)

        self.assertEqual(result, "already sent")
        self.assertEqual(len(LocMemSMSProvider.messages), 1)

    def test_a_failed_message_is_not_resurrected_by_a_replay(self):
        self.notification.mark_failed("the number is invalid")

        result = deliver_notification(str(self.notification.pk), CONTEXT)

        self.assertEqual(result, "already failed")
        self.assertEqual(LocMemSMSProvider.messages, [])

    def test_a_skipped_message_is_not_retried_by_a_replay(self):
        self.notification.mark_skipped("no verified destination")

        result = deliver_notification(str(self.notification.pk), CONTEXT)

        self.assertEqual(result, "already skipped")

    def test_a_task_for_a_row_that_is_gone_does_nothing(self):
        notification_id = str(self.notification.pk)
        self.notification.delete()

        self.assertEqual(deliver_notification(notification_id, CONTEXT), "gone")


@override_settings(SMS_BACKEND="apps.accounts.sms.locmem.LocMemSMSProvider")
class RecipientIsolationTests(TestCase):
    def setUp(self):
        LocMemSMSProvider.clear()

    def test_a_message_goes_only_to_its_own_recipient(self):
        intended = make_reachable("intended")
        bystander = make_reachable("bystander")
        notification = make_notification(intended)

        deliver_notification(str(notification.pk), CONTEXT)

        sent_to = {message.phone for message in LocMemSMSProvider.messages}

        self.assertEqual(sent_to, {intended.phone})
        self.assertNotIn(bystander.phone, sent_to)

    def test_deleting_a_recipient_takes_their_notifications_with_them(self):
        user = make_reachable()
        make_notification(user)

        user.delete()

        self.assertEqual(Notification.objects.count(), 0)
