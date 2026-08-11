from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Operations view of an account.

    Verification timestamps are read-only here. They are evidence that something was
    proven at a point in time, and an admin being able to type one in by hand would
    make them worthless as an audit trail.
    """

    ordering = ["-created_at"]
    list_display = ["email", "phone", "full_name", "is_active", "is_staff", "created_at"]
    list_filter = ["is_active", "is_staff", "is_superuser", "created_at"]
    search_fields = ["email", "phone", "first_name", "last_name"]
    readonly_fields = [
        "id",
        "created_at",
        "updated_at",
        "last_login",
        "last_active_at",
        "email_verified_at",
        "phone_verified_at",
    ]

    fieldsets = [
        (None, {"fields": ["id", "email", "password"]}),
        ("Personal", {"fields": ["first_name", "last_name", "phone"]}),
        ("Verification", {"fields": ["email_verified_at", "phone_verified_at"]}),
        (
            "Permissions",
            {"fields": ["is_active", "is_staff", "is_superuser", "groups", "user_permissions"]},
        ),
        ("Activity", {"fields": ["last_login", "last_active_at", "created_at", "updated_at"]}),
    ]

    add_fieldsets = [
        (
            None,
            {
                "classes": ["wide"],
                "fields": ["email", "phone", "first_name", "last_name", "password1", "password2"],
            },
        ),
    ]
