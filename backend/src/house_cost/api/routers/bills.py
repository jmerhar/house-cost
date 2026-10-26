"""Bills: entered and corrected by anyone, split line by line by the rules."""

from datetime import date

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import extract, func, or_, select

from ...audit import record
from ...bills import (
    LineDraft,
    UnknownCategory,
    UnknownLine,
    is_locked,
    locked_periods,
    set_lines,
)
from ...models import Bill, BillLine, BillReading, Household, Service, utcnow
from ...notify.events import bill_added
from ...splitting import NoRule, households_in_order
from ..deps import DbDep, PersonDep, ServicesDep, get_or_404
from ..schemas import BillIn, BillOut, BillPage

router = APIRouter(prefix="/bills", tags=["bills"])


def bill_out(bill: Bill, periods: list[tuple[date, date]]) -> BillOut:
    """A bill as the API returns it, marked locked when a closed reconciliation covers it."""
    return BillOut.model_validate(bill).model_copy(update={"locked": is_locked(bill.date, periods)})


async def _live_bill(db, bill_id: int) -> Bill:
    bill = await get_or_404(db, Bill, bill_id)
    if bill.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return bill


@router.get("")
async def list_bills(
    db: DbDep,
    year: int | None = None,
    category_id: int | None = None,
    paid_by_id: int | None = None,
    q: str | None = Query(None, max_length=100),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> BillPage:
    """Bills not deleted, newest first, optionally narrowed by year, category, payer or text."""
    conditions = [Bill.deleted_at.is_(None)]
    if year is not None:
        conditions.append(extract("year", Bill.date) == year)
    if paid_by_id is not None:
        conditions.append(Bill.paid_by_id == paid_by_id)
    if category_id is not None:
        conditions.append(
            Bill.id.in_(select(BillLine.bill_id).where(BillLine.category_id == category_id))
        )
    if q:
        pattern = f"%{q}%"
        conditions.append(
            or_(
                Bill.supplier.ilike(pattern),
                Bill.description.ilike(pattern),
                Bill.invoice_number.ilike(pattern),
                Bill.notes.ilike(pattern),
            )
        )
    total = (await db.execute(select(func.count(Bill.id)).where(*conditions))).scalar_one()
    rows = await db.execute(
        select(Bill)
        .where(*conditions)
        .order_by(Bill.date.desc(), Bill.id.desc())
        .limit(limit)
        .offset(offset)
    )
    periods = await locked_periods(db)
    return BillPage(items=[bill_out(bill, periods) for bill in rows.scalars()], total=total)


@router.get("/{bill_id}")
async def get_bill(bill_id: int, db: DbDep) -> BillOut:
    """One bill, with its lines, their shares and its attachments."""
    return bill_out(await _live_bill(db, bill_id), await locked_periods(db))


async def _apply(db, bill: Bill, body: BillIn, *, date_changed: bool) -> None:
    """Copy ``body`` onto ``bill`` and split its lines, turning a bad line into a 422."""
    if await db.get(Household, body.paid_by_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_household")
    if body.service_id is not None and await db.get(Service, body.service_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_service")
    for key, value in body.model_dump(exclude={"lines", "readings"}).items():
        setattr(bill, key, value)
    bill.readings = [BillReading(**reading.model_dump()) for reading in body.readings]
    drafts = [
        LineDraft(line.id, line.description, line.category_id, line.amount_cents)
        for line in body.lines
    ]
    try:
        await set_lines(db, bill, drafts, await households_in_order(db), date_changed=date_changed)
    except NoRule as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "no_rule") from exc
    except UnknownCategory as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_category") from exc
    except UnknownLine as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_line") from exc


def _refuse_if_locked(on: date, periods: list[tuple[date, date]]) -> None:
    if is_locked(on, periods):
        raise HTTPException(status.HTTP_409_CONFLICT, "period_closed")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_bill(
    body: BillIn, person: PersonDep, db: DbDep, services: ServicesDep, tasks: BackgroundTasks
) -> BillOut:
    """Enter a bill. Each line is split by its category's rule in force on the bill's date.

    Once it is saved, the other households hear of it, and everyone of a price it changed.
    """
    periods = await locked_periods(db)
    _refuse_if_locked(body.date, periods)
    bill = Bill(created_by_id=person.id, lines=[], attachments=[], readings=[])
    await _apply(db, bill, body, date_changed=True)
    db.add(bill)
    await db.flush()
    await db.refresh(bill)
    out = bill_out(bill, periods)
    record(db, person, "create", "bill", bill.id, after=out)
    # Background tasks can run before the request's own session closes, so the bill is
    # committed here for the notification's separate session to find.
    await db.commit()
    tasks.add_task(bill_added, services.sessionmaker, services.sender, bill.id, person.id)
    return out


@router.put("/{bill_id}")
async def update_bill(bill_id: int, body: BillIn, person: PersonDep, db: DbDep) -> BillOut:
    """Correct a bill. Lines whose category, amount and date are unchanged keep their split."""
    bill = await _live_bill(db, bill_id)
    periods = await locked_periods(db)
    _refuse_if_locked(bill.date, periods)
    _refuse_if_locked(body.date, periods)
    before = bill_out(bill, periods)
    await _apply(db, bill, body, date_changed=body.date != bill.date)
    await db.flush()
    await db.refresh(bill)
    out = bill_out(bill, periods)
    record(db, person, "update", "bill", bill.id, before=before, after=out)
    return out


@router.delete("/{bill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bill(bill_id: int, person: PersonDep, db: DbDep) -> None:
    """Delete a bill. It is only marked, and stays in the audit log."""
    bill = await _live_bill(db, bill_id)
    periods = await locked_periods(db)
    _refuse_if_locked(bill.date, periods)
    record(db, person, "delete", "bill", bill.id, before=bill_out(bill, periods))
    bill.deleted_at = utcnow()
