from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.catalog import specs
from apps.catalog.models import Service, ServiceCategory, ServiceOption
from apps.catalog.tests.factories import make_category, make_option, make_service


class ServiceCategoryTests(TestCase):
    def test_creates_a_category(self):
        category = make_category("dispatch", name="Dispatch")

        self.assertEqual(str(category), "Dispatch")
        self.assertTrue(category.is_active)

    def test_slug_is_unique(self):
        # Built directly rather than through the factory, which reuses by slug.
        ServiceCategory.objects.create(slug="dispatch", name="Dispatch")

        with self.assertRaises(IntegrityError), transaction.atomic():
            ServiceCategory.objects.create(slug="dispatch", name="Dispatch Again")

    def test_orders_by_sort_order_then_name(self):
        make_category("laundry", name="Laundry", sort_order=2)
        make_category("beauty", name="Beauty", sort_order=1)
        make_category("cleaning", name="Cleaning", sort_order=1)

        self.assertEqual(
            [c.name for c in ServiceCategory.objects.all()], ["Beauty", "Cleaning", "Laundry"]
        )


class ServiceTests(TestCase):
    def test_creates_a_service_under_a_category(self):
        category = make_category()
        service = make_service(category, slug="deep-clean")

        self.assertEqual(service.category, category)
        self.assertEqual(list(category.services.all()), [service])

    def test_slug_is_unique_across_categories(self):
        make_service(slug="deep-clean")

        with self.assertRaises(IntegrityError), transaction.atomic():
            make_service(make_category("beauty"), slug="deep-clean")

    def test_base_price_cannot_be_negative(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_service(base_price_kobo=-1)

    def test_a_category_holding_services_cannot_be_deleted(self):
        # Deleting it would orphan services customers can still see.
        service = make_service()

        with self.assertRaises(ProtectedError):
            service.category.delete()

    def test_deleting_a_service_removes_its_options(self):
        service = make_service()
        make_option(service)

        service.delete()

        self.assertEqual(ServiceOption.objects.count(), 0)


class ServiceSpecBindingTests(TestCase):
    def test_a_service_resolves_its_spec(self):
        service = make_service(spec_key="cleaning")

        self.assertEqual(service.spec.key, "cleaning")

    def test_an_unregistered_spec_key_is_rejected_by_validation(self):
        service = Service(
            category=make_category(), slug="mystery", name="Mystery", spec_key="teleportation"
        )

        with self.assertRaises(ValidationError) as caught:
            service.full_clean()

        self.assertIn("spec_key", caught.exception.error_dict)

    def test_every_phase_one_vertical_is_registered(self):
        self.assertEqual(
            specs.registered_keys(),
            ["beauty", "cleaning", "dispatch", "errands", "home_services", "laundry"],
        )

    def test_each_spec_exposes_a_details_schema(self):
        for key in specs.registered_keys():
            schema = specs.get(key).details_schema()

            self.assertEqual(schema["key"], key)
            self.assertTrue(schema["fields"], f"{key} declares no fields")

    def test_registering_a_duplicate_key_is_refused(self):
        # Two modules claiming one key would make which spec applies depend on
        # import order.
        with self.assertRaises(ValueError):
            specs.register(specs.get("cleaning"))

    def test_an_unknown_key_raises_a_named_error(self):
        with self.assertRaises(specs.SpecNotRegistered):
            specs.get("teleportation")


class ServiceOptionTests(TestCase):
    def test_option_keys_are_unique_within_a_service(self):
        service = make_service()
        make_option(service, "ironing")

        with self.assertRaises(IntegrityError), transaction.atomic():
            make_option(service, "ironing")

    def test_the_same_key_may_be_used_by_a_different_service(self):
        make_option(make_service(slug="one"), "ironing")
        make_option(make_service(slug="two"), "ironing")

        self.assertEqual(2, sum(s.options.count() for s in Service.objects.all()))


class DetailsValidationTests(TestCase):
    def test_a_valid_cleaning_payload_passes(self):
        serializer = specs.get("cleaning").details_serializer(
            data={
                "property_type": "APARTMENT",
                "bedrooms": 3,
                "bathrooms": 2,
                "depth": "DEEP",
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_an_invalid_choice_is_rejected(self):
        serializer = specs.get("cleaning").details_serializer(
            data={"property_type": "CASTLE", "bedrooms": 3, "bathrooms": 2, "depth": "DEEP"}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("property_type", serializer.errors)

    def test_a_missing_required_field_is_rejected(self):
        serializer = specs.get("dispatch").details_serializer(
            data={"pickup_landmark": "Ikeja City Mall"}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("dropoff_landmark", serializer.errors)

    def test_one_vertical_cannot_satisfy_another(self):
        # The whole point of per-vertical specs: a laundry payload is not a valid
        # dispatch request, and core booking code never has to know why.
        serializer = specs.get("dispatch").details_serializer(
            data={"item_count": 12, "wash_type": "DRY_CLEAN"}
        )

        self.assertFalse(serializer.is_valid())
