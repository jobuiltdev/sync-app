import uuid

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.accounts.address import Address
from apps.bookings.models import Booking, BookingStatusEvent, generate_reference
from apps.bookings.services import create_booking
from apps.bookings.state import BookingStatus
from apps.bookings.tests.factories import VALID_CLEANING_DETAILS, full_setup, make_booking


class BookingModelTests(TestCase):
    def test_creates_a_booking_with_its_relationships(self):
        booking = make_booking()

        self.assertIsNotNone(booking.customer)
        self.assertIsNotNone(booking.provider)
        self.assertIsNotNone(booking.service)

    def test_has_a_uuid_primary_key_and_base_model_timestamps(self):
        booking = make_booking()

        self.assertIsInstance(booking.id, uuid.UUID)
        self.assertIsNotNone(booking.created_at)
        self.assertIsNotNone(booking.updated_at)

    def test_starts_assigned(self):
        self.assertEqual(make_booking().status, BookingStatus.ASSIGNED)

    def test_gets_a_human_reference(self):
        booking = make_booking()

        self.assertTrue(booking.reference.startswith("SY-"))
        self.assertEqual(len(booking.reference), 9)

    def test_references_are_unique_across_bookings(self):
        references = {make_booking().reference for _ in range(5)}

        self.assertEqual(len(references), 5)

    def test_the_reference_alphabet_avoids_confusable_characters(self):
        # A reference gets read aloud to support. O versus 0 and I versus 1 are
        # where that goes wrong.
        for _ in range(50):
            self.assertNotRegex(generate_reference(), r"[OI01]")

    def test_a_duplicate_reference_is_refused(self):
        booking = make_booking()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Booking.objects.filter(pk=make_booking().pk).update(reference=booking.reference)

    def test_the_spec_key_is_copied_from_the_service(self):
        booking = make_booking()

        self.assertEqual(booking.spec_key, booking.service.spec_key)

    def test_records_which_statuses_are_terminal(self):
        self.assertFalse(make_booking(status=BookingStatus.ASSIGNED).is_terminal)
        self.assertTrue(make_booking(status=BookingStatus.COMPLETED).is_terminal)
        self.assertTrue(make_booking(status=BookingStatus.CANCELLED).is_terminal)

    def test_a_customer_with_bookings_cannot_be_deleted(self):
        # A booking is a record of something that happened between two people. It
        # must outlive a profile tidy-up, so the account is deactivated instead.
        booking = make_booking()

        with self.assertRaises(ProtectedError):
            booking.customer.delete()

    def test_a_provider_with_bookings_cannot_be_deleted(self):
        booking = make_booking()

        with self.assertRaises(ProtectedError):
            booking.provider.delete()

    def test_a_service_with_bookings_cannot_be_deleted(self):
        booking = make_booking()

        with self.assertRaises(ProtectedError):
            booking.service.delete()

    def test_coordinates_must_be_stored_as_a_pair(self):
        booking = make_booking()

        with self.assertRaises(IntegrityError), transaction.atomic():
            Booking.objects.filter(pk=booking.pk).update(address_latitude="6.42")


class AddressSnapshotTests(TestCase):
    def setUp(self):
        self.data = full_setup()
        self.booking = create_booking(
            customer=self.data["customer"],
            service=self.data["service"],
            provider=self.data["provider"],
            address=self.data["address"],
            details=VALID_CLEANING_DETAILS,
        )

    def test_the_snapshot_holds_the_location_not_just_a_reference(self):
        self.assertEqual(self.booking.address_street, "14 Adeola Odeku Street")
        self.assertEqual(self.booking.address_landmark, "Opposite Eko Hotel gate")
        self.assertEqual(self.booking.address_area, "Victoria Island")
        self.assertEqual(self.booking.address_lga, "Eti-Osa")
        self.assertEqual(self.booking.address_state, "LAGOS")
        self.assertEqual(self.booking.address_directions, "Blue gate, second floor.")

    def test_the_landmark_survives_because_it_is_how_a_provider_finds_the_place(self):
        self.assertTrue(self.booking.address_landmark)

    def test_the_source_address_is_still_linked_for_convenience(self):
        self.assertEqual(self.booking.source_address, self.data["address"])

    def test_editing_the_original_address_does_not_rewrite_the_booking(self):
        # The whole reason for a snapshot: last month's completed job must not move
        # house when the customer updates their flat number.
        address = self.data["address"]
        address.street_address = "99 Somewhere Else"
        address.landmark = "A different landmark"
        address.save()

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.address_street, "14 Adeola Odeku Street")
        self.assertEqual(self.booking.address_landmark, "Opposite Eko Hotel gate")

    def test_deleting_the_original_address_does_not_destroy_the_booking(self):
        self.data["address"].delete()

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.address_street, "14 Adeola Odeku Street")
        self.assertIsNone(self.booking.source_address)

    def test_the_snapshot_renders_a_readable_summary(self):
        self.assertIn("Adeola Odeku", self.booking.address_summary)
        self.assertIn("Eko Hotel", self.booking.address_summary)

    def test_coordinates_are_copied_when_present(self):
        data = full_setup()
        address = Address.objects.create(
            user=data["customer"],
            street_address="1 Somewhere",
            landmark="Near the mast",
            state="LAGOS",
            latitude="6.428055",
            longitude="3.421944",
        )

        booking = create_booking(
            customer=data["customer"],
            service=data["service"],
            provider=data["provider"],
            address=address,
            details=VALID_CLEANING_DETAILS,
        )

        self.assertEqual(str(booking.address_latitude), "6.428055")
        self.assertEqual(str(booking.address_longitude), "3.421944")


class BookingStatusEventTests(TestCase):
    def test_creation_writes_an_opening_event(self):
        data = full_setup()

        booking = create_booking(
            customer=data["customer"],
            service=data["service"],
            provider=data["provider"],
            address=data["address"],
            details=VALID_CLEANING_DETAILS,
        )

        event = booking.events.get()
        self.assertEqual(event.from_status, "")
        self.assertEqual(event.to_status, BookingStatus.ASSIGNED)
        self.assertEqual(event.actor_id, data["customer"].id)

    def test_events_are_ordered_oldest_first(self):
        booking = make_booking()
        for target in [BookingStatus.EN_ROUTE, BookingStatus.IN_PROGRESS]:
            BookingStatusEvent.objects.create(
                booking=booking, from_status=booking.status, to_status=target, actor_type="PROVIDER"
            )

        self.assertEqual(
            [e.to_status for e in booking.events.all()],
            [BookingStatus.EN_ROUTE, BookingStatus.IN_PROGRESS],
        )

    def test_events_go_when_their_booking_goes(self):
        booking = make_booking()
        BookingStatusEvent.objects.create(
            booking=booking, to_status=BookingStatus.CANCELLED, actor_type="CUSTOMER"
        )

        booking.delete()

        self.assertEqual(BookingStatusEvent.objects.count(), 0)
