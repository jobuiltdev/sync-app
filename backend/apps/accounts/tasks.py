"""Account housekeeping.

One task: retiring verification challenges that can no longer verify anything.

**Nothing is deleted.** A challenge is the record that somebody was asked to
prove a number at a particular moment, and the hash it carries is what makes a
replayed code fail rather than being silently unrecognised. Deleting them would
trade an audit trail and part of the anti-replay model for disk space nobody is
short of. What this does instead is mark them retired, which is the same thing
the domain already does when a newer challenge supersedes an older one.

**Safe to retry.** It writes one timestamp onto rows that are already unusable,
and the query excludes anything it has already touched.
"""

import logging

from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone

from apps.accounts.challenges import VerificationChallenge
from apps.common.tasks import safe_task

logger = logging.getLogger(__name__)


@safe_task(name="apps.accounts.tasks.retire_stale_challenges")
def retire_stale_challenges() -> dict[str, int]:
    """Marks challenges that can no longer be used as retired.

    Two kinds qualify, and neither could verify anything before this ran:

    * **expired**, whose window has passed
    * **exhausted**, which used up their attempts without being consumed

    A consumed challenge is left exactly as it is. It is the record of a
    successful verification and is the most useful row in the table.

    Bounded, because the first run against a long-lived database has every stale
    challenge ever made to get through, and the next tick picks up the rest.
    """
    limit = settings.TASK_BATCH_SIZE
    now = timezone.now()

    stale = (
        VerificationChallenge.objects.filter(
            consumed_at__isnull=True,
            superseded_at__isnull=True,
        )
        .filter(Q(expires_at__lte=now) | Q(attempt_count__gte=F("max_attempts")))
        .order_by("expires_at")
        .values_list("pk", flat=True)
    )

    batch = list(stale[:limit])
    if not batch:
        return {"retired": 0}

    # A single conditional update rather than a row at a time. The filter is
    # repeated so that a challenge consumed between the read and this write is
    # not retired underneath somebody who was in the middle of using it.
    retired = VerificationChallenge.objects.filter(
        pk__in=batch, consumed_at__isnull=True, superseded_at__isnull=True
    ).update(superseded_at=now, updated_at=now)

    if retired:
        # Counts only. Never a destination, never a hash, and there is no code
        # here to leak in the first place.
        logger.info("Retired %d unusable verification challenge(s)", retired)

    return {"retired": retired}
