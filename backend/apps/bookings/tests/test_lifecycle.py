from django.test import TestCase

from apps.bookings.models import Booking
from apps.bookings.services import IllegalTransition, transition
from apps.bookings.state import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    ActorType,
    BookingStatus,
    actors_for,
    is_allowed,
    targets_from,
)
from apps.bookings.tests.factories import make_booking


class TransitionTableTests(TestCase):
    def test_every_status_appears_in_the_table(self):
        # A status missing from the table would be a dead end reachable only by a
        # direct database write.
        self.assertEqual(set(ALLOWED_TRANSITIONS), set(BookingStatus.values))

    def test_no_transition_targets_an_unknown_status(self):
        for targets in ALLOWED_TRANSITIONS.values():
            self.assertTrue(set(targets) <= set(BookingStatus.values))

    def test_every_transition_names_at_least_one_actor(self):
        for current, targets in ALLOWED_TRANSITIONS.items():
            for target, actors in targets.items():
                self.assertTrue(actors, f"{current} -> {target} permits nobody")

    def test_every_actor_named_is_a_known_actor(self):
        for targets in ALLOWED_TRANSITIONS.values():
            for actors in targets.values():
                self.assertTrue(set(actors) <= set(ActorType.values))

    def test_terminal_statuses_lead_nowhere(self):
        for status in TERMINAL_STATUSES:
            self.assertEqual(targets_from(status), frozenset())

    def test_en_route_is_optional_because_assigned_also_reaches_in_progress(self):
        # A service with no travel step simply never uses EN_ROUTE. That is how the
        # architecture expresses its optionality, without a per-service flag.
        self.assertIn(BookingStatus.IN_PROGRESS, targets_from(BookingStatus.ASSIGNED))
        self.assertIn(BookingStatus.EN_ROUTE, targets_from(BookingStatus.ASSIGNED))

    def test_only_a_provider_starts_work(self):
        self.assertEqual(
            actors_for(BookingStatus.ASSIGNED, BookingStatus.IN_PROGRESS),
            frozenset({ActorType.PROVIDER}),
        )

    def test_only_a_customer_confirms_completion(self):
        # The provider says the work is done; the customer decides whether it is.
        self.assertEqual(
            actors_for(BookingStatus.AWAITING_CONFIRMATION, BookingStatus.COMPLETED),
            frozenset({ActorType.CUSTOMER}),
        )

    def test_is_allowed_reports_without_mutating(self):
        self.assertTrue(
            is_allowed(BookingStatus.ASSIGNED, BookingStatus.EN_ROUTE, ActorType.PROVIDER)
        )
        self.assertFalse(
            is_allowed(BookingStatus.ASSIGNED, BookingStatus.COMPLETED, ActorType.CUSTOMER)
        )


class TransitionTests(TestCase):
    def test_the_happy_path_runs_to_completion(self):
        booking = make_booking()

        transition(booking, BookingStatus.EN_ROUTE, actor_type=ActorType.PROVIDER)
        transition(booking, BookingStatus.IN_PROGRESS, actor_type=ActorType.PROVIDER)
        transition(booking, BookingStatus.AWAITING_CONFIRMATION, actor_type=ActorType.PROVIDER)
        transition(booking, BookingStatus.COMPLETED, actor_type=ActorType.CUSTOMER)

        booking.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.COMPLETED)

    def test_a_service_without_travel_skips_en_route(self):
        booking = make_booking()

        transition(booking, BookingStatus.IN_PROGRESS, actor_type=ActorType.PROVIDER)

        self.assertEqual(booking.status, BookingStatus.IN_PROGRESS)

    def test_each_transition_writes_a_history_row(self):
        booking = make_booking()

        transition(booking, BookingStatus.EN_ROUTE, actor_type=ActorType.PROVIDER, reason="Leaving")

        event = booking.events.latest("created_at")
        self.assertEqual(event.from_status, BookingStatus.ASSIGNED)
        self.assertEqual(event.to_status, BookingStatus.EN_ROUTE)
        self.assertEqual(event.reason, "Leaving")

    def test_completion_stamps_completed_at(self):
        booking = make_booking(status=BookingStatus.AWAITING_CONFIRMATION)

        transition(booking, BookingStatus.COMPLETED, actor_type=ActorType.CUSTOMER)

        self.assertIsNotNone(booking.completed_at)

    def test_cancellation_stamps_cancelled_at(self):
        booking = make_booking()

        transition(booking, BookingStatus.CANCELLED, actor_type=ActorType.CUSTOMER)

        self.assertIsNotNone(booking.cancelled_at)

    def test_a_customer_may_cancel_before_work_starts(self):
        booking = make_booking()

        transition(booking, BookingStatus.CANCELLED, actor_type=ActorType.CUSTOMER)

        self.assertEqual(booking.status, BookingStatus.CANCELLED)


