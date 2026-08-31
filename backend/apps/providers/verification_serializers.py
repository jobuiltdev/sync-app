"""What a provider is allowed to see and send about their own verification.

Every field on the attempt model that a provider could not legitimately set is
read-only here, and the ones a reviewer owns are not exposed for writing at all.
That is stated twice on purpose: once in `read_only_fields`, and once by the views
never passing request data into an update.

Nothing in this module can serialise an identifier. `masked_identifier` is four
characters by database constraint, and there is no field carrying a token, a
portrait or a vendor payload because the model has nowhere to keep one.
"""

from rest_framework import serializers

from apps.providers.services import ChecklistItem, VerificationChecklist
from apps.providers.verification import ProviderVerification


class ChecklistItemSerializer(serializers.Serializer):
    """Declared for the schema; `to_representation` below builds the payload."""

    key = serializers.CharField(read_only=True)
    # `label` is also the name DRF's own `Field` uses for a form label, so the
    # stubs see a conflict that is not one. Same situation, and same suppression,
    # as the address label in `bookings.serializers`.
    label = serializers.CharField(read_only=True)  # type: ignore[assignment]
    complete = serializers.BooleanField(read_only=True)
    action = serializers.CharField(read_only=True, allow_blank=True)

    def to_representation(self, instance: ChecklistItem) -> dict:
        return {
            "key": instance.key,
            "label": instance.label,
            "complete": instance.complete,
            "action": instance.action,
        }


class VerificationChecklistSerializer(serializers.Serializer):
    """The server's answer to "where am I up to", computed rather than inferred."""

    items = ChecklistItemSerializer(many=True, read_only=True)
    complete = serializers.BooleanField(read_only=True)
    can_start_identity_check = serializers.BooleanField(read_only=True)
    blocked_reason = serializers.CharField(read_only=True, allow_blank=True)
    verification_status = serializers.CharField(read_only=True)

    def to_representation(self, instance: VerificationChecklist) -> dict:
        return {
            "items": [ChecklistItemSerializer().to_representation(item) for item in instance.items],
            "complete": instance.complete,
            "can_start_identity_check": instance.can_start_identity_check,
            "blocked_reason": instance.blocked_reason,
            "verification_status": self.context["verification_status"],
        }


class ProviderVerificationSerializer(serializers.ModelSerializer):
    """One attempt, as much of it as a provider may see.

    The reviewer's identity is not included. A provider is entitled to the
    decision and the reason; who made it is an internal matter and publishing it
    invites people to argue with a named individual.
    """

    reviewed = serializers.SerializerMethodField()
    failed_checks = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = ProviderVerification
        fields = [
            "id",
            "status",
            "submitted_at",
            "identity_check_status",
            "face_match_status",
            "liveness_status",
            "identity_vendor",
            "identity_reference",
            "identity_method",
            "identity_checked_at",
            "masked_identifier",
            "rejection_code",
            "consent_notice_version",
            "consented_at",
            "review_note",
            "reviewed",
            "reviewed_at",
            "failed_checks",
            "created_at",
        ]
        # Every one of them. A provider posting to this endpoint cannot set an
        # outcome, a reference, a review note or a status, because there is no
        # writable field on the serializer at all.
        read_only_fields = fields

    def get_reviewed(self, attempt: ProviderVerification) -> bool:
        return attempt.reviewed_at is not None


class StartVerificationSerializer(serializers.Serializer):
    """What a provider sends to begin.

    Two fields, and neither is an identifier. `authorization_reference` is what the
    identity provider handed back after the holder consented there; it is opaque
    here, never stored, and the fake adapter refuses anything shaped like a real
    NIN so a development database cannot accumulate them.
    """

    authorization_reference = serializers.CharField(
        max_length=200,
        write_only=True,
        help_text=(
            "The reference returned by the identity provider's consent flow. "
            "Never a NIN, a BVN or any part of one."
        ),
    )
    consent = serializers.BooleanField(
        write_only=True,
        help_text="Whether the provider agreed to the identity verification notice.",
    )

    def validate_authorization_reference(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("An authorization reference is required.")
        # A last line of defence in front of every adapter, not only the fake.
        # Eleven consecutive digits is a NIN or a BVN and must never reach here.
        if any(
            stripped[index : index + 11].isdigit() for index in range(max(1, len(stripped) - 10))
        ):
            raise serializers.ValidationError(
                "That looks like a government identifier. Send the authorization "
                "reference from the consent flow, not the number itself.",
            )
        return stripped
