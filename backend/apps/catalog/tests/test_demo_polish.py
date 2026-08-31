"""The demo polish pass: one cleaning route, priced answers, and honest copy.

Grouped by the thing that could regress rather than by module. Each of these
covers a decision that is easy to undo by accident: merging two services without
losing the bookings on one, pricing an answer without inventing a number, and
asking a question in words somebody would actually say.
"""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.bookings.services import agreed_price_kobo, options_delta_kobo
from apps.catalog.models import Service, ServiceOption
from apps.catalog.specs.verticals import (
    DEEP_CLEAN_OPTION,
    EXPRESS_OPTION,
    BeautySpec,
    CleaningSpec,
    ErrandsSpec,
    HomeServicesDetailsSerializer,
    HomeServicesSpec,
    LaundrySpec,
)
from apps.providers.models import ProviderProfile, ProviderService

User = get_user_model()


class CleaningIsOneRouteTests(TestCase):
    """Two services became one service with a question."""

    def setUp(self):
        call_command("seed_catalog", verbosity=0)

    def test_only_one_cleaning_service_is_sold(self):
        active = Service.objects.filter(category__slug="cleaning", is_active=True)

        self.assertEqual(active.count(), 1)
        self.assertEqual(active.first().name, "Cleaning")

    def _revive_deep_clean(self) -> Service:
        """Recreate the row an existing database still has.

        A fresh database never gets a deep-clean row, because the seed stopped
        producing one. The retirement path only matters for databases that
        already had it, which is every real one, so the tests below put it back
        before checking that reseeding retires it.
        """
        return Service.objects.create(
            category=Service.objects.get(slug="standard-clean").category,
            slug="deep-clean",
            name="Deep Clean",
            summary="Top to bottom.",
            spec_key="cleaning",
            pricing_model="FIXED",
            base_price_kobo=3_500_000,
            is_active=True,
        )

    def test_the_deep_clean_row_survives_deactivated(self):
        # Never deleted. A booking points at it, and history has to resolve.
        self._revive_deep_clean()

        call_command("seed_catalog", verbosity=0)

        deep = Service.objects.get(slug="deep-clean")
        self.assertFalse(deep.is_active)

    def test_the_surviving_slug_is_the_one_bookings_point_at(self):
        # Renaming the row a year of bookings hangs off would have orphaned them
        # behind a service nobody browses.
        self.assertTrue(Service.objects.filter(slug="standard-clean", is_active=True).exists())

    def test_reseeding_does_not_bring_deep_clean_back(self):
        self._revive_deep_clean()
        call_command("seed_catalog", verbosity=0)
        call_command("seed_catalog", verbosity=0)

        self.assertFalse(Service.objects.get(slug="deep-clean").is_active)

    def test_the_depth_question_is_required(self):
        depth = CleaningSpec().details_serializer().fields["depth"]

        self.assertTrue(depth.required)

    def test_both_depths_are_explained_rather_than_just_named(self):
        schema = CleaningSpec().details_schema(Service.objects.get(slug="standard-clean"))
        depth = next(f for f in schema["fields"] if f["name"] == "depth")

        self.assertEqual(depth["choice_labels"]["STANDARD"], "Standard cleaning")
        self.assertEqual(depth["choice_labels"]["DEEP"], "Deep cleaning")
        for value in ("STANDARD", "DEEP"):
            self.assertGreater(len(depth["choice_help"][value]), 30)


