import uuid
from typing import ClassVar

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from apps.accounts.identity import normalize_email, normalize_phone


class UserManager(BaseUserManager["User"]):
    """Creates users through the same normalisation path as the API.

    Everything that makes a user, the API, the admin, `createsuperuser`, and test
    factories, goes through here, so no route into the database can skip it.
    """

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra: object) -> User:
        if not email:
            raise ValueError("Users must have an email address.")

        phone = extra.pop("phone", None)
        user = self.model(
            email=normalize_email(email),
            phone=normalize_phone(str(phone)) if phone else None,
            **extra,
        )
        # set_password hashes; set_unusable_password marks the account as reachable
        # only through a future social identity, which M1 does not create yet.
        if password is None:
            user.set_unusable_password()
        else:
            user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: object) -> User:
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: object) -> User:
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)

        if extra.get("is_staff") is not True:
            raise ValueError("Superusers must have is_staff=True.")
        if extra.get("is_superuser") is not True:
            raise ValueError("Superusers must have is_superuser=True.")

        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """A person on Sync, whether they book services, provide them, or both.

    Roles are not a field. A customer and a provider are the same account with
    different profiles attached, because in this market one person is regularly
    both, and a role enum would force them into two logins.

    Verification is deliberately separate from authentication: an account is usable
    the moment it exists, and `email_verified_at` / `phone_verified_at` record what
    has since been proven. They are timestamps rather than booleans so there is an
    audit trail of when each was established. The workflows that set them, and the
    policy deciding what they gate, both arrive later.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(unique=True)
    # Optional at registration, so signing up needs one identifier rather than two.
    # Null rather than blank when absent: Postgres allows many NULLs under a unique
    # constraint but only one empty string, which would let the first user without a
    # phone block every other one.
    phone = models.CharField(max_length=20, unique=True, null=True, blank=True)

    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)

    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_active_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    # Email is already the username field; listing it again here would make
    # createsuperuser prompt for it twice.
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        db_table = "accounts_user"
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(email=""),
                name="accounts_user_email_not_empty",
            ),
            # Guards the NULL-versus-empty-string rule above at the database level,
            # so a direct write cannot reintroduce the collision.
            models.CheckConstraint(
                condition=models.Q(phone__isnull=True) | ~models.Q(phone=""),
                name="accounts_user_phone_not_empty",
            ),
        ]

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        super().clean()
        self.email = normalize_email(self.email)
        if self.phone:
            self.phone = normalize_phone(self.phone)

    @property
    def is_email_verified(self) -> bool:
        return self.email_verified_at is not None

    @property
    def is_phone_verified(self) -> bool:
        return self.phone_verified_at is not None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def touch_last_active(self) -> None:
        self.last_active_at = timezone.now()
        self.save(update_fields=["last_active_at", "updated_at"])
