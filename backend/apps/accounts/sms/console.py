import logging

from apps.accounts.sms.base import SMSProvider

logger = logging.getLogger(__name__)


class ConsoleSMSProvider(SMSProvider):
    """Development provider. Prints the code to the console and sends nothing.

    Writes to stdout rather than the logger on purpose: logs get shipped and
    retained, and a verification code should not end up in a log aggregator. This
    provider is the development default and is never the production setting.
    """

    def send_verification_code(self, phone: str, code: str) -> None:
        print(f"\n[sms] verification code for {phone}: {code}\n")
