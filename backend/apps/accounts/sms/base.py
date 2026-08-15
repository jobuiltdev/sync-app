"""The boundary between the verification domain and whoever sends the message.

The domain depends on this interface and never on a vendor. Swapping Termii for
another provider is a settings change and one new subclass, with no edit to the
verification logic.
"""

from abc import ABC, abstractmethod

from django.conf import settings
from django.utils.module_loading import import_string


class SMSDeliveryError(Exception):
    """The provider could not accept the message.

    Raised so the caller can decide what to do. Verification treats it as a hard
    failure: if the code did not go out, no challenge should be left behind
    implying that it did.
    """


VERIFICATION_TEMPLATE = (
    "{code} is your Sync verification code. It expires shortly. Do not share it with anyone."
)


class SMSProvider(ABC):
    """One way to put a string on somebody's phone.

    `send` is the whole interface. A verification code and a job offer are both
    just text by the time they reach here, and giving each kind of message its own
    provider method would mean every new kind needing an edit in every vendor
    adapter.
    """

    @abstractmethod
    def send(self, phone: str, message: str) -> None:
        """Deliver one message to an E.164 number.

        Raises `SMSDeliveryError` when the provider would not take it. What that
        means is the caller's decision: verification treats it as a hard failure,
        and notifications retry a bounded number of times and then give up.
        """

    def send_verification_code(self, phone: str, code: str) -> None:
        """Deliver a verification code to an E.164 number.

        Composed here rather than in each adapter, so the wording is the same
        whichever provider is configured and no vendor module owns user-facing
        copy.

        Implementations must not log the code. It is a live credential for as long
        as the challenge stands.
        """
        self.send(phone, VERIFICATION_TEMPLATE.format(code=code))


def get_sms_provider() -> SMSProvider:
    """Builds the configured provider.

    Resolved per call rather than cached at import, so tests and settings
    overrides take effect without reaching into module state.
    """
    provider_class = import_string(settings.SMS_BACKEND)
    return provider_class()
