from django.core.exceptions import ValidationError
from django.db import models

from apps.catalog import specs
from apps.common.models import BaseModel


class ServiceCategory(BaseModel):
    """A grouping customers browse by, such as Cleaning or Dispatch.

    A category carries no behaviour. It exists so the home screen has something to
    lay out and so a service belongs somewhere; the behavioural differences between
    verticals live in the spec, not here.
    """

    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    icon_key = models.CharField(
        max_length=60,
        blank=True,
        help_text="Names an icon the app ships. Not a URL, so the app stays offline-capable.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_service_category"
        verbose_name_plural = "service categories"
        ordering = ["sort_order", "name"]
        indexes = [models.Index(fields=["is_active", "sort_order"])]

    def __str__(self) -> str:
        return self.name


class BookingMode(models.TextChoices):
    ON_DEMAND = "ON_DEMAND", "On demand"
    SCHEDULED = "SCHEDULED", "Scheduled"
    BOTH = "BOTH", "On demand or scheduled"


class PricingModel(models.TextChoices):
    """How a price is arrived at.

    Stored on the service because it decides how the app presents a price before a
    quote exists: a fixed price is shown as a price, a distance price as "from", and
    a quote-on-site service as no price at all. The calculation itself lands in M3.
    """

    FIXED = "FIXED", "Fixed price"
    PER_HOUR = "PER_HOUR", "Per hour"
    PER_ITEM = "PER_ITEM", "Per item"
    DISTANCE = "DISTANCE", "By distance"
    QUOTE_ON_SITE = "QUOTE_ON_SITE", "Quoted after inspection"


class Service(BaseModel):
    """A specific thing a customer can request and a provider can offer.

    `spec_key` is the join between a database row and the code that knows what a
    request for it must contain. It is validated against the registry rather than
    constrained by choices, because a choices list would put every spec addition
    into a migration for no benefit.
    """

    category = models.ForeignKey(
        ServiceCategory,
        # A category holding services must not disappear from under them.
        on_delete=models.PROTECT,
        related_name="services",
    )

    slug = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=140)
    summary = models.CharField(max_length=255, blank=True, help_text="One line, shown in lists.")
    description = models.TextField(blank=True)

    spec_key = models.CharField(max_length=60)

    booking_modes = models.CharField(
        max_length=20, choices=BookingMode.choices, default=BookingMode.SCHEDULED
    )
    pricing_model = models.CharField(
        max_length=20, choices=PricingModel.choices, default=PricingModel.FIXED
    )
    #: Money is an integer number of kobo everywhere. The lowest price a customer
    #: could pay, used for the "from" figure while browsing.
    base_price_kobo = models.BigIntegerField(default=0)

    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_service"
        ordering = ["sort_order", "name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(base_price_kobo__gte=0),
                name="catalog_service_base_price_not_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["is_active", "sort_order"]),
            models.Index(fields=["category", "is_active"]),
        ]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()
        if self.spec_key and not specs.is_registered(self.spec_key):
            raise ValidationError(
                {
                    "spec_key": (
                        f"No service spec is registered for {self.spec_key!r}. "
                        f"Known specs: {', '.join(specs.registered_keys())}."
                    )
                }
            )

    @property
    def spec(self) -> specs.ServiceSpec:
        return specs.get(self.spec_key)


class ServiceOption(BaseModel):
    """An add-on a customer can choose, such as ironing included.

    Separate from the spec's details because an option is priced and configurable by
    operations, while a spec field is structural and belongs in code.
    """

    class Kind(models.TextChoices):
        BOOLEAN = "BOOLEAN", "Yes or no"
        QUANTITY = "QUANTITY", "Quantity"
        CHOICE = "CHOICE", "One of several"

    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="options")
    key = models.SlugField(max_length=60)
    label = models.CharField(max_length=140)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.BOOLEAN)
    price_delta_kobo = models.BigIntegerField(default=0)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "catalog_service_option"
        ordering = ["sort_order", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["service", "key"], name="catalog_option_unique_key_per_service"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.service.name}: {self.label}"
