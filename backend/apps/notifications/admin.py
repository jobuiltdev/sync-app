"""The answer to "did they ever get told".

Read only, in full. A notification is a record of something that already happened
or already failed to, and editing one would turn an audit trail into a note. There
is no resend action either: re-sending needs the context that deliberately was not
stored, and a button that silently sends a message rendered from nothing is worse
than no button.

The list carries no message text, because none is stored. What it shows is who,
what event, which channel, and what became of it, which is what somebody
answering a support question actually needs.
"""

from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    ordering = ["-created_at"]
    list_display = [
        "created_at",
        "event_type",
        "channel",
        "recipient",
        "subject_reference",
        "status",
        "attempts",
    ]
    list_filter = ["status", "channel", "event_type", "created_at"]
    # By reference and by the recipient's own identifiers. Not by message text,
    # which does not exist, and not by destination, which would make this a
    # lookup table of everybody's phone number.
    search_fields = [
        "subject_reference",
        "recipient__phone",
        "recipient__email",
    ]
    readonly_fields = [
        "id",
        "event_type",
        "channel",
        "recipient",
        "subject_type",
        "subject_id",
        "subject_reference",
        "status",
        "dedupe_key",
        "attempts",
        "failure_reason",
        "queued_at",
        "delivered_at",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request, obj=None) -> bool:
        # Notifications come from domain events. One typed in here would be a
        # message about something that did not happen.
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