class IllegalTransitionTests(TestCase):
    def test_assigned_cannot_jump_to_completed(self):
        booking = make_booking()

        with self.assertRaises(IllegalTransition):
            transition(booking, BookingStatus.COMPLETED, actor_type=ActorType.CUSTOMER)

    def test_a_refused_transition_leaves_the_database_unchanged(self):
        booking = make_booking()

        with self.assertRaises(IllegalTransition):
            transition(booking, BookingStatus.COMPLETED, actor_type=ActorType.CUSTOMER)

        self.assertEqual(Booking.objects.get(pk=booking.pk).status, BookingStatus.ASSIGNED)

    def test_a_refused_transition_writes_no_history_row(self):
        booking = make_booking()
        before = booking.events.count()

        with self.assertRaises(IllegalTransition):
            transition(booking, BookingStatus.COMPLETED, actor_type=ActorType.CUSTOMER)

        self.assertEqual(booking.events.count(), before)

    def test_a_customer_cannot_declare_work_in_progress(self):
        booking = make_booking()

        with self.assertRaises(IllegalTransition):
            transition(booking, BookingStatus.IN_PROGRESS, actor_type=ActorType.CUSTOMER)

    def test_a_provider_cannot_confirm_completion_on_the_customers_behalf(self):
        booking = make_booking(status=BookingStatus.AWAITING_CONFIRMATION)

        with self.assertRaises(IllegalTransition):
            transition(booking, BookingStatus.COMPLETED, actor_type=ActorType.PROVIDER)

    def test_a_completed_booking_cannot_be_reopened(self):
        booking = make_booking(status=BookingStatus.COMPLETED)

        with self.assertRaises(IllegalTransition):
            transition(booking, BookingStatus.IN_PROGRESS, actor_type=ActorType.PROVIDER)

    def test_a_cancelled_booking_cannot_be_resurrected(self):
        booking = make_booking(status=BookingStatus.CANCELLED)

        with self.assertRaises(IllegalTransition):
            transition(booking, BookingStatus.ASSIGNED, actor_type=ActorType.CUSTOMER)

    def test_work_in_progress_cannot_be_cancelled(self):
        # Cancelling a job the provider is standing in the customer's home doing is
        # a dispute, not a cancellation, and disputes are a later milestone.
        booking = make_booking(status=BookingStatus.IN_PROGRESS)

        with self.assertRaises(IllegalTransition):
            transition(booking, BookingStatus.CANCELLED, actor_type=ActorType.CUSTOMER)

    def test_a_status_cannot_transition_to_itself(self):
        booking = make_booking()

        with self.assertRaises(IllegalTransition):
            transition(booking, BookingStatus.ASSIGNED, actor_type=ActorType.CUSTOMER)

    def test_the_error_reports_what_would_have_been_allowed(self):
        booking = make_booking()

        with self.assertRaises(IllegalTransition) as caught:
            transition(booking, BookingStatus.COMPLETED, actor_type=ActorType.CUSTOMER)

        details = caught.exception.details
        self.assertEqual(details["current_status"], BookingStatus.ASSIGNED)
        self.assertEqual(details["requested_status"], BookingStatus.COMPLETED)
        self.assertIn(BookingStatus.EN_ROUTE, details["allowed_transitions"])

    def test_the_error_names_the_actor_when_the_edge_exists_but_the_actor_is_wrong(self):
        booking = make_booking()

        with self.assertRaises(IllegalTransition) as caught:
            transition(booking, BookingStatus.IN_PROGRESS, actor_type=ActorType.CUSTOMER)

        self.assertIn("provider", str(caught.exception.detail).lower())
