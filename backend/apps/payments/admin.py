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
from apps.payments.anomalies import FinancialAnomaly
from apps.payments.destinations import PayoutDestination
from apps.payments.errors import PayoutNotActionable
from apps.payments.intents import PaymentIntent
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
    list_display = [
        "provider",
        "amount_kobo",
        "currency",
        "status",
        "transfer_reference",
        "requested_at",
        "processed_at",
    ]
    list_filter = ["status", "currency", "transfer_provider", "requested_at"]
    search_fields = [
        "provider__display_name",
        "provider__user__email",
        "transfer_reference",
        "gateway_reference",
    ]
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
        "transfer_reference",
        "transfer_provider",
        "gateway_reference",
        "gateway_status",
        "submitted_at",
        "reconciled_at",
        "created_at",
        "updated_at",
    ]
    actions = ["send_payout", "reconcile", "mark_paid", "mark_failed"]

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

    @admin.action(description="Send the money (submits a real transfer)")
    def send_payout(self, request: HttpRequest, queryset) -> None:
        """Releases a requested payout to the transfer provider.

        The one operator action that moves money, which is why it is worded to
        say so. It queues the same task the rest of the system would use rather
        than doing the work in the request, so an operator clicking twice cannot
        submit twice: the task refuses a payout that already carries a transfer
        reference, exactly as it would for any other caller.

        A payout is still something a provider asks for. This releases what they
        asked for; nothing here creates a payout, and there is no automatic
        payout anywhere in the system.
        """
        from apps.payments.execution import PayoutAlreadySubmitted
        from apps.payments.tasks import execute_payout_task

        queued = 0
        for payout in queryset:
            if payout.is_submitted:
                self.message_user(
                    request,
                    f"{payout}: a transfer was already submitted. Use Reconcile instead.",
                    level=messages.WARNING,
                )
                continue
            if payout.status != "REQUESTED":
                self.message_user(
                    request,
                    f"{payout}: only a requested payout can be sent.",
                    level=messages.WARNING,
                )
                continue

            try:
                execute_payout_task.delay(str(payout.pk))
                queued += 1
            except PayoutAlreadySubmitted:
                self.message_user(request, f"{payout}: already submitted.", level=messages.WARNING)

        if queued:
            self.message_user(
                request, f"{queued} payout(s) queued for transfer.", level=messages.SUCCESS
            )

    @admin.action(description="Ask the provider what happened")
    def reconcile(self, request: HttpRequest, queryset) -> None:
        """Resolves a submitted payout by asking the provider.

        The correct response to a payout stuck in processing, and the only safe
        one: it asks rather than resends.
        """
        from apps.payments.execution import reconcile_payout

        for payout in queryset:
            if not payout.needs_reconciliation:
                self.message_user(
                    request,
                    f"{payout}: nothing to reconcile.",
                    level=messages.WARNING,
                )
                continue

            resolved = reconcile_payout(payout.pk)
            self.message_user(
                request,
                f"{payout}: the provider says {resolved.gateway_status or 'nothing yet'} "
                f"({resolved.status}).",
                level=messages.SUCCESS,
            )

    @admin.action(description="Mark as paid (only if the provider confirms it)")
    def mark_paid(self, request: HttpRequest, queryset) -> None:
        """The manual override, for a transfer confirmed outside this system.

        Goes through the same lifecycle function everything else does, so it
        cannot skip a state or resurrect a terminal payout. It exists because a
        provider dashboard sometimes knows something an API does not.
        """
        self._apply(request, queryset, services.mark_paid, "marked paid")

    @admin.action(description="Mark as failed")
    def mark_failed(self, request: HttpRequest, queryset) -> None:
        self._apply(
            request,
            queryset,
            lambda payout: services.mark_failed(payout, reason="Marked failed by an operator"),
            "marked failed",
        )


@admin.register(FinancialAnomaly)
class FinancialAnomalyAdmin(admin.ModelAdmin):
    """What the consistency sweep found and could not safely fix itself.

    The list an operator should look at first in the morning. Everything here is
    read only except closing one: the anomaly is evidence, and editing evidence
    is how the cause of a problem gets lost.
    """

    ordering = ["-last_seen_at"]
    list_display = [
        "kind",
        "classification",
        "subject_type",
        "subject_reference",
        "times_seen",
        "last_seen_at",
        "resolved_at",
    ]
    list_filter = ["classification", "kind", "resolved_at"]
    search_fields = ["subject_reference", "detail"]
    readonly_fields = [
        "id",
        "kind",
        "classification",
        "subject_type",
        "subject_id",
        "subject_reference",
        "detail",
        "first_seen_at",
        "last_seen_at",
        "times_seen",
        "created_at",
        "updated_at",
    ]
    fields = [*readonly_fields, "resolved_at", "resolution"]
    actions = ["close"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        # Anomalies are found, not filed.
        return False

    @admin.action(description="Close as dealt with")
    def close(self, request: HttpRequest, queryset) -> None:
        closed = 0
        for anomaly in queryset.filter(resolved_at__isnull=True):
            anomaly.resolve(f"Closed by {request.user}")
            closed += 1

        self.message_user(request, f"{closed} anomaly(ies) closed.", level=messages.SUCCESS)


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    """Payments, read only, with the references support conversations need.

    No actions that change a status. A payment moves only on what the provider
    says, and an admin able to type SUCCESSFUL onto one would be exactly the hole
    the verification path exists to close. Reconciling one is available from the
    payment itself through the task, not from here.
    """

    ordering = ["-created_at"]
    list_display = [
        "reference",
        "booking",
        "amount_kobo",
        "currency",
        "status",
        "gateway",
        "method",
        "created_at",
    ]
    list_filter = ["status", "gateway", "currency", "created_at"]
    search_fields = ["reference", "gateway_reference", "booking__reference", "customer__email"]
    readonly_fields = [
        "id",
        "reference",
        "booking",
        "customer",
        "amount_kobo",
        "currency",
        "status",
        "gateway",
        "gateway_reference",
        "gateway_status",
        "method",
        "authorization_url",
        "idempotency_key",
        "paid_at",
        "failed_at",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


@admin.register(PayoutDestination)
class PayoutDestinationAdmin(admin.ModelAdmin):
    """Where providers are paid.

    The account number is not here because it is not anywhere. What is stored is a
    hash and the last four digits, and neither is editable: a destination is
    changed by its owner, through the API, not by an operator typing into a form.
    """

    ordering = ["-created_at"]
    list_display = [
        "provider",
        "bank_name",
        "account_name",
        "account_number_last4",
        "verification_status",
        "is_active",
    ]
    list_filter = ["verification_status", "is_active", "bank_name"]
    search_fields = ["provider__display_name", "account_name", "bank_name"]
    readonly_fields = [
        "id",
        "provider",
        "bank_code",
        "bank_name",
        "account_name",
        "account_number_last4",
        "verification_status",
        "resolved_account_name",
        "verified_at",
        "provider_reference",
        "created_at",
        "updated_at",
    ]
    fields = [*readonly_fields, "is_active"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
