from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import Address, User

PASSWORD = "Lagos-Rider-2026"


def make_user(email: str = "ada@example.com") -> User:
    return User.objects.create_user(email=email, password=PASSWORD)


def make_address(user: User, **overrides) -> Address:
    defaults = {
        "user": user,
        "street_address": "14 Adeola Odeku Street",
        "landmark": "Opposite Eko Hotel gate",
        "area": "Victoria Island",
        "lga": "Eti-Osa",
        "state": "LAGOS",
    }
    return Address.objects.create(**{**defaults, **overrides})


class AddressModelTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_creates_an_address(self):
        address = make_address(self.user)

        self.assertEqual(address.user, self.user)
        self.assertIn("Adeola Odeku", str(address))
        self.assertIn("Lagos", str(address))

    def test_landmark_is_required_because_street_addresses_are_unreliable(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_address(self.user, landmark="")

    def test_street_address_cannot_be_empty(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_address(self.user, street_address="")

    def test_area_and_lga_are_optional(self):
        address = make_address(self.user, area="", lga="")

        self.assertEqual(address.area, "")

    def test_coordinates_are_optional(self):
        address = make_address(self.user)

        self.assertIsNone(address.latitude)
        self.assertIsNone(address.longitude)

    def test_coordinates_may_be_stored_as_a_pair(self):
        address = make_address(self.user, latitude="6.428055", longitude="3.421944")

        self.assertIsNotNone(address.latitude)

    def test_a_lone_latitude_is_refused(self):
        # Half a coordinate is not a location, and storing one would silently break
        # any distance filter built on top of it later.
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_address(self.user, latitude="6.428055")

    def test_a_lone_longitude_is_refused(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_address(self.user, longitude="3.421944")

    def test_deleting_the_user_removes_their_addresses(self):
        make_address(self.user)

        self.user.delete()

        self.assertEqual(Address.objects.count(), 0)


class DefaultAddressConstraintTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_a_user_may_have_only_one_default(self):
        make_address(self.user, is_default=True)

        with self.assertRaises(IntegrityError), transaction.atomic():
            make_address(self.user, is_default=True)

    def test_two_users_may_each_have_their_own_default(self):
        other = make_user("chidi@example.com")

        make_address(self.user, is_default=True)
        make_address(other, is_default=True)

        self.assertEqual(Address.objects.filter(is_default=True).count(), 2)

    def test_many_non_default_addresses_are_allowed(self):
        make_address(self.user)
        make_address(self.user)

        self.assertEqual(Address.objects.filter(is_default=False).count(), 2)

    def test_the_default_sorts_first(self):
        make_address(self.user, street_address="First")
        default = make_address(self.user, street_address="Second", is_default=True)

        self.assertEqual(Address.objects.filter(user=self.user).first(), default)
