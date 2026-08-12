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


class SMSProvider(ABC):
    @abstractmethod
    def send_verification_code(self, phone: str, code: str) -> None:
        """Deliver a verification code to an E.164 number.

        Implementations must not log the code. It is a live credential for as long
        as the challenge stands.
        """


def get_sms_provider() -> SMSProvider:
    """Builds the configured provider.

    Resolved per call rather than cached at import, so tests and settings
    overrides take effect without reaching into module state.
    """
    provider_class = import_string(settings.SMS_BACKEND)
    return provider_class()
