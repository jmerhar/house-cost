"""Reading a bill's file into a proposed bill, and the readings bills have measured."""

import asyncio
import re
import tempfile
from pathlib import Path

import pypdfium2 as pdfium
from fastapi import APIRouter, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...extraction.pipeline import Extraction, extract
from ...models import Attachment, Bill, BillReading, Service, Supplier
from ...storage import TooLarge, save, sniff
from ..deps import DbDep, ServicesDep
from ..schemas import Proposal, ProposedLine, ReadingIn, ReadingPoint, ServiceChanges

router = APIRouter(tags=["reading"])

#: How long reading one file may take; OCR of a long scan on a small server is the slow part.
READ_SECONDS = 180


def _same_number(a: str | None, b: str | None) -> bool:
    """Whether two invoice numbers are the same once spaces, dots and case are set aside:
    "FA MEA26/100 001" and the QR code's "FT FA.MEA26/100001" are not, but their tails are."""
    if not a or not b:
        return False

    def tail(number: str) -> str:
        return re.sub(r"[\s.]", "", number.upper()).split("/")[-1]

    return tail(a) == tail(b) and tail(a) != ""


async def _duplicate(db: AsyncSession, sha256: str, number: str | None, supplier: str | None):
    """A live bill this file or invoice is already entered as."""
    by_file = await db.execute(
        select(Attachment.bill_id)
        .join(Bill, Bill.id == Attachment.bill_id)
        .where(Attachment.sha256 == sha256, Bill.deleted_at.is_(None))
    )
    found = by_file.scalars().first()
    if found is not None or not number:
        return found
    candidates = await db.execute(
        select(Bill.id, Bill.invoice_number, Bill.supplier).where(
            Bill.deleted_at.is_(None), Bill.invoice_number.is_not(None)
        )
    )
    for bill_id, other, other_supplier in candidates.all():
        if _same_number(number, other) and (
            not supplier or not other_supplier or supplier == other_supplier
        ):
            return bill_id
    return None


def _service_for(services: list[Service], supplier: Supplier | None, identifiers: dict[str, str]):
    """The service a bill is for: one whose references the bill prints, else the supplier's only
    active service."""
    printed = {value.replace(" ", "").upper() for value in identifiers.values()}
    for service in services:
        if any(value.replace(" ", "").upper() in printed for value in service.identifiers.values()):
            return service
    if supplier is None:
        return None
    own = [s for s in services if s.supplier_id == supplier.id and s.active]
    return own[0] if len(own) == 1 else None


def _changes(service: Service | None, extraction: Extraction) -> ServiceChanges:
    """What the bill says about the contract that differs from the service on file."""
    findings = extraction.findings
    if service is None:
        return ServiceChanges()
    return ServiceChanges(
        ends_on=findings.ends_on
        if findings.ends_on and findings.ends_on != service.ends_on
        else None,
        renews_automatically=(
            findings.renews_automatically
            if findings.renews_automatically is not None
            and findings.renews_automatically != service.renews_automatically
            else None
        ),
        lock_in_until=(
            findings.lock_in_until
            if findings.lock_in_until and findings.lock_in_until != service.lock_in_until
            else None
        ),
    )


@router.post("/bills/read")
async def read_bill(file: UploadFile, db: DbDep, services: ServicesDep) -> Proposal:
    """Read a bill's PDF or photo into a proposed bill, which nothing saves until a person has
    checked it. The file is not kept; it is attached when the bill is saved."""
    with tempfile.TemporaryDirectory(prefix="read-") as scratch:
        root = Path(scratch)
        try:
            sha256, _, head = await save(root, file, services.settings.max_upload_bytes)
        except TooLarge:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "too_large") from None
        content_type = sniff(head)
        if content_type is None:
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported_file")
        suppliers = list((await db.execute(select(Supplier))).scalars())
        known = {s.nif for s in suppliers if s.nif}
        path = root / sha256[:2] / sha256
        try:
            extraction = await asyncio.wait_for(
                asyncio.to_thread(extract, path, content_type, known), READ_SECONDS
            )
        except TimeoutError:
            raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "read_timeout") from None
        except pdfium.PdfiumError, OSError, ValueError:
            # A file that passed the type check but cannot be opened: refused, not a crash.
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unreadable") from None

    findings = extraction.findings
    supplier = next((s for s in suppliers if s.nif and s.nif == extraction.issuer_nif), None)
    all_services = list((await db.execute(select(Service))).scalars())
    service = _service_for(all_services, supplier, findings.identifiers)
    category = (service.default_category_id if service else None) or (
        supplier.default_category_id if supplier else None
    )
    lines = [
        ProposedLine(description=d, amount_cents=c, category_id=category) for d, c in findings.lines
    ]
    if not lines and findings.total_cents is not None:
        lines = [
            ProposedLine(description="", amount_cents=findings.total_cents, category_id=category)
        ]
    return Proposal(
        supplier_id=supplier.id if supplier else None,
        supplier_name=supplier.name if supplier else None,
        issuer_nif=extraction.issuer_nif,
        service_id=service.id if service else None,
        date=findings.on,
        invoice_number=findings.invoice_number,
        total_cents=findings.total_cents,
        period_start=findings.period_start,
        period_end=findings.period_end,
        due_date=findings.due_date,
        lines=lines,
        readings=[
            ReadingIn(quantity=r.quantity, value=r.value, unit_price=r.unit_price)
            for r in findings.readings
        ],
        service_changes=_changes(service, extraction),
        sources=extraction.sources,
        warnings=extraction.warnings,
        text_source=extraction.text_source,
        duplicate_bill_id=await _duplicate(
            db, sha256, findings.invoice_number, supplier.name if supplier else None
        ),
    )


@router.get("/readings")
async def readings(db: DbDep, service_id: int | None = None) -> list[ReadingPoint]:
    """Every reading of bills not deleted, oldest first, optionally for one service."""
    conditions = [Bill.deleted_at.is_(None)]
    if service_id is not None:
        conditions.append(Bill.service_id == service_id)
    rows = await db.execute(
        select(BillReading, Bill)
        .join(Bill, Bill.id == BillReading.bill_id)
        .where(*conditions)
        .order_by(func.coalesce(Bill.period_end, Bill.date), Bill.id)
    )
    return [
        ReadingPoint(
            bill_id=bill.id,
            date=bill.date,
            period_start=bill.period_start,
            period_end=bill.period_end,
            service_id=bill.service_id,
            quantity=reading.quantity,
            value=reading.value,
            unit_price=reading.unit_price,
        )
        for reading, bill in rows.all()
    ]
