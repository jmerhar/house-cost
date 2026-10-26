"""The fiscal QR code Portuguese invoices carry (Portaria 195/2020), and what it states.

Its fields are `KEY:value` pairs joined by `*`: A the issuer's NIF, B the customer's, D the kind of
document, F its date, G its number, H its ATCUD, I3–I8 the taxable amounts and VAT at each rate,
N the total tax and O the total with tax. Being part of the certified invoice, what it says is
taken over anything read from the page.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from PIL import Image


@dataclass(frozen=True)
class Atcud:
    """What an invoice's QR code states."""

    issuer_nif: str
    customer_nif: str | None
    kind: str | None
    on: date | None
    number: str | None
    atcud: str | None
    tax_cents: int | None
    total_cents: int | None


def _cents(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int((Decimal(value) * 100).to_integral_value())
    except InvalidOperation:
        return None


def _date(value: str | None) -> date | None:
    if not value or len(value) != 8 or not value.isdigit():
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


def parse(text: str) -> Atcud | None:
    """The fields of an ATCUD QR code's text, or None when the text is not one."""
    fields: dict[str, str] = {}
    for part in text.split("*"):
        key, sep, value = part.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    issuer = fields.get("A", "")
    if not (issuer.isdigit() and len(issuer) == 9 and "O" in fields):
        return None
    customer = fields.get("B")
    return Atcud(
        issuer_nif=issuer,
        customer_nif=customer if customer and customer.isdigit() else None,
        kind=fields.get("D"),
        on=_date(fields.get("F")),
        number=fields.get("G"),
        atcud=fields.get("H"),
        tax_cents=_cents(fields.get("N")),
        total_cents=_cents(fields.get("O")),
    )


def find(images: list[Image.Image]) -> Atcud | None:
    """The first ATCUD QR code in ``images`` (pages rendered, or photos), if any can be read."""
    import zxingcpp

    for image in images:
        for result in zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.QRCode):
            found = parse(result.text)
            if found is not None:
                return found
    return None
