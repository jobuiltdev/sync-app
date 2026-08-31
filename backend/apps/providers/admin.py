"""Reviewing providers.

Every action here calls a domain service. Nothing in this module assigns a status
field, which matters more than it looks: an admin that writes
`verification_status = "APPROVED"` directly is a second implementation of the
lifecycle, and the second implementation is the one that forgets the rule about
all three checks passing.

The attempt list is read-only for the same reason. A reviewer decides through the
two actions; they do not edit outcomes, references or timestamps, because those
are a record of what a vendor said rather than an opinion.
"""

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.common.exceptions import APIError
from apps.providers.models import ProviderProfile, ProviderService, ProviderServiceArea
from apps.providers.services import approve, reinstate, reject, suspend
from apps.providers.verification import ProviderVerification

#: Shown on the inline, and every one of them read-only. Declared once, and as a
#: tuple: `fields` and `readonly_fields` accept different shapes, and a tuple is
#: assignable to both where a list is not.
ATTEMPT_INLINE_FIELDS: tuple[str, ...] = (
    "created_at",
    "status",
    "identity_check_status",
    "face_match_status",
    "liveness_status",
    "identity_vendor",
    "identity_reference",
    "masked_identifier",
    "rejection_code",
    "reviewed_by",
    "reviewed_at",
    "review_note",
)


class ProviderVerificationInline(admin.TabularInline):
    """Every attempt this provider has made, on the profile page.

    Read-only. A reviewer needs the history in front of them when deciding, and
    nobody needs to edit it.
    """

    model = ProviderVerification
    extra = 0
    can_delete = False
    fields = ATTEMPT_INLINE_FIELDS
    readonly_fields = ATTEMPT_INLINE_FIELDS
    ordering = ["-created_at"]

    def has_add_permission(self, request: HttpRequest, obj=None) -> bool:
        return False


@admin.register(ProviderProfile)
class ProviderProfileAdmin(admin.ModelAdmin):
    list_display = [
        "display_name",
        "provider_type",
        "verification_status",
        "is_accepting_jobs",
        "created_at",
    ]
    list_filter = ["verification_status", "provider_type", "is_accepting_jobs"]
    search_fields = ["display_name", "business_name", "user__email"]
    # Adjudicated through the actions below, never typed into a field.
    readonly_fields = ["verification_status", "created_at", "updated_at"]
    inlines = [ProviderVerificationInline]
    actions = ["suspend_provider", "reinstate_provider"]

    @admin.action(description="Suspend (stops offers, keeps the record)")
    def suspend_provider(self, request: HttpRequest, queryset: QuerySet) -> None:
        _run_over(self, request, queryset, suspend, "Suspended")

    @admin.action(description="Reinstate (they turn themselves back on)")
    def reinstate_provider(self, request: HttpRequest, queryset: QuerySet) -> None:
        _run_over(self, request, queryset, reinstate, "Reinstated")


@admin.register(ProviderVerification)
class ProviderVerificationAdmin(admin.ModelAdmin):
    """The review queue.

    Filtered to what is waiting by default, because a reviewer opening this page
    wants the work rather than the archive.
    """

    list_display = [
        "provider",
        "status",
        "identity_check_status",
        "face_match_status",
        "liveness_status",
        "submitted_at",
        "reviewed_at",
    ]
    list_filter = ["status", "identity_check_status", "face_match_status", "liveness_status"]
    search_fields = [
        "provider__display_name",
        "provider__user__email",
        "identity_reference",
        "masked_identifier",
    ]
    ordering = ["-created_at"]
    actions = ["approve_attempt", "reject_attempt"]

    # A record of what happened, not a form. Every field, including the review
    # note, is written by a service.
    def get_readonly_fields(self, request: HttpRequest, obj=None) -> list[str]:
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Attempts are created by providers. One conjured here would have no
        # consent record behind it.
        return False

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        # The history is the point. Deleting a rejection is deleting the answer to
        # "what did we know and when".
        return False

    @admin.action(description="Approve (this provider may take work)")
    def approve_attempt(self, request: HttpRequest, queryset: QuerySet) -> None:
        done, failed = 0, 0
        for attempt in queryset.select_related("provider"):
            try:
                approve(attempt, reviewer=request.user)
                done += 1
            except (APIError, ValidationError) as exc:
                failed += 1
                self.message_user(request, f"{attempt.provider}: {_reason(exc)}", messages.ERROR)
        if done:
            self.message_user(request, f"Approved {done}.", messages.SUCCESS)
        if failed:
            self.message_user(request, f"{failed} could not be approved.", messages.WARNING)

    @admin.action(description="Reject (needs a reason in the note first)")
    def reject_attempt(self, request: HttpRequest, queryset: QuerySet) -> None:
        done, failed = 0, 0
        for attempt in queryset.select_related("provider"):
            note = attempt.review_note.strip()
            if not note:
                failed += 1
                self.message_user(
                    request,
                    f"{attempt.provider}: add a review note explaining what to fix, "
                    "then reject. A provider cannot act on a rejection with no reason.",
                    messages.ERROR,
                )
                continue
            try:
                reject(attempt, reviewer=request.user, note=note)
                done += 1
            except (APIError, ValidationError) as exc:
                failed += 1
                self.message_user(request, f"{attempt.provider}: {_reason(exc)}", messages.ERROR)
        if done:
            self.message_user(request, f"Rejected {done}.", messages.SUCCESS)
        if failed:
            self.message_user(request, f"{failed} could not be rejected.", messages.WARNING)


def _reason(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    return str(detail or exc)


def _run_over(
    model_admin: admin.ModelAdmin,
    request: HttpRequest,
    queryset: QuerySet,
    action,
    verb: str,
) -> None:
    done, failed = 0, 0
    for profile in queryset:
        try:
            action(profile, reviewer=request.user)
            done += 1
        except (APIError, ValidationError) as exc:
            failed += 1
            model_admin.message_user(request, f"{profile}: {_reason(exc)}", messages.ERROR)
    if done:
        model_admin.message_user(request, f"{verb} {done}.", messages.SUCCESS)
    if failed:
        model_admin.message_user(request, f"{failed} unchanged.", messages.WARNING)


admin.site.register(ProviderService)
admin.site.register(ProviderServiceArea)
