from django.conf import settings
from django.db import models

from apps.common.models import BaseModel
from apps.common.nigeria import NigerianState


class Address(BaseModel):
    """Somewhere a service happens.

    Deliberately landmark-first. Street addresses across much of Nigeria are
    incomplete, unsigned or unknown to the rider, and a landmark plus a phone call
    is how people actually find each other. `landmark` is therefore required, while
    coordinates are optional and currently only stored.

    Coordinates exist now so that dispatch and matching can filter on distance
    later without a data backfill against addresses that were never captured with
    them. Nothing reads them in this milestone.
    """

    class Label(models.TextChoices):
        HOME = "HOME", "Home"
        WORK = "WORK", "Work"
        OTHER = "OTHER", "Other"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
    )

    label = models.CharField(max_length=10, choices=Label.choices, default=Label.HOME)
    street_address = models.CharField(max_length=255)
    landmark = models.CharField(
        max_length=255,
        help_text="A nearby place the provider will recognise. Often more useful than the street.",
    )
    area = models.CharField(max_length=120, blank=True, help_text="Neighbourhood or estate.")
    lga = models.CharField(max_length=120, blank=True, help_text="Local government area.")
    state = models.CharField(max_length=20, choices=NigerianState.choices)

    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    directions_note = models.TextField(blank=True)

    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "accounts_address"
        verbose_name_plural = "addresses"
        ordering = ["-is_default", "-created_at"]
        constraints = [
            # A partial unique index rather than application logic, so two requests
            # setting a default at the same time cannot both win.
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default=True),
                name="accounts_address_one_default_per_user",
            ),
            models.CheckConstraint(
                condition=~models.Q(street_address=""),
                name="accounts_address_street_not_empty",
            ),
            models.CheckConstraint(
                condition=~models.Q(landmark=""),
                name="accounts_address_landmark_not_empty",
            ),
            # Coordinates are meaningless one at a time.
            models.CheckConstraint(
                condition=(
                    models.Q(latitude__isnull=True, longitude__isnull=True)
                    | models.Q(latitude__isnull=False, longitude__isnull=False)
                ),
                name="accounts_address_coordinates_paired",
            ),
        ]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.street_address}, {self.get_state_display()}"
