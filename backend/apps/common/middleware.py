"""Cross-cutting request handling.

One middleware: giving every request an identifier that appears in its response
and in every log line it produces. That is the difference between "a payout
failed at some point yesterday" and being able to read the exact sequence of
what happened.
"""

import logging
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)

HEADER = "HTTP_X_REQUEST_ID"
RESPONSE_HEADER = "X-Request-ID"

#: Long enough for a UUID with room to spare, short enough that nobody can push
#: an unbounded string into every log line this request writes.
MAX_LENGTH = 64

#: Letters, digits, dashes and underscores. Wide enough for the trace id formats
#: other systems actually use, and narrow enough that nothing here can carry a
#: newline, a space or a control character. This value is echoed into a response
#: header and into log output, and anything that could carry a newline could
#: forge a convincing log line.
ALLOWED = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_")


def _clean(value: str) -> str:
    """The incoming id if it is safe to reuse, otherwise nothing.

    An id from outside is a convenience for tracing a request across a proxy, not
    something to trust. It is accepted only when it is short and made entirely of
    characters that cannot break a log line.
    """
    candidate = value.strip()

    if not candidate or len(candidate) > MAX_LENGTH:
        return ""
    if not set(candidate) <= ALLOWED:
        return ""

    return candidate


class RequestIDMiddleware:
    """Attaches an id to the request, the response and the logs.

    Held in a context variable rather than on the request object alone, so the
    logging filter can reach it without every log call having to be handed the
    request. It is deliberately never written to the database: it identifies one
    HTTP round trip, not a domain object, and a payout that outlives the request
    that created it has its own reference for that.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = _clean(str(request.META.get(HEADER, ""))) or uuid.uuid4().hex

        request.request_id = request_id  # type: ignore[attr-defined]
        token = set_request_id(request_id)

        try:
            response = self.get_response(request)
        finally:
            reset_request_id(token)

        response[RESPONSE_HEADER] = request_id
        return response


# --- the ambient identifier ------------------------------------------------

from contextvars import ContextVar  # noqa: E402

_request_id: ContextVar[str] = ContextVar("request_id", default="")


def set_request_id(value: str):
    return _request_id.set(value)


def reset_request_id(token) -> None:
    _request_id.reset(token)


def get_request_id() -> str:
    return _request_id.get()


class RequestIDFilter(logging.Filter):
    """Puts the current request id on every log record.

    A filter rather than an adapter, so it applies to Django's own loggers and to
    third-party ones without anybody changing a call site. Records made outside a
    request, which is every Celery task, get a dash: honest about the fact that
    no HTTP request is in flight rather than inventing one.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True
