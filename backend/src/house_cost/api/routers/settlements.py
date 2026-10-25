"""Settlements: money one household sent another to settle up."""

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import extract, select

from ...audit import record
from ...models import Household, Settlement, utcnow
from ..deps import DbDep, PersonDep, get_or_404
from ..schemas import SettlementIn, SettlementOut

router = APIRouter(prefix="/settlements", tags=["settlements"])


async def _live(db, settlement_id: int) -> Settlement:
    settlement = await get_or_404(db, Settlement, settlement_id)
    if settlement.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return settlement


async def _check_households(db, body: SettlementIn) -> None:
    for household_id in (body.from_id, body.to_id):
        if await db.get(Household, household_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_household")


@router.get("")
async def list_settlements(
    db: DbDep,
    year: int | None = None,
    limit: int = Query(200, ge=1, le=1000),
) -> list[SettlementOut]:
    """Settlements not deleted, newest first."""
    conditions = [Settlement.deleted_at.is_(None)]
    if year is not None:
        conditions.append(extract("year", Settlement.date) == year)
    rows = await db.execute(
        select(Settlement)
        .where(*conditions)
        .order_by(Settlement.date.desc(), Settlement.id.desc())
        .limit(limit)
    )
    return [SettlementOut.model_validate(row) for row in rows.scalars()]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_settlement(body: SettlementIn, person: PersonDep, db: DbDep) -> SettlementOut:
    """Record a transfer between two households."""
    await _check_households(db, body)
    settlement = Settlement(**body.model_dump(), created_by_id=person.id, attachments=[])
    db.add(settlement)
    await db.flush()
    out = SettlementOut.model_validate(settlement)
    record(db, person, "create", "settlement", settlement.id, after=out)
    return out


@router.put("/{settlement_id}")
async def update_settlement(
    settlement_id: int, body: SettlementIn, person: PersonDep, db: DbDep
) -> SettlementOut:
    """Correct a recorded transfer."""
    settlement = await _live(db, settlement_id)
    await _check_households(db, body)
    before = SettlementOut.model_validate(settlement)
    for key, value in body.model_dump().items():
        setattr(settlement, key, value)
    await db.flush()
    await db.refresh(settlement)
    out = SettlementOut.model_validate(settlement)
    record(db, person, "update", "settlement", settlement.id, before=before, after=out)
    return out


@router.delete("/{settlement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_settlement(settlement_id: int, person: PersonDep, db: DbDep) -> None:
    """Delete a recorded transfer. It is only marked, and stays in the audit log."""
    settlement = await _live(db, settlement_id)
    record(
        db,
        person,
        "delete",
        "settlement",
        settlement.id,
        before=SettlementOut.model_validate(settlement),
    )
    settlement.deleted_at = utcnow()