class CleaningPriceTests(TestCase):
    """The two prices the category already charged, kept."""

    def setUp(self):
        call_command("seed_catalog", verbosity=0)
        self.service = Service.objects.get(slug="standard-clean")

    def test_a_standard_clean_costs_the_base_price(self):
        price = agreed_price_kobo(self.service, None, {"depth": "STANDARD"})

        self.assertEqual(price, 1_500_000)

    def test_a_deep_clean_costs_what_the_deep_clean_service_used_to(self):
        price = agreed_price_kobo(self.service, None, {"depth": "DEEP"})

        self.assertEqual(price, 3_500_000)

    def test_the_difference_is_the_option_not_a_hardcoded_number(self):
        option = ServiceOption.objects.get(service=self.service, key=DEEP_CLEAN_OPTION)
        option.price_delta_kobo = 999_999
        option.save(update_fields=["price_delta_kobo"])

        price = agreed_price_kobo(self.service, None, {"depth": "DEEP"})

        self.assertEqual(price, 1_500_000 + 999_999)

    def test_a_deactivated_option_stops_being_charged(self):
        ServiceOption.objects.filter(service=self.service, key=DEEP_CLEAN_OPTION).update(
            is_active=False
        )

        self.assertEqual(agreed_price_kobo(self.service, None, {"depth": "DEEP"}), 1_500_000)

    def test_omitting_details_prices_as_it_always_did(self):
        # Every existing caller passes no details. None of them may change price.
        self.assertEqual(agreed_price_kobo(self.service, None), 1_500_000)

    def test_the_quoted_delta_matches_what_is_charged(self):
        schema = self.service.spec.details_schema(self.service)
        depth = next(f for f in schema["fields"] if f["name"] == "depth")

        quoted = depth["price_deltas"]["DEEP"]
        charged = options_delta_kobo(self.service, {"depth": "DEEP"})

        self.assertEqual(quoted, charged)
        self.assertNotIn("STANDARD", depth["price_deltas"])


class LaundryExpressTests(TestCase):
    """Express costs three thousand naira, flat."""

    #: ₦3,000 in kobo. Named once so the assertions below read as one decision
    #: rather than five copies of a number.
    EXPRESS_KOBO = 300_000

    def setUp(self):
        call_command("seed_catalog", verbosity=0)
        self.service = Service.objects.get(slug="wash-and-fold")

    def test_express_selects_an_option(self):
        self.assertEqual(LaundrySpec().option_keys({"express": True}), [EXPRESS_OPTION])
        self.assertEqual(LaundrySpec().option_keys({"express": False}), [])

    def test_standard_turnaround_costs_the_base_price(self):
        self.assertEqual(agreed_price_kobo(self.service, None, {"express": False}), 50_000)

    def test_express_is_visibly_dearer(self):
        standard = agreed_price_kobo(self.service, None, {"express": False})
        express = agreed_price_kobo(self.service, None, {"express": True})

        self.assertEqual(express, standard + self.EXPRESS_KOBO)
        self.assertGreater(express, standard)

    def test_the_surcharge_is_the_configured_amount(self):
        option = ServiceOption.objects.get(service=self.service, key=EXPRESS_OPTION)

        self.assertEqual(option.price_delta_kobo, self.EXPRESS_KOBO)
        self.assertTrue(option.is_active)

    def test_it_is_flat_rather_than_per_item(self):
        # Turning a load around in a day costs the same for five shirts as for
        # fifty, so the surcharge must not scale with the order.
        few = agreed_price_kobo(self.service, None, {"express": True, "item_count": 5})
        many = agreed_price_kobo(self.service, None, {"express": True, "item_count": 50})

        self.assertEqual(few, many)

    def test_the_quoted_surcharge_matches_what_is_charged(self):
        schema = self.service.spec.details_schema(self.service)
        express = next(f for f in schema["fields"] if f["name"] == "express")

        self.assertEqual(express["price_deltas"]["true"], self.EXPRESS_KOBO)
        self.assertEqual(
            express["price_deltas"]["true"],
            options_delta_kobo(self.service, {"express": True}),
        )

    def test_repricing_it_needs_no_code_change(self):
        ServiceOption.objects.filter(service=self.service, key=EXPRESS_OPTION).update(
            price_delta_kobo=450_000
        )

        self.assertEqual(agreed_price_kobo(self.service, None, {"express": True}), 500_000)

    def test_reseeding_keeps_the_price(self):
        call_command("seed_catalog", verbosity=0)

        self.assertEqual(
            ServiceOption.objects.get(service=self.service, key=EXPRESS_OPTION).price_delta_kobo,
            self.EXPRESS_KOBO,
        )


