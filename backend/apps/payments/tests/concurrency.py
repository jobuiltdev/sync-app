"""Running things at genuinely the same moment, for the race tests.

Shared by the settlement, payout and payment race suites so there is one
description of what "at the same instant" means here rather than three.
"""

import threading

from django.db import connections


def run_together(target, arguments: list[tuple]) -> list[Exception | None]:
    """Fires one thread per argument tuple, released from a barrier together.

    The barrier is what makes this a race rather than a sequence. Each thread
    closes its own connection afterwards, since a thread that leaves one open
    holds a lock the test then waits on forever.

    Returns one entry per thread: None where it succeeded, the exception where it
    did not, so a caller can assert on who won as well as on what survived.
    """
    outcomes: list[Exception | None] = [None] * len(arguments)
    barrier = threading.Barrier(len(arguments))

    def attempt(index: int, args: tuple) -> None:
        try:
            barrier.wait(timeout=10)
            target(*args)
        except Exception as exc:
            outcomes[index] = exc
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=attempt, args=(index, args)) for index, args in enumerate(arguments)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    return outcomes
