"""The catalog seed.

Two of these matter more than the rest. The first asserts that every vertical
with a registered spec also has something bookable, which is the gap that let
errands and beauty exist in code for four milestones without ever appearing in
the app. The second asserts the seed is safe to run against a database with
bookings in it.
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.catalog.management.commands.seed_catalog import CATALOG
from apps.catalog.models import Service, ServiceCategory
from apps.catalog.specs import registry


def seed(**options) -> str:
    out = StringIO()
    call_command("seed_catalog", stdout=out, **options)
    return out.getvalue()


class SeedCatalogTests(TestCase):
    def test_it_creates_every_category(self):
        seed()

        self.assertEqual(
            list(
                ServiceCategory.objects.filter(is_active=True)
                .order_by("sort_order")
                .values_list("slug", flat=True)
            ),
            [category.slug for category in CATALOG],
        )

    def test_every_registered_spec_is_bookable(self):
        """The gap this file exists for.

        A spec with no service is a vertical the product advertises and cannot
        sell. Errands and beauty were both in that state until M9.
        """
        seed()

        bookable = set(Service.objects.filter(is_active=True).values_list("spec_key", flat=True))

        self.assertEqual(bookable, set(registry.registered_keys()))

    def test_every_service_names_a_registered_spec(self):
        seed()

        for service in Service.objects.all():
            with self.subTest(service=service.slug):
                self.assertTrue(registry.is_registered(service.spec_key))

    def test_every_category_ships_an_icon(self):
        """Blank icon keys fall back to a generic glyph, so a catalog seeded
        without them renders six identical rows."""
        seed()

        for category in ServiceCategory.objects.all():
            with self.subTest(category=category.slug):
                self.assertNotEqual(category.icon_key, "")

    def test_every_service_has_a_summary(self):
        seed()

        for service in Service.objects.all():
            with self.subTest(service=service.slug):
                self.assertNotEqual(service.summary, "")

    def test_running_it_twice_changes_nothing(self):
        seed()
        before = ServiceCategory.objects.count(), Service.objects.count()

        seed()

        self.assertEqual((ServiceCategory.objects.count(), Service.objects.count()), before)

    def test_it_updates_rather_than_duplicating(self):
        seed()
        service = Service.objects.get(slug="standard-clean")
        service.summary = "edited by hand"
        service.save(update_fields=["summary"])

        seed()
        service.refresh_from_db()

        self.assertNotEqual(service.summary, "edited by hand")
        self.assertEqual(Service.objects.filter(slug="standard-clean").count(), 1)

    def test_prune_deactivates_rather_than_deleting(self):
        """A booking holds a foreign key to its service. Deleting one would take
        a customer's history with it."""
        seed()
        stale = Service.objects.create(
            category=ServiceCategory.objects.first(),
            slug="withdrawn-service",
            name="Withdrawn",
            spec_key="cleaning",
        )

        seed(prune=True)
        stale.refresh_from_db()

        self.assertFalse(stale.is_active)
        self.assertTrue(Service.objects.filter(pk=stale.pk).exists())

    def test_prune_leaves_seeded_services_active(self):
        seed()
        seed(prune=True)

        self.assertEqual(
            Service.objects.filter(is_active=False).count(),
            0,
        )

    def test_no_service_names_a_single_trade_it_does_not_own(self):
        """`Plumbing Callout` named one trade while its form asked for four, so a
        customer with a broken socket had no row to tap."""
        seed()

        home = Service.objects.get(spec_key="home_services", is_active=True)

        self.assertNotIn("plumbing", home.name.lower())
        self.assertEqual(home.summary, "Home services across Lagos.")


class HomeServicesTradeTests(TestCase):
    def test_air_conditioning_and_appliances_are_electrical(self):
        """They were separate options, which asked the customer to categorise
        their own fault before we would take it."""
        from apps.catalog.specs.verticals import HomeServicesDetailsSerializer

        choices = HomeServicesDetailsSerializer().fields["trade"].choices

        self.assertEqual(set(choices), {"PLUMBING", "ELECTRICAL", "CARPENTRY", "PAINTING"})

    def test_the_remaining_trades_still_validate(self):
        from apps.catalog.specs.verticals import HomeServicesDetailsSerializer

        for trade in ["PLUMBING", "ELECTRICAL", "CARPENTRY", "PAINTING"]:
            with self.subTest(trade=trade):
                serializer = HomeServicesDetailsSerializer(
                    data={"trade": trade, "problem_description": "The socket sparks."}
                )
                self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_a_withdrawn_trade_is_refused(self):
        from apps.catalog.specs.verticals import HomeServicesDetailsSerializer

        serializer = HomeServicesDetailsSerializer(
            data={"trade": "AC", "problem_description": "Not cooling."}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("trade", serializer.errors)
