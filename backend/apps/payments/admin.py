"""Operations view of the money, and the only place a payout is moved forward.

The transitions a provider must never make are here rather than on any endpoint.
They run through the same `services.transition_payout` an eventual transfer
adapter will call, so the lifecycle is enforced identically whether a person or a
program is doing it.

Every financial field is read only. Settlements are immutable by design, and an
admin able to retype an amount would make that design a matter of trust rather
than of fact.
"""

from django.contrib import admin, messages
from django.http import HttpRequest

from apps.payments import services
from apps.payments.destinations import PayoutDestination
from apps.payments.errors import PayoutNotActionable
from apps.payments.payouts import PayoutRequest
from apps.payments.settlements import BookingSettlement


@admin.register(BookingSettlement)
class BookingSettlementAdmin(admin.ModelAdmin):
    """Read only, in full.

    A settlement is written once by the domain and never edited, so there is no
    add form and no change form here either. Correcting one is a compensating
    record, which is a decision for the milestone that introduces disputes.
    """

    ordering = ["-created_at"]
    list_display = [
        "booking",
        "provider",
        "gross_amount_kobo",
        "commission_amount_kobo",
        "provider_amount_kobo",
        "currency",
        "status",
        "created_at",
    ]
    list_filter = ["status", "currency", "created_at"]
    search_fields = ["booking__reference", "provider__display_name"]
    readonly_fields = [
        "id",
        "booking",
        "provider",
        "gross_amount_kobo",
        "commission_amount_kobo",
        "provider_amount_kobo",
        "commission_rate_bps",
        "currency",
        "status",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(PayoutRequest)
class PayoutRequestAdmin(admin.ModelAdmin):
    """Payouts, moved by named actions rather than by editing a status field.

    The status is read only and the moves are admin actions, which is the same
    arrangement the booking lifecycle uses: nothing anywhere assigns a status
    directly, so the transition table is the whole truth about how a payout moves.
    """

    ordering = ["-created_at"]
    list_display = ["provider", "amount_kobo", "currency", "status", "requested_at", "processed_at"]
    list_filter = ["status", "currency", "requested_at"]
    search_fields = ["provider__display_name", "provider__user__email"]
    readonly_fields = [
        "id",
        "provider",
        "amount_kobo",
        "currency",
        "status",
        "requested_at",
        "processed_at",
        "failure_reason",
        "idempotency_key",
        "created_at",
        "updated_at",
    ]
    actions = ["start_processing", "mark_paid", "mark_failed"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        # A payout is something a provider asks for. An admin creating one would
        # be a transfer with nobody having requested it.
        return False

    def _apply(self, request: HttpRequest, queryset, move, description: str) -> None:
        moved = 0
        for payout in queryset:
            try:
                move(payout)
                moved += 1
            except PayoutNotActionable as exc:
                self.message_user(request, f"{payout}: {exc.detail}", level=messages.WARNING)

        if moved:
            self.message_user(request, f"{moved} payout(s) {description}.", level=messages.SUCCESS)

    @admin.action(description="Start processing")
    def start_processing(self, request: HttpRequest, queryset) -> None:
        self._apply(request, queryset, services.start_processing, "moved to processing")

    @admin.action(description="Mark as paid")
    def mark_paid(self, request: HttpRequest, queryset) -> None:
        self._apply(request, queryset, services.mark_paid, "marked paid")

    @admin.action(description="Mark as failed")
    def mark_failed(self, request: HttpRequest, queryset) -> None:
        self._apply(
            request,
            queryset,
            lambda payout: services.mark_failed(payout, reason="Marked failed by an operator"),
            "marked failed",
        )


@admin.register(PayoutDestination)
class PayoutDestinationAdmin(admin.ModelAdmin):
    """Where providers are paid.

    The account number is not here because it is not anywhere. What is stored is a
    hash and the last four digits, and neither is editable: a destination is
    changed by its owner, through the API, not by an operator typing into a form.
    """

    ordering = ["-created_at"]
    list_display = ["provider", "bank_name", "account_name", "account_number_last4", "is_active"]
    list_filter = ["is_active", "bank_name"]
    search_fields = ["provider__display_name", "account_name", "bank_name"]
    readonly_fields = [
        "id",
        "provider",
        "bank_code",
        "bank_name",
        "account_name",
        "account_number_last4",
        "provider_reference",
        "created_at",
        "updated_at",
    ]
    fields = [*readonly_fields, "is_active"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
