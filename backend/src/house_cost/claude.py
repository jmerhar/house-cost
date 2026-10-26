"""Claude, when an API key is set: reading bills no parser knows, a contract's terms, and
questions about a document.

Every answer is a proposal for a person to check, never saved by itself. Without a key none of
this exists: the routes answer 404 and the interface shows nothing of it.
"""

import base64
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation

import anthropic
import httpx2
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

#: How long one request to Claude may take.
TIMEOUT_SECONDS = 150
MAX_TOKENS = 8000

LANGUAGE_NAMES = {"en": "English", "pt-PT": "European Portuguese"}


class ClaudeFailed(Exception):
    """Claude gave no usable answer: ``code`` is "claude_declined" or "claude_failed"."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class LineRead(BaseModel):
    description: str
    amount: str = Field(description="In euros with a decimal point, such as 12.34")


class BillRead(BaseModel):
    """What Claude read from a bill. Dates are YYYY-MM-DD and amounts euros with a decimal
    point, as text, so a misread value is dropped rather than refusing the whole answer."""

    supplier_name: str | None = None
    supplier_nif: str | None = Field(None, description="The issuer's 9-digit Portuguese NIF")
    invoice_number: str | None = None
    date: str | None = Field(None, description="The invoice date, YYYY-MM-DD")
    period_start: str | None = Field(None, description="Start of the billed period, YYYY-MM-DD")
    period_end: str | None = Field(None, description="End of the billed period, YYYY-MM-DD")
    due_date: str | None = Field(None, description="Payment due date, YYYY-MM-DD")
    total: str | None = Field(None, description="Total to pay in euros, such as 322.69")
    lines: list[LineRead] = Field(
        default_factory=list,
        description="The bill's parts with their amounts including VAT, adding up to the total",
    )


class TermsRead(BaseModel):
    """What Claude read from a contract or its terms."""

    service_name: str | None = Field(None, description="What is contracted, such as Internet")
    supplier_name: str | None = None
    starts_on: str | None = Field(None, description="YYYY-MM-DD")
    ends_on: str | None = Field(None, description="When the contract ends or renews, YYYY-MM-DD")
    renews_automatically: bool | None = None
    lock_in_until: str | None = Field(None, description="End of any lock-in period, YYYY-MM-DD")
    notice_days: int | None = Field(None, description="Days of notice needed to leave")
    billed_every_days: int | None = Field(None, description="Days between bills, such as 30")
    summary: str = Field(description="What a household sharing the cost should know, briefly")


class Citation(BaseModel):
    page: int | None
    quote: str


class Answer(BaseModel):
    text: str
    citations: list[Citation]


def day_or_none(value: str | None) -> date | None:
    """A YYYY-MM-DD date Claude wrote, or nothing when it wrote something else."""
    try:
        return date.fromisoformat(value.strip()) if value else None
    except ValueError:
        return None


def cents_or_none(value: str | None) -> int | None:
    """Euros Claude wrote ("322.69", "€ 1 234,50") as cents, or nothing when unreadable."""
    if not value:
        return None
    text = re.sub(r"[€\s]", "", value)
    if "," in text and "." in text:
        # Whichever comes last is the decimal separator; the other groups thousands.
        decimal_comma = text.rfind(",") > text.rfind(".")
        text = text.replace(".", "").replace(",", ".") if decimal_comma else text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        return int((Decimal(text) * 100).quantize(Decimal(1)))
    except InvalidOperation:
        return None


def _document(data: bytes, media_type: str, citations: bool = False) -> dict:
    """The file as a content block: a PDF as a document, a photo as an image."""
    encoded = base64.standard_b64encode(data).decode()
    if media_type == "application/pdf":
        block: dict = {
            "type": "document",
            "source": {"type": "base64", "media_type": media_type, "data": encoded},
        }
        if citations:
            block["citations"] = {"enabled": True}
        return block
    source = {"type": "base64", "media_type": media_type, "data": encoded}
    return {"type": "image", "source": source}


class Claude:
    """The calls the app makes to Claude, each one request for one file."""

    def __init__(
        self, api_key: str, model: str, http_client: httpx2.AsyncClient | None = None
    ) -> None:
        self.model = model
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key, timeout=TIMEOUT_SECONDS, http_client=http_client
        )

    async def _parse[T: BaseModel](self, content: list[dict], schema: type[T]) -> T:
        try:
            response = await self.client.messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": content}],
                output_format=schema,
            )
        except anthropic.APIError as error:
            logger.warning("Claude request failed: %s", type(error).__name__)
            raise ClaudeFailed("claude_failed") from error
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise ClaudeFailed("claude_declined")
        return response.parsed_output

    async def read_bill(self, data: bytes, media_type: str) -> BillRead:
        """The bill's issuer, number, dates, total and parts."""
        return await self._parse(
            [
                _document(data, media_type),
                {
                    "type": "text",
                    "text": "This is a utility or service bill for a house in Portugal. Read "
                    "what it states; leave out anything it does not show.",
                },
            ],
            BillRead,
        )

    async def read_terms(self, data: bytes, media_type: str, lang: str) -> TermsRead:
        """A contract's dates, lock-in and notice, and a summary in ``lang``."""
        return await self._parse(
            [
                _document(data, media_type),
                {
                    "type": "text",
                    "text": "This is a contract, or the terms of one, for a service at a house "
                    "in Portugal whose costs several households share. Read its dates, any "
                    "lock-in, the notice needed to leave and how often it bills; leave out "
                    "what it does not state. Write the summary in "
                    f"{LANGUAGE_NAMES.get(lang, 'English')}, in a few sentences: the price, "
                    "the lock-in and what leaving early costs.",
                },
            ],
            TermsRead,
        )

    async def ask(self, data: bytes, media_type: str, question: str, lang: str) -> Answer:
        """An answer to ``question`` from the document, citing the pages it rests on."""
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            _document(data, media_type, citations=True),
                            {
                                "type": "text",
                                "text": "Answer from this document only, briefly, in "
                                f"{LANGUAGE_NAMES.get(lang, 'English')}. If it does not say, "
                                f"say so.\n\n{question}",
                            },
                        ],
                    }
                ],
            )
        except anthropic.APIError as error:
            logger.warning("Claude request failed: %s", type(error).__name__)
            raise ClaudeFailed("claude_failed") from error
        if response.stop_reason == "refusal":
            raise ClaudeFailed("claude_declined")
        text, citations = [], []
        for block in response.content:
            if block.type != "text":
                continue
            text.append(block.text)
            for cited in block.citations or []:
                page = getattr(cited, "start_page_number", None)
                citations.append(Citation(page=page, quote=cited.cited_text.strip()))
        return Answer(text="".join(text).strip(), citations=citations)
