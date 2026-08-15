"""The vocabulary, the routing policy, and what the messages actually say.

These are the tests that catch an event added without a message, a message added
without a route, and a route that quietly starts sending SMS for something that
does not warrant one. Each of those is invisible in review and obvious here.
"""

from django.test import SimpleTestCase

from apps.notifications.events import CHANNEL_POLICY, Channel, EventType, channels_for
from apps.notifications.messages import _BUILDERS, naira, render

#: A context with every key any builder reads, so one loop can render all of them.
FULL_CONTEXT = {
    "reference": "SY-8F3K2A",
    "service_name": "Standard clean",
    "provider_name": "Ada Cleaning Services",
    "area": "Victoria Island",
    "state": "Lagos",
    "amount_kobo": 1_600_000,
}


class VocabularyTests(SimpleTestCase):
    def test_every_event_has_a_route(self):
        """An event with no channels is an event nobody is ever told about.

        It would look completely correct at the call site and do nothing.
        """
        missing = [event for event in EventType.values if event not in CHANNEL_POLICY]

        self.assertEqual(missing, [])

    def test_every_event_has_a_message(self):
        missing = [event for event in EventType.values if event not in _BUILDERS]

        self.assertEqual(missing, [])

    def test_no_message_without_an_event(self):
        """A builder for an event that no longer exists is dead copy."""
        orphaned = [key for key in _BUILDERS if key not in EventType.values]

        self.assertEqual(orphaned, [])

    def test_unknown_event_routes_nowhere(self):
        self.assertEqual(channels_for("SOMETHING_ELSE"), ())

    def test_every_route_is_a_real_channel(self):
        for event, channels in CHANNEL_POLICY.items():
            for channel in channels:
                self.assertIn(channel, Channel.values, f"{event} routes to {channel}")

    def test_no_event_routes_to_the_same_channel_twice(self):
        for event, channels in CHANNEL_POLICY.items():
            self.assertEqual(len(channels), len(set(channels)), event)


class ChannelPolicyTests(SimpleTestCase):
    """SMS costs money per message and interrupts somebody's day.

    Pinned as an explicit set rather than a rule, so widening it is a deliberate
    edit to this list and shows up in a diff as one.
    """

    EXPECTED_SMS = {
        EventType.PROVIDER_ASSIGNED,
        EventType.BOOKING_EN_ROUTE,
        EventType.BOOKING_AWAITING_CONFIRMATION,
        EventType.PAYMENT_FAILED,
        EventType.OFFER_RECEIVED,
        EventType.JOB_CANCELLED,
        EventType.PAYOUT_PAID,
        EventType.PAYOUT_FAILED,
    }

    def test_sms_goes_only_where_it_is_warranted(self):
        actual = {event for event, channels in CHANNEL_POLICY.items() if Channel.SMS in channels}

        self.assertEqual(actual, self.EXPECTED_SMS)

    def test_verification_is_not_routed_here(self):
        """Verification codes belong to the verification system.

        Routing one through this app would require an unverified destination,
        which is exactly what this app refuses to send to. The two would deadlock,
        and the fact that no such event exists is what prevents it.
        """
        names = " ".join(EventType.values).upper()

        self.assertNotIn("VERIF", names)
        self.assertNotIn("OTP", names)


class MessageTests(SimpleTestCase):
    def test_every_message_renders(self):
        for event in EventType.values:
            with self.subTest(event=event):
                message = render(event, FULL_CONTEXT)

                self.assertTrue(message.subject.strip())
                self.assertTrue(message.body.strip())

    def test_no_message_leaks_a_placeholder_or_a_none(self):
        """The failure mode of a missing context key, made visible."""
        for event in EventType.values:
            with self.subTest(event=event):
                message = render(event, FULL_CONTEXT)
                text = f"{message.subject} {message.body}"

                self.assertNotIn("None", text)
                self.assertNotIn("{", text)
                self.assertNotIn("}", text)

    def test_a_missing_context_does_not_raise(self):
        """A caller that forgot a key gets a poorer message, not an exception.

        Raising here would travel up into whatever domain call triggered it.
        """
        for event in EventType.values:
            with self.subTest(event=event):
                message = render(event, {})

                self.assertTrue(message.body.strip())

    def test_an_unknown_event_gets_something_neutral(self):
        message = render("NO_SUCH_EVENT", FULL_CONTEXT)

        self.assertTrue(message.body.strip())

    def test_sms_bodies_stay_within_two_segments(self):
        """Termii bills per 160 characters.

        Two segments is the ceiling; the ones a provider acts on should be one.
        """
        for event, channels in CHANNEL_POLICY.items():
            if Channel.SMS not in channels:
                continue
            with self.subTest(event=event):
                self.assertLessEqual(len(render(event, FULL_CONTEXT).sms), 320)

    def test_a_lost_offer_never_names_the_winner(self):
        message = render(
            EventType.OFFER_SUPERSEDED,
            {**FULL_CONTEXT, "provider_name": "Ada Cleaning Services"},
        )
        text = f"{message.subject} {message.body}"

        self.assertNotIn("Ada Cleaning Services", text)
        # Nor the reference, which would let them look up a job that is not theirs.
        self.assertNotIn("SY-8F3K2A", text)

    def test_a_failed_payout_carries_no_bank_wording(self):
        message = render(
            EventType.PAYOUT_FAILED,
            {**FULL_CONTEXT, "failure_reason": "ACCOUNT DORMANT: contact 0700-GTB"},
        )

        self.assertNotIn("DORMANT", message.body)
        self.assertNotIn("0700", message.body)


class NairaTests(SimpleTestCase):
    def test_kobo_are_shown_as_naira(self):
        self.assertEqual(naira(2_000_000), "NGN 20,000")

    def test_zero_is_shown_rather_than_hidden(self):
        self.assertEqual(naira(0), "NGN 0")

    def test_thousands_are_grouped(self):
        self.assertEqual(naira(150_000_000), "NGN 1,500,000")
