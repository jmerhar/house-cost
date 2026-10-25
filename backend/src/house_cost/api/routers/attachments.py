"""Files attached to bills and settlements: uploaded, downloaded, removed."""

from pathlib import PurePath
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import exists, select

from ...audit import record
from ...bills import is_locked, locked_periods
from ...models import Attachment, Bill, Settlement
from ...storage import TooLarge, path_for, save, sniff
from ..deps import DbDep, PersonDep, ServicesDep, get_or_404
from ..schemas import AttachmentOut

router = APIRouter(prefix="/attachments", tags=["attachments"])

#: The policy an attached file is served under: no script, no frames, nothing fetched from
#: elsewhere, so a file shown in the browser cannot act in the app's origin.
SANDBOX = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"


def _clean_name(name: str | None) -> str:
    """The upload's own file name without any directory part, never empty."""
    base = PurePath((name or "").replace("\\", "/")).name.strip()
    return base[:255] or "file"


async def _owner(db, bill_id: int | None, settlement_id: int | None) -> Bill | Settlement:
    if (bill_id is None) == (settlement_id is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "one_owner")
    owner = (
        await db.get(Bill, bill_id)
        if bill_id is not None
        else await db.get(Settlement, settlement_id)
    )
    if owner is None or owner.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return owner


async def _referenced(db, sha256: str) -> bool:
    return (await db.execute(select(exists().where(Attachment.sha256 == sha256)))).scalar_one()


async def _refuse_if_locked(db, owner: Bill | Settlement) -> None:
    if isinstance(owner, Bill) and is_locked(owner.date, await locked_periods(db)):
        raise HTTPException(status.HTTP_409_CONFLICT, "period_closed")


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(
    file: UploadFile,
    person: PersonDep,
    db: DbDep,
    services: ServicesDep,
    bill_id: int | None = Form(None),
    settlement_id: int | None = Form(None),
) -> AttachmentOut:
    """Attach a PDF or a photo (JPEG, PNG, WebP, HEIC) to a bill or a settlement."""
    owner = await _owner(db, bill_id, settlement_id)
    await _refuse_if_locked(db, owner)
    try:
        sha256, size, head = await save(
            services.settings.files_dir, file, services.settings.max_upload_bytes
        )
    except TooLarge:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "too_large") from None
    content_type = sniff(head)
    if content_type is None:
        # Removed again, unless an attachment already holds the same bytes.
        if not await _referenced(db, sha256):
            path_for(services.settings.files_dir, sha256).unlink(missing_ok=True)
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "unsupported_file")
    attachment = Attachment(
        bill_id=bill_id,
        settlement_id=settlement_id,
        filename=_clean_name(file.filename),
        content_type=content_type,
        size=size,
        sha256=sha256,
        created_by_id=person.id,
    )
    db.add(attachment)
    await db.flush()
    out = AttachmentOut.model_validate(attachment)
    entity, entity_id = ("bill", bill_id) if bill_id is not None else ("settlement", settlement_id)
    record(db, person, "attach", entity, entity_id, after=out)
    return out


@router.get("/{attachment_id}", response_class=FileResponse)
async def download(attachment_id: int, db: DbDep, services: ServicesDep) -> FileResponse:
    """The attached file itself, shown in the browser where it can be.

    Served with a sandboxing content security policy and no type sniffing, so even a file that
    slipped past the type check cannot run script in the app's origin.
    """
    attachment = await get_or_404(db, Attachment, attachment_id)
    path = path_for(services.settings.files_dir, attachment.sha256)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file_missing")
    return FileResponse(
        path,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(attachment.filename)}",
            "Content-Security-Policy": SANDBOX,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(attachment_id: int, person: PersonDep, db: DbDep) -> None:
    """Detach a file. Its bytes stay on disk, so the audit log's record of it still points at it."""
    attachment = await get_or_404(db, Attachment, attachment_id)
    owner = await _owner(db, attachment.bill_id, attachment.settlement_id)
    await _refuse_if_locked(db, owner)
    entity, entity_id = (
        ("bill", attachment.bill_id)
        if attachment.bill_id is not None
        else ("settlement", attachment.settlement_id)
    )
    record(db, person, "detach", entity, entity_id, before=AttachmentOut.model_validate(attachment))
    await db.delete(attachment)
