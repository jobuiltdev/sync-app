from rest_framework import status
from rest_framework.test import APITestCase

from apps.bookings.tests.factories import make_provider_offering
from apps.catalog.tests.factories import make_category, make_option, make_service

CATEGORIES_URL = "/api/v1/catalog/categories/"
SERVICES_URL = "/api/v1/catalog/services/"


class CatalogBrowsingTests(APITestCase):
    def setUp(self):
        self.cleaning = make_category("cleaning", name="Cleaning", sort_order=0)
        self.dispatch = make_category("dispatch", name="Dispatch", sort_order=1)
        self.service = make_service(self.cleaning, slug="standard-clean")
        make_service(self.dispatch, slug="same-day-dispatch", spec_key="dispatch")

    def test_categories_are_readable_without_an_account(self):
        # Someone deciding whether Sync is worth signing up for must be able to see
        # what it offers first.
        response = self.client.get(CATEGORIES_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([c["slug"] for c in response.data], ["cleaning", "dispatch"])

    def test_categories_carry_their_services(self):
        response = self.client.get(CATEGORIES_URL)

        cleaning = next(c for c in response.data if c["slug"] == "cleaning")
        self.assertEqual([s["slug"] for s in cleaning["services"]], ["standard-clean"])

    def test_inactive_categories_are_hidden(self):
        make_category("retired", is_active=False)

        response = self.client.get(CATEGORIES_URL)

        self.assertNotIn("retired", [c["slug"] for c in response.data])

    def test_inactive_services_are_hidden_from_their_category(self):
        make_service(self.cleaning, slug="retired-clean", is_active=False)

        response = self.client.get(CATEGORIES_URL)

        cleaning = next(c for c in response.data if c["slug"] == "cleaning")
        self.assertNotIn("retired-clean", [s["slug"] for s in cleaning["services"]])

    def test_services_can_be_listed(self):
        response = self.client.get(SERVICES_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)

    def test_services_can_be_filtered_by_category(self):
        response = self.client.get(SERVICES_URL, {"category": "dispatch"})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["slug"], "same-day-dispatch")

    def test_an_unknown_category_filter_returns_nothing_rather_than_everything(self):
        response = self.client.get(SERVICES_URL, {"category": "teleportation"})

        self.assertEqual(response.data["count"], 0)

    def test_service_lists_are_paginated(self):
        response = self.client.get(SERVICES_URL)

        self.assertIn("results", response.data)
        self.assertIn("count", response.data)


class ServiceDetailTests(APITestCase):
    def setUp(self):
        self.service = make_service(slug="standard-clean", spec_key="cleaning")
        make_option(self.service, "ironing")

    def test_returns_the_service_with_its_options(self):
        response = self.client.get(f"{SERVICES_URL}standard-clean/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["slug"], "standard-clean")
        self.assertEqual([o["key"] for o in response.data["options"]], ["ironing"])

    def test_returns_the_request_field_schema_from_the_spec(self):
        # This is what lets the mobile request form be driven by the API, so a new
        # vertical does not require a new app build.
        response = self.client.get(f"{SERVICES_URL}standard-clean/")

        schema = response.data["details_schema"]
        self.assertEqual(schema["key"], "cleaning")
        self.assertIn("bedrooms", [f["name"] for f in schema["fields"]])

    def test_the_schema_marks_which_fields_are_required(self):
        response = self.client.get(f"{SERVICES_URL}standard-clean/")

        fields = {f["name"]: f for f in response.data["details_schema"]["fields"]}
        self.assertTrue(fields["bedrooms"]["required"])
        self.assertFalse(fields["has_supplies"]["required"])

    def test_the_schema_lists_the_choices_for_a_choice_field(self):
        response = self.client.get(f"{SERVICES_URL}standard-clean/")

        fields = {f["name"]: f for f in response.data["details_schema"]["fields"]}
        self.assertEqual(sorted(fields["depth"]["choices"]), ["DEEP", "STANDARD"])

    def test_an_unknown_service_is_a_404_with_the_error_envelope(self):
        response = self.client.get(f"{SERVICES_URL}does-not-exist/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "NOT_FOUND")

    def test_an_inactive_service_is_not_reachable(self):
        make_service(slug="retired", is_active=False)

        response = self.client.get(f"{SERVICES_URL}retired/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ServiceProviderDiscoveryTests(APITestCase):
    def setUp(self):
        self.service = make_service(slug="standard-clean")

    def url(self, slug: str = "standard-clean") -> str:
        return f"{SERVICES_URL}{slug}/providers/"

    def test_lists_providers_offering_the_service_without_an_account(self):
        make_provider_offering(self.service, email="one@example.com")

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["display_name"], "Ada Cleaning Services")

    def test_reports_the_price_this_provider_charges(self):
        offering = make_provider_offering(self.service, email="two@example.com")
        offered = offering.offered_services.get()
        offered.price_override_kobo = 1_200_000
        offered.save()

        response = self.client.get(self.url())

        self.assertEqual(response.data[0]["price_kobo"], 1_200_000)

    def test_a_provider_who_stopped_offering_it_is_hidden(self):
        offering = make_provider_offering(self.service, email="three@example.com")
        offering.offered_services.update(is_active=False)

        response = self.client.get(self.url())

        self.assertEqual(len(response.data), 0)

    def test_providers_of_another_service_are_not_listed(self):
        other = make_service(slug="deep-clean")
        make_provider_offering(other, email="four@example.com")

        response = self.client.get(self.url())

        self.assertEqual(len(response.data), 0)

    def test_an_unknown_service_is_a_404(self):
        response = self.client.get(self.url("teleportation"))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
