"""What a bill's text says, read by the parser for its supplier, or by the generic one.

A supplier's parser is chosen by the NIF its invoices carry. Each returns Findings with only what
it could read; the pipeline merges them with the QR code's fields, which win where both speak.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from .text import AMOUNT, DATE, after, cents, day, number, plain

#: A unit price, which can have more decimals than an amount: "0,1499".
PRICE = r"\d+[.,]\d+"


@dataclass
class Reading:
    """A quantity a bill measures, electricity in kWh or water in m³, and its unit price."""

    quantity: str
    value: float
    unit_price: float | None = None


@dataclass
class Findings:
    """What a parser read from a bill's text."""

    invoice_number: str | None = None
    on: date | None = None
    total_cents: int | None = None
    period_start: date | None = None
    period_end: date | None = None
    due_date: date | None = None
    #: The bill's parts as (description, cents), when the supplier itemises them.
    lines: list[tuple[str, int]] = field(default_factory=list)
    readings: list[Reading] = field(default_factory=list)
    #: The service's references the bill prints, such as {"CPE": "PT0002…"}.
    identifiers: dict[str, str] = field(default_factory=dict)
    ends_on: date | None = None
    renews_automatically: bool | None = None
    lock_in_until: date | None = None


def _date_after(text: str, label: str) -> date | None:
    found = after(text, label, DATE)
    return day(found) if found else None


def _cents_after(text: str, label: str) -> int | None:
    found = after(text, label, AMOUNT)
    return cents(found) if found else None


def generic(text: str) -> Findings:
    """What most Portuguese invoices say in words alike: their number, date, total and due date."""
    flat = plain(text)
    number_match = re.search(
        r"fatura(?:\s+n\.?\s*o?)?\s*[:.]?\s*((?:ft|fa|fr)[\w ./-]{3,30}?)(?:\s+de\s|\n)", flat
    )
    found = Findings()
    if number_match:
        found.invoice_number = number_match.group(1).strip().upper()
    found.on = _date_after(text, r"data (?:de|da) (?:emissao|fatura)") or _date_after(
        text, r"fatura[^\n]*?\bde\b"
    )
    found.total_cents = _cents_after(text, r"total a pagar") or _cents_after(text, r"valor a pagar")
    found.due_date = _date_after(text, r"data limite de pagamento") or _date_after(
        text, r"a partir de"
    )
    period = re.search(rf"periodo de faturacao[^\n\d]*({DATE})\s*a\s*({DATE})", flat)
    if period:
        found.period_start, found.period_end = day(period.group(1)), day(period.group(2))
    return found


def meo_energia(text: str) -> Findings:
    """MEO Energia's electricity bill: also its consumption and price, CPE and contract term."""
    found = generic(text)
    flat = plain(text)
    consumption = re.search(rf"consumo em \w+[^\n]*?({AMOUNT})\s*\(kwh\)[^\n]*?€\s*({PRICE})", flat)
    if consumption:
        kwh = number(consumption.group(1))
        if kwh is not None:
            found.readings.append(Reading("electricity_kwh", kwh, number(consumption.group(2))))
    cpe = re.search(r"\b(pt\d{16}[a-z]{2})\b", flat)
    if cpe:
        found.identifiers["CPE"] = cpe.group(1).upper()
    term = re.search(rf"termina a ({DATE})\s*(\(renovacao automatica\))?", flat)
    if term:
        found.ends_on = day(term.group(1))
        found.renews_automatically = term.group(2) is not None
    lock_in = re.search(rf"fidelizacao:\s*(?:ate\s*)?({DATE})", flat)
    if lock_in:
        found.lock_in_until = day(lock_in.group(1))
    return found


#: MEO's telecom invoice groups its items under these headings, each with a "Total …" line.
MEO_GROUPS = (("pacotes", "Package"), ("telemovel", "Mobile"), ("adesoes", "Activation"),
              ("equipamentos", "Equipment"))  # fmt: skip


def meo(text: str) -> Findings:
    """MEO's telecom invoice: also its groups of items as lines, and the lock-in it reports."""
    found = generic(text)
    flat = plain(text)
    total = _cents_after(text, r"total da fatura[^\n]*?arredondado[^\n]*?")
    found.total_cents = total or found.total_cents
    for heading, label in MEO_GROUPS:
        match = re.search(rf"total {heading[:4]}\w*\s*€?\s*({AMOUNT})", flat)
        amount = cents(match.group(1)) if match else None
        if amount:
            found.lines.append((label, amount))
    lock_in = re.search(rf"fideliza\w*\s+a decorrer[^\n]*?ate\s+({DATE})", flat)
    if lock_in:
        found.lock_in_until = day(lock_in.group(1))
    service = re.search(r"servico\s+(\d{8,12})", flat)
    if service:
        found.identifiers["Serviço"] = service.group(1)
    return found


#: The parser for each supplier whose bills are read in full, by NIF.
BY_NIF: dict[str, Callable[[str], Findings]] = {
    "506743357": meo_energia,
    "504615947": meo,
}


def parse(text: str, nif: str | None) -> Findings:
    """The findings of the supplier's own parser, or of the generic one."""
    return BY_NIF.get(nif or "", generic)(text)
