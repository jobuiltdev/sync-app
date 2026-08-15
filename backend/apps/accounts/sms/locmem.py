from dataclasses import dataclass

from apps.accounts.sms.base import SMSProvider


@dataclass(frozen=True)
class SentMessage:
    phone: str
    code: str


@dataclass(frozen=True)
class SentSMS:
    phone: str
    body: str


class LocMemSMSProvider(SMSProvider):
    """Test provider. Records messages in memory and sends nothing.

    Two records, because tests ask two different questions of it. `sent` holds the
    raw verification codes, which is what a verification test needs and what it
    could not recover from the rendered text. `messages` holds every message as it
    would actually have gone out, which is what a notification test needs.

    Both live on the class so a test can inspect them without having to reach the
    instance the domain constructed.
    """

    sent: list[SentMessage] = []
    messages: list[SentSMS] = []

    def send(self, phone: str, message: str) -> None:
        type(self).messages.append(SentSMS(phone=phone, body=message))

    def send_verification_code(self, phone: str, code: str) -> None:
        type(self).sent.append(SentMessage(phone=phone, code=code))
        # Still goes through `send`, so the fake exercises the same path a real
        # provider would and `messages` sees the rendered code too.
        super().send_verification_code(phone, code)

    @classmethod
    def clear(cls) -> None:
        cls.sent = []
        cls.messages = []

    @classmethod
    def last(cls) -> SentMessage | None:
        return cls.sent[-1] if cls.sent else None

    @classmethod
    def last_message(cls) -> SentSMS | None:
        return cls.messages[-1] if cls.messages else None
