"""Reading amounts and dates out of a bill's text, as Portuguese bills write them."""

import re
import unicodedata
from datetime import date

#: Portuguese month names and their abbreviations, without accents, by number.
MONTHS = {
    "janeiro": 1, "jan": 1, "fevereiro": 2, "fev": 2, "marco": 3, "mar": 3, "abril": 4, "abr": 4,
    "maio": 5, "mai": 5, "junho": 6, "jun": 6, "julho": 7, "jul": 7, "agosto": 8, "ago": 8,
    "setembro": 9, "set": 9, "outubro": 10, "out": 10, "novembro": 11, "nov": 11,
    "dezembro": 12, "dez": 12,
}  # fmt: skip

#: An amount as bills print it: "322,69", "1 459,00", "1.234,56", "22.72", "0,805".
AMOUNT = r"-?\d{1,3}(?:[ . ]\d{3})*(?:[.,]\d{1,3})|-?\d+(?:[.,]\d{1,3})?"
#: A date as bills print it: "23/10/2026", "23-10-2026", "23 setembro 2026", "12 ago 2027".
DATE = r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}|\d{1,2}\s+(?:de\s+)?[a-zçã]{3,9}\.?\s+(?:de\s+)?\d{4}"


def plain(text: str) -> str:
    """Text lower-cased and without accents, with look-alike characters folded, so a pattern
    written once matches what OCR and a text layer both give.

    Some PDFs carry the euro sign as \x80, its Windows-1252 code, which reads as € here.
    """
    folded = unicodedata.normalize("NFKD", text.lower().replace("\x80", "€"))
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return folded.replace("º", "o").replace("°", "o")


def cents(text: str, decimals: int = 2) -> int | None:
    """An amount's text as cents, rounding a third decimal ("17,663" → 1766), or None."""
    value = text.replace(" ", " ").strip()
    negative = value.startswith("-")
    value = value.lstrip("-")
    match = re.fullmatch(r"(\d{1,3}(?:[ .]\d{3})+|\d+)(?:[.,](\d{1,3}))?", value)
    if not match:
        return None
    whole = int(re.sub(r"[ .]", "", match.group(1)))
    fraction = (match.group(2) or "").ljust(3, "0")
    thousandths = whole * 1000 + int(fraction)
    result = (thousandths + 5) // 10 if decimals == 2 else thousandths
    return -result if negative else result


def number(text: str) -> float | None:
    """A quantity's text as a number: "1 459,00" → 1459.0, "0,1499" → 0.1499."""
    value = text.replace(" ", " ").replace(" ", "")
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return float(value)
    except ValueError:
        return None


def day(text: str) -> date | None:
    """A date's text as a date, day first, or None."""
    value = plain(text).strip()
    numeric = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", value)
    try:
        if numeric:
            return date(int(numeric.group(3)), int(numeric.group(2)), int(numeric.group(1)))
        written = re.fullmatch(r"(\d{1,2})\s+(?:de\s+)?([a-z]{3,9})\.?\s+(?:de\s+)?(\d{4})", value)
        if written and written.group(2) in MONTHS:
            return date(int(written.group(3)), MONTHS[written.group(2)], int(written.group(1)))
    except ValueError:
        return None
    return None


def after(text: str, label: str, pattern: str = AMOUNT) -> str | None:
    """What follows ``label`` (a regex over the plain text) and matches ``pattern``, on the same
    line or the next one; None when the label is not there."""
    match = re.search(rf"{label}[^\n\d-]*(?:\n[^\n\d-]*)?({pattern})", plain(text))
    return match.group(1) if match else None


def nifs(text: str) -> set[str]:
    """Every nine-digit number in the text that could be a NIF ("NIPC 506 743 357")."""
    return {
        re.sub(r"\D", "", found) for found in re.findall(r"(?<!\d)\d{3} ?\d{3} ?\d{3}(?!\d)", text)
    }
