"""Log formatting, and the rule about what may never appear in a log.

Named `log` rather than `logging` so that nothing in this package ever has to
think about whether an import resolves here or to the standard library.

Production emits one JSON object per line, because logs are read by a machine
before they are read by a person and a line that has to be parsed with a regex is
a line nobody greps correctly under pressure. Development keeps the human format,
since a developer reading a terminal is the actual audience there.

### What must never be logged

Passwords, verification codes, JWTs, refresh tokens, card details, bank account
numbers, provider API keys, and raw provider payloads. These are not filtered out
by scrubbing after the fact, which is a losing game: they are not passed to a
logger in the first place, and the tests assert that for each area. This
formatter is the last line rather than the first, and it drops any field whose
name looks like a secret so that a future caller who logs `extra={"token": ...}`
does not quietly succeed.

No dependency was added for this. A JSON formatter is twenty lines of the
standard library, and a structured logging package would bring a configuration
system, a processor pipeline and its own opinions for no benefit at this size.
"""

import json
import logging
from typing import Any

#: Anything whose key contains one of these is dropped from a log record's extra
#: fields. Substring matching on purpose, so `paystack_secret_key`, `api_key` and
#: `refresh_token` are all caught without listing every spelling.
SENSITIVE_KEYS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "code_hash",
    "otp",
    "verification_code",
    "account_number",
    "card",
    "cvv",
    "pin",
    "payload",
)

#: Attributes every LogRecord carries. Everything else was put there by a caller
#: and is what gets promoted into the JSON object.
_STANDARD = frozenset(
    set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__)
    | {"asctime", "message", "request_id", "taskName"}
)


def is_sensitive(key: str) -> bool:
    """Whether a field name looks like it holds something that must not be logged.

    Separators are stripped before matching, so `api_key`, `apiKey`, `X-Api-Key`
    and `API KEY` are all the same question. Without that, a header name copied
    into a log record would slip through on a hyphen.
    """
    normalised = key.lower().replace("-", "").replace("_", "").replace(" ", "")
    return any(marker.replace("_", "") in normalised for marker in SENSITIVE_KEYS)


class JSONFormatter(logging.Formatter):
    """One JSON object per line.

    Fields a caller passed through `extra` are promoted to top level, minus
    anything that looks like a secret. The exception text is included but the
    traceback is not sent anywhere a client can see it: this is server-side
    output, which is exactly where a traceback belongs.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }

        for key, value in record.__dict__.items():
            if key in _STANDARD or key.startswith("_"):
                continue
            if is_sensitive(key):
                # Dropped rather than masked. A masked value still tells a reader
                # that a secret was there, and a caller who sees "[redacted]"
                # tends to conclude the logging is handling it for them.
                continue
            payload[key] = _safe(value)

        if record.exc_info:
            exception = record.exc_info[1]
            payload["error"] = type(exception).__name__ if exception else "Exception"
            payload["error_detail"] = str(exception)[:500] if exception else ""

        return json.dumps(payload, default=str)


def _safe(value: Any) -> Any:
    """Keeps a value if json can render it, otherwise its repr."""
    if isinstance(value, str | int | float | bool | type(None)):
        return value
    if isinstance(value, list | tuple):
        return [_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _safe(item) for key, item in value.items() if not is_sensitive(key)}
    return str(value)
