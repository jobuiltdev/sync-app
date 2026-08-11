from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.catalog.tests.factories import make_service
from apps.providers.models import ProviderProfile, ProviderService, VerificationStatus

PASSWORD = "Lagos-Rider-2026"

PROFILE_URL = "/api/v1/provider/profile/"
CREATE_URL = "/api/v1/provider/profile/create/"
SERVICES_URL = "/api/v1/provider/services/"
AREAS_URL = "/api/v1/provider/areas/"


def make_user(email: str = "ada@example.com") -> User:
    return User.objects.create_user(email=email, password=PASSWORD)


class ProviderProfileApiTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_authenticate(self.user)

    def test_creating_a_profile_requires_authentication(self):
        self.client.force_authenticate(None)

        response = self.client.post(CREATE_URL, {"display_name": "Ada"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_creates_a_provider_profile_for_the_signed_in_account(self):
        response = self.client.post(CREATE_URL, {"display_name": "Ada's Cleaning"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ProviderProfile.objects.get().user, self.user)

    def test_a_new_profile_starts_pending(self):
        response = self.client.post(CREATE_URL, {"display_name": "Ada's Cleaning"}, format="json")

        self.assertEqual(response.data["verification_status"], VerificationStatus.PENDING)

    def test_verification_status_cannot_be_self_declared(self):
        # Otherwise a provider approves themselves and walks into a customer's home.
        response = self.client.post(
            CREATE_URL,
            {"display_name": "Ada", "verification_status": VerificationStatus.APPROVED},
            format="json",
        )

        self.assertEqual(response.data["verification_status"], VerificationStatus.PENDING)

    def test_verification_status_cannot_be_raised_by_update(self):
        self.client.post(CREATE_URL, {"display_name": "Ada"}, format="json")

        self.client.patch(
            PROFILE_URL, {"verification_status": VerificationStatus.APPROVED}, format="json"
        )

        self.assertEqual(
            ProviderProfile.objects.get().verification_status, VerificationStatus.PENDING
        )

    def test_a_second_profile_is_refused(self):
        self.client.post(CREATE_URL, {"display_name": "Ada"}, format="json")

        response = self.client.post(CREATE_URL, {"display_name": "Again"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"]["code"], "PROVIDER_PROFILE_EXISTS")

    def test_reading_the_profile_before_creating_one_is_a_clear_error(self):
        response = self.client.get(PROFILE_URL)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "PROVIDER_PROFILE_NOT_FOUND")

    def test_reads_the_signed_in_providers_profile(self):
        self.client.post(CREATE_URL, {"display_name": "Ada's Cleaning"}, format="json")

        response = self.client.get(PROFILE_URL)

        self.assertEqual(response.data["display_name"], "Ada's Cleaning")

    def test_updates_the_profile(self):
        self.client.post(CREATE_URL, {"display_name": "Ada"}, format="json")

        response = self.client.patch(PROFILE_URL, {"bio": "Ten years in Lagos."}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["bio"], "Ten years in Lagos.")

    def test_a_provider_never_sees_another_providers_profile(self):
        self.client.post(CREATE_URL, {"display_name": "Ada"}, format="json")
        other = make_user("chidi@example.com")
        ProviderProfile.objects.create(user=other, display_name="Chidi")

        response = self.client.get(PROFILE_URL)

        self.assertEqual(response.data["display_name"], "Ada")

    def test_rejects_an_empty_display_name(self):
        response = self.client.post(CREATE_URL, {"display_name": ""}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")


class ProviderServiceApiTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.profile = ProviderProfile.objects.create(user=self.user, display_name="Ada")
        self.service = make_service(slug="standard-clean")
        self.client.force_authenticate(self.user)

    def test_requires_authentication(self):
        self.client.force_authenticate(None)

        self.assertEqual(self.client.get(SERVICES_URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_offers_a_service_by_slug(self):
        response = self.client.post(SERVICES_URL, {"service_slug": "standard-clean"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(ProviderService.objects.get().provider, self.profile)

    def test_reports_the_catalog_price_when_there_is_no_override(self):
        response = self.client.post(SERVICES_URL, {"service_slug": "standard-clean"}, format="json")

        self.assertEqual(response.data["effective_price_kobo"], self.service.base_price_kobo)

    def test_an_override_replaces_the_catalog_price(self):
        response = self.client.post(
            SERVICES_URL,
            {"service_slug": "standard-clean", "price_override_kobo": 2_000_000},
            format="json",
        )

        self.assertEqual(response.data["effective_price_kobo"], 2_000_000)

    def test_offering_the_same_service_twice_is_refused(self):
        self.client.post(SERVICES_URL, {"service_slug": "standard-clean"}, format="json")

        response = self.client.post(SERVICES_URL, {"service_slug": "standard-clean"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "SERVICE_ALREADY_OFFERED")

    def test_an_inactive_service_cannot_be_offered(self):
        make_service(slug="retired", is_active=False)

        response = self.client.post(SERVICES_URL, {"service_slug": "retired"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("service_slug", response.data["error"]["details"]["fields"])

    def test_a_negative_override_is_refused(self):
        response = self.client.post(
            SERVICES_URL,
            {"service_slug": "standard-clean", "price_override_kobo": -100},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_lists_only_this_providers_services(self):
        other = ProviderProfile.objects.create(
            user=make_user("chidi@example.com"), display_name="Chidi"
        )
        ProviderService.objects.create(provider=other, service=self.service)

        response = self.client.get(SERVICES_URL)

        self.assertEqual(len(response.data), 0)

    def test_another_providers_offer_cannot_be_deleted(self):
        other = ProviderProfile.objects.create(
            user=make_user("chidi@example.com"), display_name="Chidi"
        )
        theirs = ProviderService.objects.create(provider=other, service=self.service)

        response = self.client.delete(f"{SERVICES_URL}{theirs.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(ProviderService.objects.filter(pk=theirs.pk).exists())

    def test_stops_offering_a_service(self):
        created = self.client.post(
            SERVICES_URL, {"service_slug": "standard-clean"}, format="json"
        ).data

        response = self.client.delete(f"{SERVICES_URL}{created['id']}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(ProviderService.objects.count(), 0)

    def test_an_account_without_a_provider_profile_is_told_so(self):
        self.client.force_authenticate(make_user("nobody@example.com"))

        response = self.client.get(SERVICES_URL)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["error"]["code"], "PROVIDER_PROFILE_NOT_FOUND")


class ProviderServiceAreaApiTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.profile = ProviderProfile.objects.create(user=self.user, display_name="Ada")
        self.client.force_authenticate(self.user)

    def test_adds_an_area(self):
        response = self.client.post(AREAS_URL, {"state": "LAGOS", "lga": "Ikeja"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.profile.service_areas.count(), 1)

    def test_an_area_without_an_lga_covers_the_state(self):
        response = self.client.post(AREAS_URL, {"state": "LAGOS"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["lga"], "")

    def test_the_same_area_twice_is_refused(self):
        self.client.post(AREAS_URL, {"state": "LAGOS", "lga": "Ikeja"}, format="json")

        response = self.client.post(AREAS_URL, {"state": "LAGOS", "lga": "Ikeja"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "AREA_ALREADY_COVERED")

    def test_rejects_an_unknown_state(self):
        response = self.client.post(AREAS_URL, {"state": "ATLANTIS"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("state", response.data["error"]["details"]["fields"])

    def test_lists_only_this_providers_areas(self):
        other = ProviderProfile.objects.create(
            user=make_user("chidi@example.com"), display_name="Chidi"
        )
        other.service_areas.create(state="LAGOS", lga="Ikeja")

        response = self.client.get(AREAS_URL)

        self.assertEqual(len(response.data), 0)

    def test_removes_an_area(self):
        created = self.client.post(AREAS_URL, {"state": "LAGOS"}, format="json").data

        response = self.client.delete(f"{AREAS_URL}{created['id']}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
