from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Address, User

PASSWORD = "Lagos-Rider-2026"
URL = "/api/v1/customer/addresses/"

PAYLOAD = {
    "street_address": "14 Adeola Odeku Street",
    "landmark": "Opposite Eko Hotel gate",
    "area": "Victoria Island",
    "lga": "Eti-Osa",
    "state": "LAGOS",
}


class AddressAuthorizationTests(APITestCase):
    def setUp(self):
        self.ada = User.objects.create_user(email="ada@example.com", password=PASSWORD)
        self.chidi = User.objects.create_user(email="chidi@example.com", password=PASSWORD)

    def test_listing_requires_authentication(self):
        response = self.client.get(URL)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["error"]["code"], "NOT_AUTHENTICATED")

    def test_creating_requires_authentication(self):
        response = self.client.post(URL, PAYLOAD, format="json")

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_user_only_sees_their_own_addresses(self):
        Address.objects.create(user=self.chidi, **PAYLOAD)
        self.client.force_authenticate(self.ada)

        response = self.client.get(URL)

        self.assertEqual(response.data["count"], 0)

    def test_another_users_address_is_a_404_not_a_403(self):
        # A 403 would confirm the id exists. A 404 says nothing either way.
        theirs = Address.objects.create(user=self.chidi, **PAYLOAD)
        self.client.force_authenticate(self.ada)

        response = self.client.get(f"{URL}{theirs.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_another_users_address_cannot_be_updated(self):
        theirs = Address.objects.create(user=self.chidi, **PAYLOAD)
        self.client.force_authenticate(self.ada)

        response = self.client.patch(f"{URL}{theirs.id}/", {"landmark": "Hijacked"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        theirs.refresh_from_db()
        self.assertEqual(theirs.landmark, PAYLOAD["landmark"])

    def test_another_users_address_cannot_be_deleted(self):
        theirs = Address.objects.create(user=self.chidi, **PAYLOAD)
        self.client.force_authenticate(self.ada)

        response = self.client.delete(f"{URL}{theirs.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Address.objects.filter(pk=theirs.pk).exists())

    def test_an_address_cannot_be_created_for_someone_else(self):
        self.client.force_authenticate(self.ada)

        response = self.client.post(URL, {**PAYLOAD, "user": str(self.chidi.id)}, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Address.objects.get().user, self.ada)


class AddressCrudTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ada@example.com", password=PASSWORD)
        self.client.force_authenticate(self.user)

    def test_creates_an_address(self):
        response = self.client.post(URL, PAYLOAD, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["landmark"], PAYLOAD["landmark"])

    def test_the_first_address_becomes_the_default_automatically(self):
        # Asking someone to nominate a default when they have exactly one is pure
        # friction.
        response = self.client.post(URL, PAYLOAD, format="json")

        self.assertTrue(response.data["is_default"])

    def test_a_later_address_is_not_default_unless_asked(self):
        self.client.post(URL, PAYLOAD, format="json")

        second = self.client.post(URL, {**PAYLOAD, "street_address": "2 Other"}, format="json")

        self.assertFalse(second.data["is_default"])

    def test_marking_a_new_address_default_demotes_the_previous_one(self):
        first = self.client.post(URL, PAYLOAD, format="json").data

        self.client.post(
            URL, {**PAYLOAD, "street_address": "2 Other", "is_default": True}, format="json"
        )

        self.assertFalse(Address.objects.get(id=first["id"]).is_default)
        self.assertEqual(Address.objects.filter(is_default=True).count(), 1)

    def test_promoting_an_existing_address_demotes_the_other(self):
        first = self.client.post(URL, PAYLOAD, format="json").data
        second = self.client.post(URL, {**PAYLOAD, "street_address": "2 Other"}, format="json").data

        self.client.patch(f"{URL}{second['id']}/", {"is_default": True}, format="json")

        self.assertFalse(Address.objects.get(id=first["id"]).is_default)
        self.assertTrue(Address.objects.get(id=second["id"]).is_default)

    def test_deleting_the_default_promotes_another(self):
        # Leaving a customer with addresses but no default would silently break the
        # "use my usual place" path later.
        first = self.client.post(URL, PAYLOAD, format="json").data
        self.client.post(URL, {**PAYLOAD, "street_address": "2 Other"}, format="json")

        self.client.delete(f"{URL}{first['id']}/")

        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)

    def test_deleting_the_only_address_leaves_none(self):
        created = self.client.post(URL, PAYLOAD, format="json").data

        response = self.client.delete(f"{URL}{created['id']}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Address.objects.count(), 0)

    def test_updates_a_field(self):
        created = self.client.post(URL, PAYLOAD, format="json").data

        response = self.client.patch(
            f"{URL}{created['id']}/", {"landmark": "Beside the filling station"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["landmark"], "Beside the filling station")

    def test_rejects_a_missing_landmark(self):
        response = self.client.post(URL, {**PAYLOAD, "landmark": ""}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "VALIDATION_ERROR")
        self.assertIn("landmark", response.data["error"]["details"]["fields"])

    def test_rejects_an_unknown_state(self):
        response = self.client.post(URL, {**PAYLOAD, "state": "ATLANTIS"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("state", response.data["error"]["details"]["fields"])

    def test_rejects_a_lone_coordinate(self):
        response = self.client.post(URL, {**PAYLOAD, "latitude": "6.428055"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("latitude", response.data["error"]["details"]["fields"])

    def test_accepts_a_coordinate_pair(self):
        response = self.client.post(
            URL, {**PAYLOAD, "latitude": "6.428055", "longitude": "3.421944"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_a_nonexistent_address_is_a_404(self):
        response = self.client.get(f"{URL}00000000-0000-4000-8000-000000000000/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