class ErrandsWordingTests(TestCase):
    def test_the_purchase_question_is_a_question(self):
        label = ErrandsSpec().details_serializer().fields["requires_purchase"].label

        self.assertEqual(label, "Will the provider need to buy anything for you?")

    def test_it_stays_a_boolean_so_old_bookings_still_read(self):
        field = ErrandsSpec().details_serializer().fields["requires_purchase"]

        self.assertEqual(field.__class__.__name__, "BooleanField")

    def test_the_help_says_the_cost_is_separate_without_promising_reimbursement(self):
        help_text = ErrandsSpec().presentation["requires_purchase"]["help_text"].lower()

        self.assertIn("separate", help_text)
        # Sync does not front the money or settle it, so it must not say it does.
        for promise in ("reimburse", "refund", "we pay", "sync pays", "we cover"):
            self.assertNotIn(promise, help_text)

    def test_it_is_asked_as_yes_or_no(self):
        self.assertEqual(ErrandsSpec().presentation["requires_purchase"]["style"], "yes_no")


class HomeServicesOtherTests(TestCase):
    def test_other_is_offered(self):
        self.assertIn("OTHER", HomeServicesDetailsSerializer().fields["trade"].choices)

    def test_other_needs_a_real_description(self):
        serializer = HomeServicesDetailsSerializer(
            data={"trade": "OTHER", "problem_description": "broken"}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("problem_description", serializer.errors)

    def test_a_described_other_job_is_accepted(self):
        serializer = HomeServicesDetailsSerializer(
            data={
                "trade": "OTHER",
                "problem_description": "The gate motor stopped responding to the remote.",
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_free_text_is_not_forced_into_any_format(self):
        # No commas, no tags, no key-value pairs. Somebody's own words.
        serializer = HomeServicesDetailsSerializer(
            data={
                "trade": "OTHER",
                "problem_description": "there is water coming through the ceiling upstairs",
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_the_named_trades_are_unaffected(self):
        serializer = HomeServicesDetailsSerializer(
            data={"trade": "PLUMBING", "problem_description": "Drips."}
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_a_provider_reads_the_description_not_the_word_other(self):
        summary = HomeServicesSpec().summary(
            {"trade": "OTHER", "problem_description": "Gate motor is dead"}
        )

        self.assertEqual(summary, "Gate motor is dead")


class BeautyCopyTests(TestCase):
    def setUp(self):
        call_command("seed_catalog", verbosity=0)

    def test_the_three_categories_are_the_right_ones(self):
        names = set(
            Service.objects.filter(category__slug="beauty", is_active=True).values_list(
                "name", flat=True
            )
        )

        self.assertEqual(names, {"Hair", "Nails", "Facials and Skincare"})

    def test_the_examples_are_beauty_not_groceries(self):
        for slug in ("hair", "nails", "facials-and-skincare"):
            with self.subTest(slug=slug):
                service = Service.objects.get(slug=slug)
                schema = service.spec.details_schema(service)
                treatments = next(f for f in schema["fields"] if f["name"] == "treatments")
                placeholder = treatments["placeholder"].lower()

                for grocery in ("bread", "milk", "airtime"):
                    self.assertNotIn(grocery, placeholder)
                self.assertTrue(placeholder)

    def test_each_category_gets_its_own_example(self):
        def placeholder(slug):
            service = Service.objects.get(slug=slug)
            schema = service.spec.details_schema(service)
            return next(f for f in schema["fields"] if f["name"] == "treatments")["placeholder"]

        self.assertNotEqual(placeholder("hair"), placeholder("nails"))

    def test_the_hint_does_not_demand_commas(self):
        hint = BeautySpec().presentation["treatments"]["hint"].lower()

        self.assertNotIn("comma", hint)


class SchemaContractTests(TestCase):
    """What the app is entitled to receive for every field, in every vertical."""

    def setUp(self):
        call_command("seed_catalog", verbosity=0)

    def test_every_field_carries_the_presentation_keys(self):
        required = {
            "name",
            "type",
            "required",
            "label",
            "choices",
            "help_text",
            "style",
            "placeholder",
            "hint",
            "choice_labels",
            "choice_help",
            "price_deltas",
        }

        for service in Service.objects.filter(is_active=True):
            schema = service.spec.details_schema(service)
            for field in schema["fields"]:
                with self.subTest(service=service.slug, field=field["name"]):
                    self.assertEqual(set(field), required)

    def test_a_spec_inspected_without_a_service_still_works(self):
        # The registry dumps schemas with no service. It must not need a database.
        schema = CleaningSpec().details_schema()

        self.assertTrue(schema["fields"])
        self.assertEqual(
            next(f for f in schema["fields"] if f["name"] == "depth")["price_deltas"], {}
        )


@override_settings(DEBUG=True)
class DemoSeedTests(TestCase):
    """The marketplace an investor sees.

    DEBUG is forced on because the command refuses to run without it. That guard
    is the point rather than an obstacle, and it has its own test below.
    """

    def setUp(self):
        call_command("seed_catalog", verbosity=0)
        user = User.objects.create_user(
            email="ada.okeke@example.com", password="x", phone="+2348030000001"
        )
        ProviderProfile.objects.create(user=user, display_name="Ada Cleaning Services")

        for index, name in enumerate(["M6 Alpha Services", "M5 Beta Services", "M4-Gamma"]):
            other = User.objects.create_user(
                email=f"generated{index}@example.com",
                password="x",
                phone=f"+234803000100{index}",
            )
            profile = ProviderProfile.objects.create(user=other, display_name=name)
            ProviderService.objects.create(
                provider=profile, service=Service.objects.get(slug="standard-clean")
            )

    def test_ada_is_renamed(self):
        call_command("seed_demo", verbosity=0)

        self.assertTrue(ProviderProfile.objects.filter(display_name="Ada Services").exists())
        self.assertFalse(
            ProviderProfile.objects.filter(display_name="Ada Cleaning Services").exists()
        )

    def test_ada_is_approved_and_taking_work(self):
        call_command("seed_demo", verbosity=0)
        ada = ProviderProfile.objects.get(display_name="Ada Services")

        self.assertEqual(ada.verification_status, "APPROVED")
        self.assertTrue(ada.is_accepting_jobs)

    def test_ada_offers_every_active_service(self):
        call_command("seed_demo", verbosity=0)
        ada = ProviderProfile.objects.get(display_name="Ada Services")

        offered = set(
            ProviderService.objects.filter(provider=ada, is_active=True).values_list(
                "service__slug", flat=True
            )
        )
        active = set(Service.objects.filter(is_active=True).values_list("slug", flat=True))

        self.assertEqual(offered, active)

    def test_generated_providers_leave_the_marketplace(self):
        call_command("seed_demo", verbosity=0)

        visible = ProviderService.objects.filter(
            is_active=True, provider__display_name__startswith="M"
        )

        self.assertEqual(visible.count(), 0)

    def test_generated_accounts_and_history_survive(self):
        call_command("seed_demo", verbosity=0)

        # Disabled, not deleted. Their bookings and verification history stay.
        self.assertEqual(ProviderProfile.objects.filter(display_name__startswith="M").count(), 3)
        self.assertEqual(
            ProviderService.objects.filter(provider__display_name__startswith="M").count(), 3
        )

    def test_the_cleaning_category_still_has_a_choice_of_providers(self):
        call_command("seed_demo", verbosity=0)

        cleaning = ProviderService.objects.filter(
            service__slug="standard-clean",
            is_active=True,
            provider__verification_status="APPROVED",
        )

        self.assertGreaterEqual(cleaning.count(), 3)

    def test_running_it_twice_changes_nothing(self):
        call_command("seed_demo", verbosity=0)
        before = list(
            ProviderProfile.objects.order_by("display_name").values_list(
                "display_name", "verification_status", "is_accepting_jobs"
            )
        )

        call_command("seed_demo", verbosity=0)
        after = list(
            ProviderProfile.objects.order_by("display_name").values_list(
                "display_name", "verification_status", "is_accepting_jobs"
            )
        )

        self.assertEqual(before, after)

    def test_keep_generated_leaves_them_visible(self):
        call_command("seed_demo", "--keep-generated", verbosity=0)

        visible = ProviderService.objects.filter(
            is_active=True, provider__display_name__startswith="M"
        )

        self.assertEqual(visible.count(), 3)

    def test_it_refuses_to_run_in_production(self):
        # Demo accounts in a production database would be indistinguishable from
        # real providers, and one of them takes any job in the catalog.
        with override_settings(DEBUG=False), self.assertRaises(CommandError):
            call_command("seed_demo", verbosity=0)
