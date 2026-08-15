from apps.accounts.sms.base import SMSDeliveryError, SMSProvider


class FailingSMSProvider(SMSProvider):
    """Test provider that always fails, for asserting nothing is left behind."""

    def send(self, phone: str, message: str) -> None:
        raise SMSDeliveryError("The provider rejected the message.")
