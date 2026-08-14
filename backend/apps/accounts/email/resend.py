"""Resend, as a Django email backend.

Django's own email framework is the provider-neutral abstraction here, as
docs/architecture.md records, and `EMAIL_BACKEND` is what selects an
implementation. So this is a `BaseEmailBackend` rather than a parallel interface:
the verification domain keeps calling `send_mail` and has no idea who delivers it.

**Why Resend rather than SES.** The architecture left this open between the two.
Resend needs an API key and a verified domain; SES needs an AWS account, an IAM
user, a sandbox exit request that a human reviews, and a region decision. For a
product that has not launched, the setup cost is the whole difference, and SES's
advantage is per-message price at a volume nobody here has yet. Moving to SES
later is a different `EMAIL_BACKEND` and no other change, which is exactly what
this boundary is for.

**Nothing here logs a message body.** Verification emails contain a live code.
"""

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Any

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

API_ROOT = "https://api.resend.com"
TIMEOUT_SECONDS = 20


class ResendEmailBackend(BaseEmailBackend):
    """Delivers through Resend's HTTP API.

    `fail_silently` is honoured because Django's contract says so, but the
    verification flow always passes False: a code that did not go out must roll
    the challenge back rather than leave one behind implying it did.
    """

    def __init__(self, fail_silently: bool = False, **kwargs: Any) -> None:
        super().__init__(fail_silently=fail_silently, **kwargs)

        config = settings.RESEND
        self.api_key = config["API_KEY"]
        self.api_root = config.get("API_ROOT", API_ROOT)
        self.timeout = config.get("TIMEOUT_SECONDS", TIMEOUT_SECONDS)

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        if not email_messages:
            return 0

        if not self.api_key:
            if self.fail_silently:
                return 0
            raise ValueError("RESEND_API_KEY is not set. Resend cannot send without it.")

        sent = 0
        for message in email_messages:
            try:
                message_id = self._send(message)
            except Exception:
                if not self.fail_silently:
                    raise
                continue

            # Django's backend contract returns a count, with no room for a
            # provider id. Attaching it to the message gives a caller that wants
            # the reference somewhere to read it, without changing the contract.
            message.provider_message_id = message_id  # type: ignore[attr-defined]
            sent += 1

        return sent

    def _send(self, message: EmailMessage) -> str:
        body = json.dumps(
            {
                "from": message.from_email or settings.DEFAULT_FROM_EMAIL,
                "to": list(message.to),
                "cc": list(message.cc),
                "bcc": list(message.bcc),
                "subject": message.subject,
                "text": message.body,
            }
        ).encode()

        request = urllib.request.Request(
            f"{self.api_root}/emails",
            method="POST",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:200]
            raise ValueError(f"Resend returned {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            # Never interpolate the request, which carries the Authorization
            # header, or the body, which carries the code.
            raise ValueError(f"Could not reach Resend: {type(exc).__name__}") from exc

        message_id = str(payload.get("id", ""))
        if not message_id:
            raise ValueError("Resend did not return a message id.")

        # Recipients and the provider id. Never the subject or the body.
        logger.info("Resend accepted message %s for %d recipient(s)", message_id, len(message.to))
        return message_id
