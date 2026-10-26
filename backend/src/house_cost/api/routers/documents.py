"""The document library: contracts, terms, the signed agreement, leaflets; found by their text."""

import asyncio
import logging
from typing import Annotated
from urllib.parse import quote

import pypdfium2 as pdfium
from fastapi import APIRouter, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import record
from ...extraction.pdf import read_text
from ...models import Document, Service, Supplier
from ...storage import TooLarge, path_for, save, sniff
from ..deps import DbDep, PersonDep, ServicesDep, get_or_404
from ..schemas import DocumentKind, DocumentMatch, DocumentOut, DocumentUpdate
from .attachments import SANDBOX, clean_name, held

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

#: How much text on either side of a search match an excerpt shows.
EXCERPT = 80


def document_out(document: Document) -> DocumentOut:
    """A document as the API returns it, without its full text."""
    return DocumentOut.model_validate(document)


def _excerpt(text: str, query: str) -> str:
    """The text around the first match of ``query``, on one line."""
    at = text.lower().find(query.lower())
    if at < 0:
        return ""
    start, end = max(at - EXCERPT, 0), min(at + len(query) + EXCERPT, len(text))
    snippet = " ".join(text[start:end].split())
    return ("…" if start else "") + snippet + ("…" if end < len(text) else "")


async def _links(db: AsyncSession, supplier_id: int | None, service_id: int | None) -> None:
    if supplier_id is not None and await db.get(Supplier, supplier_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_supplier")
    if service_id is not None and await db.get(Service, service_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_service")


@router.get("")
async def list_documents(
    db: DbDep,
    q: str | None = Query(None, max_length=100),
    kind: DocumentKind | None = None,
    supplier_id: int | None = None,
    service_id: int | None = None,
) -> list[DocumentMatch]:
    """Documents newest first, narrowed by kind, supplier, service, and words in their title,
    notes, file name or text."""
    conditions = []
    if kind is not None:
        conditions.append(Document.kind == kind)
    if supplier_id is not None:
        conditions.append(Document.supplier_id == supplier_id)
    if service_id is not None:
        conditions.append(Document.service_id == service_id)
    query = (q or "").strip()
    if query:
        pattern = f"%{query}%"
        conditions.append(
            or_(
                Document.title.ilike(pattern),
                Document.notes.ilike(pattern),
                Document.filename.ilike(pattern),
                Document.text.ilike(pattern),
            )
        )
    rows = await db.execute(
        select(Document)
        .where(*conditions)
        .order_by(
            func.coalesce(Document.dated, func.date(Document.created_at)).desc(), Document.id.desc()
        )
    )
    return [
        DocumentMatch(
            **document_out(row).model_dump(),
            excerpt=_excerpt(row.text, query) if query else "",
        )
        for row in rows.scalars()
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile,
    person: PersonDep,
    db: DbDep,
    services: ServicesDep,
    title: Annotated[str, Form(min_length=1, max_length=300)],
    kind: Annotated[DocumentKind, Form()] = "other",
    dated: Annotated[str | None, Form()] = None,
    supplier_id: Annotated[int | None, Form()] = None,
    service_id: Annotated[int | None, Form()] = None,
    notes: Annotated[str, Form(max_length=2000)] = "",
) -> DocumentOut:
    """Keep a PDF or a photo in the library; a PDF's text is read so it can be searched."""
    try:
        meta = DocumentUpdate(
            title=title,
            kind=kind,
            dated=dated or None,
            supplier_id=supplier_id,
            service_id=service_id,
            notes=notes,
        )
    except ValidationError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid") from None
    await _links(db, meta.supplier_id, meta.service_id)
    root = services.settings.files_dir
    try:
        sha256, size, head = await save(root, file, services.settings.max_upload_bytes)
    except TooLarge:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "too_large") from None
    content_type = sniff(head)
    if content_type is None:
        if not await held(db, sha256):
            path_for(root, sha256).unlink(missing_ok=True)
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported_file")
    text, pages = "", None
    if content_type == "application/pdf":
        try:
            read = await asyncio.to_thread(read_text, path_for(root, sha256))
            text, pages = read.text, len(read.pages)
        except pdfium.PdfiumError:
            # Kept all the same: a PDF PDFium cannot read still opens in most viewers.
            logger.warning("could not read the text of %s", sha256)
    document = Document(
        **meta.model_dump(),
        filename=clean_name(file.filename),
        content_type=content_type,
        size=size,
        sha256=sha256,
        text=text,
        pages=pages,
        created_by_id=person.id,
    )
    db.add(document)
    await db.flush()
    out = document_out(document)
    record(db, person, "create", "document", document.id, after=out)
    return out


@router.get("/{document_id}")
async def get_document(document_id: int, db: DbDep) -> DocumentOut:
    """One document's details."""
    return document_out(await get_or_404(db, Document, document_id))


@router.get("/{document_id}/file", response_class=FileResponse)
async def download(document_id: int, db: DbDep, services: ServicesDep) -> FileResponse:
    """The document's file, shown in the browser where it can be, under the same sandbox as an
    attachment."""
    document = await get_or_404(db, Document, document_id)
    path = path_for(services.settings.files_dir, document.sha256)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file_missing")
    return FileResponse(
        path,
        media_type=document.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(document.filename)}",
            "Content-Security-Policy": SANDBOX,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.put("/{document_id}")
async def update_document(
    document_id: int, body: DocumentUpdate, person: PersonDep, db: DbDep
) -> DocumentOut:
    """Change a document's title, kind, date, links or notes."""
    document = await get_or_404(db, Document, document_id)
    await _links(db, body.supplier_id, body.service_id)
    before = document_out(document)
    for key, value in body.model_dump().items():
        setattr(document, key, value)
    out = document_out(document)
    record(db, person, "update", "document", document.id, before=before, after=out)
    return out


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: int, person: PersonDep, db: DbDep) -> None:
    """Remove a document from the library. Its bytes stay on disk, as an attachment's do."""
    document = await get_or_404(db, Document, document_id)
    record(db, person, "delete", "document", document.id, before=document_out(document))
    await db.delete(document)
