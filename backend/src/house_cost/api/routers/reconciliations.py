"""Annual reconciliation, for admins. Absent altogether (404) while the setting is off."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from ...audit import get_setting, record
from ...models import (
    Adjustment,
    Category,
    Household,
    Reconciliation,
    ReconciliationShare,
    ReconciliationStatus,
    utcnow,
)
from ...reconciliation import reconcile
from ..deps import AdminDep, DbDep, get_or_404, get_person
from ..schemas import (
    ReconciliationIn,
    ReconciliationLine,
    ReconciliationOut,
    ReconciliationShareIn,
)


async def _enabled(db: DbDep) -> None:
    if not await get_setting(db, "reconciliation_enabled"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")


# The session, which app.py requires of this router, is checked before the setting, so without one
# every route answers 401 alike and whether reconciliation is on is not given away.
router = APIRouter(
    prefix="/reconciliations",
    tags=["reconciliations"],
    dependencies=[Depends(get_person), Depends(_enabled)],
)


async def _out(db, reconciliation: Reconciliation) -> ReconciliationOut:
    positions, bills = await reconcile(db, reconciliation)
    if reconciliation.status == ReconciliationStatus.CLOSED:
        # A closed reconciliation reports what it wrote, which later edits cannot change.
        written = {a.household_id: a.amount_cents for a in reconciliation.adjustments}
        lines = [
            ReconciliationLine(
                household_id=p.household_id,
                charged_cents=p.charged,
                reconciled_cents=p.charged + written.get(p.household_id, 0),
                adjustment_cents=written.get(p.household_id, 0),
            )
            for p in positions
        ]
    else:
        lines = [
            ReconciliationLine(
                household_id=p.household_id,
                charged_cents=p.charged,
                reconciled_cents=p.reconciled,
                adjustment_cents=p.adjustment,
            )
            for p in positions
        ]
    return ReconciliationOut(
        id=reconciliation.id,
        period_start=reconciliation.period_start,
        period_end=reconciliation.period_end,
        status=reconciliation.status,
        note=reconciliation.note,
        shares=[
            ReconciliationShareIn(
                category_id=s.category_id, household_id=s.household_id, basis_points=s.basis_points
            )
            for s in sorted(reconciliation.shares, key=lambda s: (s.category_id, s.household_id))
        ],
        closed_at=reconciliation.closed_at,
        lines=lines,
        bill_count=bills,
    )


async def _check(db, body: ReconciliationIn, own_id: int | None) -> None:
    """The categories and households exist, and the period overlaps no closed reconciliation."""
    for share in body.shares:
        if await db.get(Category, share.category_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_category")
        if await db.get(Household, share.household_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_household")
    overlapping = await db.execute(
        select(Reconciliation.id).where(
            Reconciliation.status == ReconciliationStatus.CLOSED,
            Reconciliation.period_start <= body.period_end,
            Reconciliation.period_end >= body.period_start,
            Reconciliation.id != (own_id or 0),
        )
    )
    if overlapping.first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "overlaps_closed_period")


def _shares(body: ReconciliationIn) -> list[ReconciliationShare]:
    return [
        ReconciliationShare(
            category_id=s.category_id, household_id=s.household_id, basis_points=s.basis_points
        )
        for s in body.shares
        if s.basis_points > 0
    ]


async def _draft(db, reconciliation_id: int) -> Reconciliation:
    reconciliation = await get_or_404(db, Reconciliation, reconciliation_id)
    if reconciliation.status != ReconciliationStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "already_closed")
    return reconciliation


@router.get("")
async def list_reconciliations(db: DbDep) -> list[ReconciliationOut]:
    """Every reconciliation, latest period first."""
    rows = await db.execute(select(Reconciliation).order_by(Reconciliation.period_start.desc()))
    return [await _out(db, row) for row in rows.scalars()]


@router.get("/{reconciliation_id}")
async def get_reconciliation(reconciliation_id: int, db: DbDep) -> ReconciliationOut:
    """One reconciliation with each household's position; a draft's is worked out afresh."""
    return await _out(db, await get_or_404(db, Reconciliation, reconciliation_id))


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_reconciliation(
    body: ReconciliationIn, admin: AdminDep, db: DbDep
) -> ReconciliationOut:
    """Start a draft reconciliation of a period."""
    await _check(db, body, None)
    reconciliation = Reconciliation(
        period_start=body.period_start,
        period_end=body.period_end,
        note=body.note,
        created_by_id=admin.id,
        shares=_shares(body),
        adjustments=[],
    )
    db.add(reconciliation)
    await db.flush()
    out = await _out(db, reconciliation)
    record(db, admin, "create", "reconciliation", reconciliation.id, after=out)
    return out


@router.put("/{reconciliation_id}")
async def update_reconciliation(
    reconciliation_id: int, body: ReconciliationIn, admin: AdminDep, db: DbDep
) -> ReconciliationOut:
    """Change a draft's period, note or reconciled shares."""
    reconciliation = await _draft(db, reconciliation_id)
    await _check(db, body, reconciliation.id)
    before = await _out(db, reconciliation)
    reconciliation.period_start = body.period_start
    reconciliation.period_end = body.period_end
    reconciliation.note = body.note
    reconciliation.shares = []
    await db.flush()
    reconciliation.shares = _shares(body)
    await db.flush()
    out = await _out(db, reconciliation)
    record(db, admin, "update", "reconciliation", reconciliation.id, before=before, after=out)
    return out


@router.post("/{reconciliation_id}/close")
async def close_reconciliation(
    reconciliation_id: int, admin: AdminDep, db: DbDep
) -> ReconciliationOut:
    """Close a draft: write each household's adjustment and lock the period's bills."""
    reconciliation = await _draft(db, reconciliation_id)
    body = ReconciliationIn(
        period_start=reconciliation.period_start,
        period_end=reconciliation.period_end,
        shares=[],
    )
    await _check(db, body, reconciliation.id)
    positions, _ = await reconcile(db, reconciliation)
    reconciliation.adjustments = [
        Adjustment(household_id=p.household_id, amount_cents=p.adjustment)
        for p in positions
        if p.adjustment
    ]
    reconciliation.status = ReconciliationStatus.CLOSED
    reconciliation.closed_at = utcnow()
    reconciliation.closed_by_id = admin.id
    await db.flush()
    out = await _out(db, reconciliation)
    record(db, admin, "close", "reconciliation", reconciliation.id, after=out)
    return out


@router.delete("/{reconciliation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reconciliation(reconciliation_id: int, admin: AdminDep, db: DbDep) -> None:
    """Discard a draft. A closed reconciliation is final."""
    reconciliation = await _draft(db, reconciliation_id)
    record(
        db,
        admin,
        "delete",
        "reconciliation",
        reconciliation.id,
        before=await _out(db, reconciliation),
    )
    await db.delete(reconciliation)
