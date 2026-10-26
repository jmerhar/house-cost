"""Reading a bill: its QR code, its text (by OCR where the text layer fails), its supplier's parser.

The result says where each value came from, so a person checking the proposal knows which values
the invoice's fiscal QR code vouches for and which were read from the page.
"""

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ..claude import BillRead, cents_or_none, day_or_none
from . import atcud, ocr
from .parsers import BY_NIF, Findings, parse
from .text import nifs

#: Pages rendered for the QR code (it is on the first page or two) and read by OCR.
QR_PAGES = 2
OCR_PAGES = 6
QR_SCALE = 200 / 72
OCR_SCALE = 300 / 72


@dataclass
class Extraction:
    """What was read from a bill, and where from: "qr", "text", "ocr" for each field read."""

    findings: Findings
    issuer_nif: str | None = None
    #: How the text was got: "text" (the PDF's own), "ocr", or "none".
    text_source: str = "none"
    sources: dict[str, str] = field(default_factory=dict)
    #: Disagreements worth a look: "total_mismatch" when the QR code and the page differ.
    warnings: list[str] = field(default_factory=list)
    #: The issuer's name, when only Claude gave one.
    supplier_name: str | None = None


def _pdf_pages(path: Path, scale: float, count: int) -> list[Image.Image]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(path)
    try:
        return [document[i].render(scale=scale).to_pil() for i in range(min(count, len(document)))]
    finally:
        document.close()


def _text(path: Path, content_type: str) -> tuple[str, str, list[Image.Image]]:
    """The bill's text, how it was got, and the images to look for a QR code in.

    Each page of a PDF keeps its own text unless that is missing or garbled, when the page is read
    by OCR instead: one invoice can mix clean pages with a scrambled one.
    """
    if content_type == "application/pdf":
        from .pdf import read_text

        own = read_text(path).pages
        qr_images = _pdf_pages(path, QR_SCALE, QR_PAGES)
        poor = [i for i, page in enumerate(own[:OCR_PAGES]) if ocr.unusable(page)]
        if not poor:
            return "\n\f".join(own), "text", qr_images
        rendered = _pdf_pages(path, OCR_SCALE, max(poor) + 1)
        pages = [_ocr(rendered[i]) if i in poor else text for i, text in enumerate(own)]
        return "\n\f".join(pages), "ocr", qr_images
    try:
        image = Image.open(path)
        image.load()
    except UnidentifiedImageError, OSError:
        return "", "none", []
    return _ocr(image), "ocr", [image]


def _ocr(image: Image.Image) -> str:
    """OCR of one image; nothing when Tesseract is not installed, so a bill still gets its QR
    code and whatever text it carries."""
    try:
        return ocr.read(image)
    except ocr.OcrUnavailable:
        return ""


def extract(path: Path, content_type: str, known_nifs: set[str]) -> Extraction:
    """Read the bill at ``path``.

    ``known_nifs`` are the suppliers on file: without a QR code, the first of them the text
    mentions is taken to be the issuer, which picks the parser.
    """
    text, text_source, qr_images = _text(path, content_type)
    code = atcud.find(qr_images) if qr_images else None
    issuer = code.issuer_nif if code else next(iter(sorted(nifs(text) & known_nifs)), None)
    findings = parse(text, issuer) if text.strip() else Findings()
    extraction = Extraction(findings=findings, issuer_nif=issuer, text_source=text_source)
    page = "ocr" if text_source == "ocr" else "text"
    for name in ("invoice_number", "on", "total_cents", "period_start", "period_end", "due_date",
                 "ends_on", "lock_in_until"):  # fmt: skip
        if getattr(findings, name) is not None:
            extraction.sources[name] = page
    if findings.lines:
        extraction.sources["lines"] = page
    if findings.readings:
        extraction.sources["readings"] = page
    if code is not None:
        _vouch(extraction, code)
    _balance(extraction)
    return extraction


def _vouch(extraction: Extraction, code: atcud.Atcud) -> None:
    """Take the QR code's date, number and total over the page's, noting a total that differs."""
    findings = extraction.findings
    if code.total_cents is not None:
        if findings.total_cents is not None and findings.total_cents != code.total_cents:
            extraction.warnings.append("total_mismatch")
        findings.total_cents = code.total_cents
        extraction.sources["total_cents"] = "qr"
    if code.on is not None:
        findings.on = code.on
        extraction.sources["on"] = "qr"
    if code.number:
        findings.invoice_number = code.number
        extraction.sources["invoice_number"] = "qr"


def _balance(extraction: Extraction) -> None:
    """Make itemised lines add up to the total, as the bill's own rounding does.

    A supplier that prints its items to a tenth of a cent rounds only the total, so the items'
    rounded amounts can miss it by a cent or two; the difference goes on the first line. A gap
    larger than that means the items were misread, and they are dropped.
    """
    findings = extraction.findings
    if not findings.lines or findings.total_cents is None:
        return
    gap = findings.total_cents - sum(amount for _, amount in findings.lines)
    if abs(gap) > len(findings.lines):
        findings.lines = []
        extraction.sources.pop("lines", None)
        extraction.warnings.append("lines_dropped")
        return
    description, amount = findings.lines[0]
    findings.lines[0] = (description, amount + gap)


#: The fields Claude may fill in, by Findings attribute and BillRead attribute.
CLAUDE_DATES = {"on": "date", "period_start": "period_start", "period_end": "period_end",
                "due_date": "due_date"}  # fmt: skip


def worth_asking_claude(extraction: Extraction) -> bool:
    """Whether Claude could add to what was read: no supplier's parser knows the issuer, or the
    date, number or total is missing."""
    findings = extraction.findings
    known = extraction.issuer_nif in BY_NIF
    return not known or None in (findings.on, findings.invoice_number, findings.total_cents)


def merge_claude(extraction: Extraction, read: BillRead) -> None:
    """Fill what the QR code and the page left empty with what Claude read, marked "claude".

    Nothing already read is replaced: the QR code is vouched for, and the page is what a person
    can check against the file.
    """
    findings = extraction.findings
    sources = extraction.sources
    if findings.invoice_number is None and read.invoice_number:
        findings.invoice_number = read.invoice_number.strip()
        sources["invoice_number"] = "claude"
    if findings.total_cents is None and (total := cents_or_none(read.total)) is not None:
        findings.total_cents = total
        sources["total_cents"] = "claude"
    for name, field_name in CLAUDE_DATES.items():
        value = day_or_none(getattr(read, field_name))
        if getattr(findings, name) is None and value is not None:
            setattr(findings, name, value)
            sources[name] = "claude"
    nif = (read.supplier_nif or "").replace(" ", "")
    if extraction.issuer_nif is None and len(nif) == 9 and nif.isdigit():
        extraction.issuer_nif = nif
        sources["issuer_nif"] = "claude"
    if read.supplier_name:
        extraction.supplier_name = read.supplier_name.strip()
    lines = [(line.description.strip(), cents_or_none(line.amount)) for line in read.lines]
    if not findings.lines and lines and all(amount is not None for _, amount in lines):
        findings.lines = [(description, amount) for description, amount in lines if amount]
        sources["lines"] = "claude"
        _balance(extraction)
