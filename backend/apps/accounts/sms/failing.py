from apps.accounts.sms.base import SMSDeliveryError, SMSProvider


class FailingSMSProvider(SMSProvider):
    """Test provider that always fails, for asserting nothing is left behind."""

    def send_verification_code(self, phone: str, code: str) -> None:
        raise SMSDeliveryError("The provider rejected the message.")
