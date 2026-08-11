"""Normalisation for the two identifiers a user can be known by.

Both run before anything is written, so the database only ever holds one canonical
form of an address or a number. Without that, uniqueness is unenforceable:
"Ada@Example.com" and "ada@example.com" are the same mailbox, and "0803 123 4567",
"+2348031234567" and "234 803 123 4567" are the same phone.
"""

import unicodedata

import phonenumbers
from django.core.exceptions import ValidationError

DEFAULT_REGION = "NG"


def normalize_email(email: str) -> str:
    """Lowercase and NFKC-normalise an address.

    The whole address is lowercased, not just the domain. The local part is
    technically case-sensitive per RFC 5321, but no mail provider a customer will
    use treats it that way, and honouring the RFC here would let two accounts exist
    for one human, which is the failure mode that actually matters.
    """
    return unicodedata.normalize("NFKC", email).strip().lower()


def normalize_phone(phone: str, region: str = DEFAULT_REGION) -> str:
    """Parse a phone number and return it in E.164.

    Defaults to Nigerian parsing, so local formats like 08031234567 resolve to
    +2348031234567, while numbers already carrying a country code are respected.
    """
    candidate = phone.strip()
    if not candidate:
        raise ValidationError("Enter a phone number.", code="invalid_phone")

    try:
        parsed = phonenumbers.parse(candidate, region)
    except phonenumbers.NumberParseException as exc:
        raise ValidationError("Enter a valid phone number.", code="invalid_phone") from exc

    if not phonenumbers.is_valid_number(parsed):
        raise ValidationError("Enter a valid phone number.", code="invalid_phone")

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
