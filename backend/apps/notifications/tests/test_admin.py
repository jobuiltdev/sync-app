"""The operations view.

Somebody answering "they say they never got told about the job" needs to see what
was attempted and what happened to it. They must not be able to change any of it,
and they must not be handed a copy of what the message said.
"""

from django.contrib.admin.sites import site
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.notifications.events import Channel, EventType
from apps.notifications.models import DeliveryStatus, Notification
from apps.notifications.tests.factories import PASSWORD, make_reachable


class NotificationAdminTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_superuser(email="ops@example.com", password=PASSWORD)
        self.client.force_login(self.staff)

        self.recipient = make_reachable()
        self.notification = Notification.objects.create(
            event_type=EventType.OFFER_RECEIVED,
            channel=Channel.SMS,
            recipient=self.recipient,
            subject_type="Offer",
            subject_reference="SY-8F3K2A",
            dedupe_key="offer:one",
        )

    def test_the_history_is_visible(self):
        response = self.client.get(reverse("admin:notifications_notification_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SY-8F3K2A")

    def test_a_failure_reason_is_visible_on_the_record(self):
        self.notification.mark_failed("The provider could not be reached in 5 attempts.")

        response = self.client.get(
            reverse("admin:notifications_notification_change", args=[self.notification.pk])
        )

        self.assertContains(response, "could not be reached")

    def test_nothing_can_be_added(self):
        """A notification typed in by hand is a message about something that

        did not happen. Every row here comes from a domain event.
        """
        admin = site._registry[Notification]

        self.assertFalse(admin.has_add_permission(None))

    def test_nothing_can_be_changed_or_deleted(self):
        admin = site._registry[Notification]

        self.assertFalse(admin.has_change_permission(None))
        self.assertFalse(admin.has_delete_permission(None))

    def test_every_field_is_read_only(self):
        admin = site._registry[Notification]
        editable = {
            field.name
            for field in Notification._meta.fields
            if field.name not in set(admin.readonly_fields)
        }

        self.assertEqual(editable, set())

    def test_the_search_does_not_expose_message_text(self):
        """There is none stored, and the search must not imply otherwise."""
        admin = site._registry[Notification]

        self.assertNotIn("failure_reason", admin.search_fields)
        self.assertNotIn("dedupe_key", admin.search_fields)

    def test_a_skipped_message_is_distinguishable_from_a_failed_one(self):
        self.notification.mark_skipped("No verified destination for this channel.")

        response = self.client.get(
            reverse("admin:notifications_notification_changelist")
            + f"?status={DeliveryStatus.SKIPPED}"
        )

        self.assertContains(response, "SY-8F3K2A")
