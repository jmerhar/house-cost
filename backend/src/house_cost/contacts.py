"""A person's email address and phone number, as they type them and as notifications use them."""

import re

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
#: Characters people write a phone number with, before it is normalised.
PHONE_TYPED = r"^[+\d\s().\-/]*$"


class InvalidContact(ValueError):
    """An address or number that cannot be one: ``code`` is "invalid_email" or "invalid_phone"."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def email(value: str) -> str:
    """An email address trimmed, or "" for none."""
    value = value.strip()
    if value and (len(value) > 254 or not EMAIL.match(value)):
        raise InvalidContact("invalid_email")
    return value


def phone(value: str, country_code: str) -> str:
    """A phone number in international form ("+351912345678"), or "" for none.

    Spaces, dots, dashes and brackets are dropped; "00" stands for "+"; a number without either
    is taken to be in ``country_code``'s country, as people write their own country's numbers.
    """
    digits = re.sub(r"[\s().\-/]", "", value)
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+"):
        digits = f"+{country_code}{digits}"
    if not re.fullmatch(r"\+\d{8,15}", digits):
        raise InvalidContact("invalid_phone")
    return digits
