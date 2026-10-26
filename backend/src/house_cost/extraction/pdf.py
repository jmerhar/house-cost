"""A PDF's text layer and its pages, read with PDFium."""

from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium


@dataclass(frozen=True)
class PdfText:
    """The text a PDF carries, page by page, and how many pages it has."""

    pages: list[str]

    @property
    def text(self) -> str:
        """Every page's text, a form feed between pages."""
        return "\f".join(self.pages)


def read_text(path: Path) -> PdfText:
    """The text layer of the PDF at ``path``.

    A scanned page has no text layer and reads as empty; a file PDFium cannot open raises
    pdfium.PdfiumError.
    """
    document = pdfium.PdfDocument(path)
    try:
        pages = []
        for index in range(len(document)):
            page = document[index]
            text_page = page.get_textpage()
            pages.append(text_page.get_text_range().replace("\r\n", "\n"))
            text_page.close()
            page.close()
        return PdfText(pages)
    finally:
        document.close()
