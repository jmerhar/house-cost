"""Reading text from images with Tesseract, and telling when a PDF's own text cannot be used.

Some PDFs carry a text layer in a font whose characters map to nonsense (MEO's telecom invoices
read as long runs of "d"), and a scan has none at all; OCR of the rendered page reads both.
"""

import functools
import io
import shutil
import subprocess

from PIL import Image

#: How long one page may take to read; a page that takes longer is skipped.
PAGE_SECONDS = 60
#: The languages read, in order of preference, when Tesseract has their data.
LANGUAGES = ("por", "eng")


class OcrUnavailable(RuntimeError):
    """Tesseract is not installed, so images cannot be read."""


@functools.cache
def languages() -> str:
    """The `-l` argument for the installed languages among LANGUAGES."""
    binary = shutil.which("tesseract")
    if binary is None:
        raise OcrUnavailable("tesseract is not installed")
    listed = subprocess.run(
        [binary, "--list-langs"], capture_output=True, text=True, timeout=30, check=False
    ).stdout.split()
    present = [language for language in LANGUAGES if language in listed]
    return "+".join(present or ["eng"])


def read(image: Image.Image) -> str:
    """The text Tesseract reads in ``image``; empty when it reads nothing or gives up."""
    binary = shutil.which("tesseract")
    if binary is None:
        raise OcrUnavailable("tesseract is not installed")
    png = io.BytesIO()
    image.convert("L").save(png, format="PNG")
    try:
        result = subprocess.run(
            [binary, "-", "-", "-l", languages(), "--psm", "3"],
            input=png.getvalue(),
            capture_output=True,
            timeout=PAGE_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ""
    return result.stdout.decode("utf-8", errors="replace")


def unusable(text: str) -> bool:
    """Whether a page's text layer is missing or garbled, so the page is better read by OCR.

    A page with next to no letters has no text layer, as a scan has none. Garbled text keeps the
    letters' count but not their mix: real Portuguese or English has about two vowels in five
    letters, while a scrambled font gives hardly any. A short page is judged only once it has
    enough letters for that mix to mean something.
    """
    letters = [c for c in text.lower() if c.isalpha()]
    if len(letters) < 5:
        return True
    if len(letters) < 40:
        return False
    vowels = sum(c in "aeiouáàâãéêíóôõú" for c in letters)
    return vowels / len(letters) < 0.2
