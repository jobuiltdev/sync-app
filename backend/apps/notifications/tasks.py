"""Delivering notifications, on the queue that already exists.

One task, on the M6B Celery app, following the same contract as every other task
here: read current state, check the work is still needed, do it, be safe run
twice.

**Safe to retry**, in the `apps.common.tasks` classification, but with a narrower
retry than `safe_task` gives. A notification retries on a provider being
unreachable and does not retry on a provider refusing the message, because
retrying a refusal sends the same message to the same bad address four more times
and pays for each attempt.

The difference from the financial tasks is what an unknown outcome means. A payout
whose result we did not see must never be resubmitted; a notification whose result
we did not see is worth another try, because the cost of a duplicate is somebody
being told twice and the cost of giving up is somebody not hearing about their
work at all.
"""

import logging

from celery import shared_task

from apps.notifications.delivery import (
    PermanentDeliveryFailure,
    TemporaryDeliveryFailure,
    deliver,
    record_attempt,
    record_permanent_failure,
    record_success,
)
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)

#: Five attempts over roughly ten minutes. A provider that has been unreachable
#: for ten minutes will not be reached by the sixth try, and the message is stale
#: by then anyway: an offer notification arriving after the window closed is worse
#: than none at all.
MAX_ATTEMPTS = 5


@shared_task(
    name="apps.notifications.tasks.deliver_notification",
    autoretry_for=(TemporaryDeliveryFailure,),
    retry_backoff=10,
    retry_backoff_max=300,
    retry_jitter=True,
    # A backstop rather than the real limit. The attempt count on the row is what
    # decides, because that survives a worker restart and Celery's counter does
    # not.
    max_retries=MAX_ATTEMPTS,
)
def deliver_notification(notification_id: str, context: dict | None = None) -> str:
    """Sends one notification.

    The context travels with the task rather than being stored, so the contents of
    a message exist only for as long as its delivery.

    Safe run twice. A task redelivered by the broker after the row was already
    sent finds it terminal and does nothing, which is the check that makes the
    whole thing idempotent even though sending is an external write.
    """
    notification = Notification.objects.filter(pk=notification_id).first()

    if notification is None:
        # Deleted with its recipient, most likely. Nothing to do, nothing wrong.
        return "gone"

    if notification.is_terminal:
        # Sent, failed or skipped already. The guard that makes a duplicate task
        # harmless.
        return f"already {notification.status.lower()}"

    try:
        deliver(notification, context or {})
    except PermanentDeliveryFailure as exc:
        record_permanent_failure(notification, str(exc))
        # Deliberately not re-raised. This is a decided outcome, and raising would
        # put a task in the failed queue that nobody should ever look at again.
        return "not deliverable"
    except TemporaryDeliveryFailure:
        record_attempt(notification)

        if notification.attempts >= MAX_ATTEMPTS:
            notification.mark_failed(
                f"The provider could not be reached in {notification.attempts} attempts."
            )
            # Recorded rather than retried, so an operator can see it and the
            # queue does not carry work that will never succeed.
            return "gave up"

        # Re-raised so Celery applies the backoff configured above.
        raise

    record_success(notification)
    return "sent"
