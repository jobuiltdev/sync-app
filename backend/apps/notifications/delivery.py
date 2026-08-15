"""Handing one message to a provider, and classifying what came back.

The only place this app talks to a channel, and it does so through the same
abstractions everything else uses: `SMSProvider` for SMS and Django's email
framework for email. No vendor is named here, and no booking or payment code can
reach a vendor at all.

The interesting part is the classification. A provider failure is not one thing:

* **Temporary.** The provider is down or slow. Trying again in a minute is
  likely to work, so it is worth retrying.
* **Permanent.** The destination is not deliverable, or the provider has refused
  the message outright. Retrying sends the same message to the same bad address
  five more times and costs money each time.

Treating those the same is how a queue fills with work that will never succeed.
"""

import logging

from django.core.mail import EmailMessage

from apps.accounts.sms.base import get_sms_provider
from apps.notifications.events import Channel
from apps.notifications.messages import render
from apps.notifications.models import Notification
from apps.notifications.service import destination_for

logger = logging.getLogger(__name__)


class TemporaryDeliveryFailure(Exception):
    """Worth trying again."""


class PermanentDeliveryFailure(Exception):
    """Not worth trying again. The message will never arrive as addressed."""


#: Substrings that mean a provider will never accept this message however many
#: times it is offered. Matched against the failure text rather than a status
#: code, because the abstractions deliberately do not expose vendor status codes.
PERMANENT_MARKERS = (
    "invalid",
    "not a valid",
    "unsubscribe",
    "blacklist",
    "blocked",
    "does not exist",
    "no such",
    "rejected",
    "malformed",
)


def classify(error: Exception) -> Exception:
    """Whether this failure is worth another attempt."""
    text = str(error).lower()

    if any(marker in text for marker in PERMANENT_MARKERS):
        return PermanentDeliveryFailure(str(error))

    return TemporaryDeliveryFailure(str(error))


def deliver(notification: Notification, context: dict) -> None:
    """Sends one message, or raises something the task knows how to handle.

    Raises `PermanentDeliveryFailure` for a message that will never arrive, and
    `TemporaryDeliveryFailure` for one worth retrying. Returns quietly when it
    was sent, and the caller records that.
    """
    # The channel first, because a channel with no sender is a deployment
    # problem and not something about this recipient.
    if notification.channel not in Channel.values:
        raise PermanentDeliveryFailure(f"There is no way to send on {notification.channel}.")

    destination = destination_for(notification.recipient, notification.channel)
    if not destination:
        # No verified destination on this channel. Not a failure to deliver: a
        # decision not to, taken because sending booking details to an unverified
        # number could hand them to a stranger.
        raise PermanentDeliveryFailure(
            "No verified destination for this channel. Nothing was sent."
        )

    message = render(notification.event_type, context)

    if notification.channel == Channel.SMS:
        _send_sms(destination, message.sms)
    else:
        _send_email(destination, message.subject, message.body)

    # The event, the channel and the recipient's id. Never the destination, never
    # the message: an address and a body in a log is the same disclosure as one
    # in the database, with wider distribution.
    logger.info(
        "Delivered a notification",
        extra={
            "event_type": notification.event_type,
            "channel": notification.channel,
            "recipient_id": str(notification.recipient_id),
            "subject_reference": notification.subject_reference,
        },
    )


def _send_sms(destination: str, body: str) -> None:
    try:
        # The same interface verification uses. Whether that resolves to Termii or
        # a console printer is a settings question and not this module's business.
        get_sms_provider().send(destination, body)
    except Exception as exc:
        # `SMSDeliveryError` is the expected one, but a provider that raises
        # something else must not escape as an unhandled task failure: it would
        # retry on Celery's terms instead of ours.
        raise classify(exc) from exc


def _send_email(destination: str, subject: str, body: str) -> None:
    try:
        EmailMessage(subject=subject, body=body, to=[destination]).send(fail_silently=False)
    except Exception as exc:
        raise classify(exc) from exc


def record_success(notification: Notification) -> None:
    notification.attempts += 1
    notification.save(update_fields=["attempts", "updated_at"])
    notification.mark_sent()


def record_attempt(notification: Notification) -> None:
    notification.attempts += 1
    notification.save(update_fields=["attempts", "updated_at"])


def record_permanent_failure(notification: Notification, reason: str) -> None:
    """Records a message that will not be attempted again.

    A destination that was never verified is recorded as skipped rather than
    failed, because nothing was wrong with the delivery: there was simply nobody
    it could safely be sent to.
    """
    notification.attempts += 1
    notification.save(update_fields=["attempts", "updated_at"])

    if "No verified destination" in reason:
        notification.mark_skipped(reason)
    else:
        notification.mark_failed(reason)

    logger.warning(
        "A notification will not be delivered",
        extra={
            "event_type": notification.event_type,
            "channel": notification.channel,
            "recipient_id": str(notification.recipient_id),
            "reason": reason[:200],
        },
    )
