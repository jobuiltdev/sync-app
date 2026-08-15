"""The catalog Sync actually sells.

Until now there was no seed at all: the categories and services in the
development database were created by hand somewhere along the way, which had two
consequences. A fresh checkout had an empty catalog, so the whole discovery half
of the app rendered its empty state. And **two of the six verticals the product
advertises had specs in code but no catalog row**, so errands and beauty could
not be browsed or booked by anybody, on any environment, ever.

This is the canonical list, and it is the answer to both. It is idempotent: it
matches on slug and updates in place, so running it against a database with
bookings in it changes copy and prices without touching a single booking, and
running it twice does nothing the second time.

It never deletes. A service that is withdrawn is deactivated by hand, because a
booking holds a foreign key to the service it was made for and deleting one out
from under a year of history is not something a seed script should be able to do.

Prices are opening figures in kobo, meant to be edited in the admin once real
providers are quoting real work. They are not business rules.
"""

from dataclasses import dataclass, field

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import BookingMode, PricingModel, Service, ServiceCategory


@dataclass(frozen=True)
class SeedService:
    slug: str
    name: str
    summary: str
    spec_key: str
    pricing_model: str
    base_price_kobo: int
    booking_modes: str = BookingMode.BOTH
    description: str = ""


@dataclass(frozen=True)
class SeedCategory:
    slug: str
    name: str
    description: str
    #: Matches an icon the app ships. Left blank, every category falls back to a
    #: generic glyph, which is what the app was doing before this existed.
    icon_key: str
    services: list[SeedService] = field(default_factory=list)


#: Ordered as a customer would scan them: the errands you send somebody to do,
#: then the work done at your home, then the things you drop off.
CATALOG: list[SeedCategory] = [
    SeedCategory(
        # The slug and the spec key stay "dispatch": they are internal
        # identifiers, one of them is stamped on every booking ever made, and
        # renaming a category is a copy decision rather than a data migration.
        slug="dispatch",
        name="Courier Services",
        description="Send a package across town, same day.",
        icon_key="dispatch",
        services=[
            SeedService(
                slug="same-day-dispatch",
                name="Same Day Delivery",
                summary="Picked up and delivered across Lagos today.",
                spec_key="dispatch",
                pricing_model=PricingModel.DISTANCE,
                base_price_kobo=120_000,
                booking_modes=BookingMode.ON_DEMAND,
            ),
        ],
    ),
    SeedCategory(
        slug="errands",
        name="Errands",
        description="Shopping, pickups and queues, done for you.",
        icon_key="errands",
        services=[
            # One service rather than several. The spec already carries a task
            # list, a spending limit and whether buying is involved, so splitting
            # "shopping" from "errands" would be two rows leading to one form.
            SeedService(
                slug="shopping-and-errands",
                name="Shopping and Errands",
                summary="Market runs, pickups and queuing. You set the spending limit.",
                spec_key="errands",
                pricing_model=PricingModel.PER_HOUR,
                base_price_kobo=250_000,
                description=(
                    "Give us the list and a spending limit. We shop, queue, collect or "
                    "drop off, and account for what was spent."
                ),
            ),
        ],
    ),
    SeedCategory(
        slug="cleaning",
        name="Cleaning",
        description="Homes and offices, standard or deep.",
        icon_key="cleaning",
        services=[
            SeedService(
                slug="standard-clean",
                name="Standard Clean",
                summary="Regular upkeep for a home or office.",
                spec_key="cleaning",
                pricing_model=PricingModel.FIXED,
                base_price_kobo=1_500_000,
            ),
            SeedService(
                slug="deep-clean",
                name="Deep Clean",
                summary="Top to bottom, including the places a standard clean skips.",
                spec_key="cleaning",
                pricing_model=PricingModel.FIXED,
                base_price_kobo=3_500_000,
            ),
        ],
    ),
    SeedCategory(
        slug="home-services",
        name="Home Services",
        description="Repairs and installations by vetted tradespeople.",
        icon_key="home_services",
        services=[
            # Was "Plumbing Callout", which named one trade while the form asked
            # for four. A customer with a broken socket had no row to tap.
            SeedService(
                slug="home-services",
                name="Home Services",
                summary="Home services across Lagos.",
                spec_key="home_services",
                pricing_model=PricingModel.QUOTE_ON_SITE,
                base_price_kobo=500_000,
                description=(
                    "Plumbing, electrical, carpentry and painting. Most repairs cannot "
                    "be priced without being seen, so the visit is quoted on site."
                ),
            ),
        ],
    ),
    SeedCategory(
        slug="beauty",
        name="Beauty",
        description="Hair, nails and skin, at home or in salon.",
        icon_key="beauty",
        services=[
            # Split three ways rather than one "Beauty" row. Somebody who wants
            # their nails done is not browsing for a haircut, and a single row
            # would make them read a form to find out whether we do it.
            SeedService(
                slug="hair",
                name="Hair",
                summary="Braiding, styling, cuts and treatments.",
                spec_key="beauty",
                pricing_model=PricingModel.FIXED,
                base_price_kobo=800_000,
            ),
            SeedService(
                slug="nails",
                name="Nails",
                summary="Manicures, pedicures and extensions.",
                spec_key="beauty",
                pricing_model=PricingModel.FIXED,
                base_price_kobo=500_000,
            ),
            SeedService(
                slug="facials-and-skincare",
                name="Facials and Skincare",
                summary="Facials, cleansing and skin treatments.",
                spec_key="beauty",
                pricing_model=PricingModel.FIXED,
                base_price_kobo=700_000,
            ),
        ],
    ),
    SeedCategory(
        slug="laundry",
        name="Laundry",
        description="Washed, ironed or dry cleaned, priced per item.",
        icon_key="laundry",
        services=[
            SeedService(
                slug="wash-and-fold",
                name="Laundry",
                # The spec asks for wash type, so the service does not name one.
                # "Wash and Fold" was a service narrower than its own form.
                summary="Wash and fold, wash and iron, or dry clean.",
                spec_key="laundry",
                pricing_model=PricingModel.PER_ITEM,
                base_price_kobo=50_000,
            ),
        ],
    ),
]


