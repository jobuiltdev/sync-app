from dataclasses import dataclass

from apps.accounts.sms.base import SMSProvider


@dataclass(frozen=True)
class SentMessage:
    phone: str
    code: str


class LocMemSMSProvider(SMSProvider):
    """Test provider. Records messages in memory and sends nothing.

    Messages live on the class so a test can inspect what was sent without having
    to reach the instance the domain constructed.
    """

    sent: list[SentMessage] = []

    def send_verification_code(self, phone: str, code: str) -> None:
        type(self).sent.append(SentMessage(phone=phone, code=code))

    @classmethod
    def clear(cls) -> None:
        cls.sent = []

    @classmethod
    def last(cls) -> SentMessage | None:
        return cls.sent[-1] if cls.sent else None
