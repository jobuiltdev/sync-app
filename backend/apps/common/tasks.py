"""What every background task in this system agrees to.

Tasks here move money or move lifecycles, often while nobody is watching, and
sometimes twice. The contract below is what makes that safe, and every task in
the project follows it:

1. **Fetch current state from the database.** Never act on what the caller passed
   or on what was true when the task was queued. A task queued three minutes ago
   describes a world that has moved on.
2. **Lock the row that is being contested**, so two workers serialise rather than
   both passing the same check.
3. **Re-check that the work is still needed.** Most repeat executions end here,
   having done nothing, which is exactly right.
4. **Make the change in one transaction**, with the record of it written in the
   same transaction.
5. **Be safe run twice**, and safe if the process dies at any point, including
   between an external call and recording its result.

### The three retry classes

Every task declares which of these it is, and the classification is a statement
about money rather than about code.

**SAFE TO RETRY.** Nothing outside this system changes, or the external call is a
read. Running it again at worst wastes a query. Offer expiry, challenge
retirement, the consistency sweep, and every status lookup are in this class, and
they retry automatically with backoff.

**REQUIRES RECONCILIATION.** An external write whose result we may not have seen.
A retry could duplicate it, so these do not retry: they leave a durable marker
saying an attempt was made, and a reconciliation task establishes what actually
happened by asking the provider. Payout submission is the case this exists for.

**NEVER RETRY.** An operation whose repetition would move money twice and which
cannot be reconciled. Nothing in this system is in this class, because anything
that would be has been moved into the second by making it reconcilable. That is
the design rule rather than an accident.
"""

from typing import Any

from celery import shared_task

#: Backoff for the safe class. Bounded: a task that has failed five times is not
#: going to succeed on the sixth, and an unbounded retry is how a queue fills up
#: with work nobody will ever look at.
SAFE_RETRY = {
    "autoretry_for": (Exception,),
    "retry_backoff": 10,
    "retry_backoff_max": 600,
    "retry_jitter": True,
    "max_retries": 5,
}

#: No automatic retry at all. The task records what it attempted and hands the
#: question to reconciliation, which is a read and therefore safe.
RECONCILE_ON_FAILURE: dict[str, Any] = {
    "autoretry_for": (),
    "max_retries": 0,
}


def safe_task(**options: Any):
    """A task that may be run again freely."""
    return shared_task(**{**SAFE_RETRY, **options})


def reconciled_task(**options: Any):
    """A task whose failure is a question for reconciliation, not a retry."""
    return shared_task(**{**RECONCILE_ON_FAILURE, **options})


def batched(queryset: Any, limit: int) -> list:
    """The first `limit` rows, as a list.

    Takes a queryset rather than any iterable, because the slice must happen in
    the database: pulling four hundred thousand rows into Python and then taking
    two hundred of them is not a bounded sweep.

    Every sweep is bounded. An unbounded sweep is one that holds locks for
    minutes on the day something goes wrong and there are four hundred thousand
    rows to look at, and the next run picks up whatever this one left.
    """
    return list(queryset[:limit])