class Command(BaseCommand):
    help = "Creates or updates the Sync service catalog. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--prune",
            action="store_true",
            help=(
                "Deactivate services and categories that are not in the seed. "
                "Never deletes: bookings point at services and history must survive."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        seen_categories: set[str] = set()
        seen_services: set[str] = set()
        created = updated = 0

        for order, seed in enumerate(CATALOG, start=1):
            category, was_created = ServiceCategory.objects.update_or_create(
                slug=seed.slug,
                defaults={
                    "name": seed.name,
                    "description": seed.description,
                    "icon_key": seed.icon_key,
                    "sort_order": order,
                    "is_active": True,
                },
            )
            seen_categories.add(seed.slug)
            created += was_created
            updated += not was_created

            for service_order, service in enumerate(seed.services, start=1):
                _, service_created = Service.objects.update_or_create(
                    slug=service.slug,
                    defaults={
                        "category": category,
                        "name": service.name,
                        "summary": service.summary,
                        "description": service.description,
                        "spec_key": service.spec_key,
                        "booking_modes": service.booking_modes,
                        "pricing_model": service.pricing_model,
                        "base_price_kobo": service.base_price_kobo,
                        "sort_order": service_order,
                        "is_active": True,
                    },
                )
                seen_services.add(service.slug)
                created += service_created
                updated += not service_created

        pruned = 0
        if options["prune"]:
            pruned += (
                Service.objects.filter(is_active=True)
                .exclude(slug__in=seen_services)
                .update(is_active=False)
            )
            pruned += (
                ServiceCategory.objects.filter(is_active=True)
                .exclude(slug__in=seen_categories)
                .update(is_active=False)
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Catalog seeded: {created} created, {updated} updated"
                + (f", {pruned} deactivated" if options["prune"] else "")
            )
        )
