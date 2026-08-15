from apps.accounts.sms.base import SMSProvider


class ConsoleSMSProvider(SMSProvider):
    """Development provider. Prints the message to the console and sends nothing.

    Writes to stdout rather than the logger on purpose: logs get shipped and
    retained, and neither a verification code nor a customer's booking details
    should end up in a log aggregator. This provider is the development default
    and is never the production setting.
    """

    def send(self, phone: str, message: str) -> None:
        print(f"\n[sms] to {phone}: {message}\n")
