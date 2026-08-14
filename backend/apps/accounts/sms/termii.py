"""Termii, behind the SMSProvider interface.

The production provider docs/architecture.md names. The only module that knows
what Termii's API looks like, and it changes nothing about the verification
security model: the code is still generated, hashed and superseded by the domain,
and this is asked only to deliver a string.

**The code is never logged.** Not on success, not on failure, not in an exception
message. It is a live credential for as long as the challenge stands, and the one
place it exists in plaintext is the request that carries it.
"""

import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

from apps.accounts.sms.base import SMSDeliveryError, SMSProvider

logger = logging.getLogger(__name__)

API_ROOT = "https://api.ng.termii.com"
TIMEOUT_SECONDS = 20


class TermiiSMSProvider(SMSProvider):
    """Sends verification codes through Termii.

    Configured entirely from the environment. Constructing this without an API
    key fails immediately rather than at the first message, so a deployment that
    has switched SMS_BACKEND without setting the key cannot start quietly and
    then swallow every verification attempt.
    """

    def __init__(self) -> None:
        config = settings.TERMII
        self.api_key = config["API_KEY"]
        self.sender_id = config["SENDER_ID"]
        self.channel = config["CHANNEL"]
        self.api_root = config.get("API_ROOT", API_ROOT)
        self.timeout = config.get("TIMEOUT_SECONDS", TIMEOUT_SECONDS)

        if not self.api_key:
            raise SMSDeliveryError("TERMII_API_KEY is not set. Termii cannot send without it.")

    def send_verification_code(self, phone: str, code: str) -> None:
        # Termii wants the number without a leading plus.
        destination = phone[1:] if phone.startswith("+") else phone

        body = json.dumps(
            {
                "to": destination,
                "from": self.sender_id,
                "sms": (
                    f"{code} is your Sync verification code. "
                    "It expires shortly. Do not share it with anyone."
                ),
                "type": "plain",
                "channel": self.channel,
                "api_key": self.api_key,
            }
        ).encode()

        request = urllib.request.Request(
            f"{self.api_root}/api/sms/send",
            method="POST",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            # The response body carries Termii's reason and does not contain the
            # message, so it is safe to surface. The request body is not touched,
            # because it holds both the code and the API key.
            detail = exc.read().decode(errors="replace")[:200]
            raise SMSDeliveryError(f"Termii returned {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise SMSDeliveryError(f"Could not reach Termii: {type(exc).__name__}") from exc

        # Termii answers 200 with a body describing the refusal when it will not
        # send, so the status code alone is not the outcome.
        message_id = str(payload.get("message_id", ""))
        if not message_id:
            raise SMSDeliveryError(
                f"Termii did not accept the message: {payload.get('message', 'no reason given')}"
            )

        # The id, the destination and nothing else. A delivery record is worth
        # having when somebody says a code never arrived; the code itself is not.
        logger.info("Termii accepted a verification message %s for %s", message_id, destination)
