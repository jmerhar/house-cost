"""PDFs made in the tests, standing in for real bills and contracts, which hold personal details
and stay out of the repository."""

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def pdf(*pages: list[str]) -> bytes:
    """A PDF with a text layer: each page's lines, top to bottom."""
    out = io.BytesIO()
    page = canvas.Canvas(out, pagesize=A4)
    for lines in pages:
        y = 800
        for line in lines:
            page.drawString(50, y, line)
            y -= 16
        page.showPage()
    page.save()
    return out.getvalue()


def image_only_pdf() -> bytes:
    """A PDF with a page and no text on it, as a scan is."""
    out = io.BytesIO()
    page = canvas.Canvas(out, pagesize=A4)
    page.rect(50, 50, 200, 200, fill=1)
    page.showPage()
    page.save()
    return out.getvalue()
