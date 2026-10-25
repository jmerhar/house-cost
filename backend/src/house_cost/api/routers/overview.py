"""Balances, the yearly summary and its CSV export, the audit log, and the app's settings."""

import csv
import io
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy import extract, func, select

from ...audit import get_setting, record, set_setting
from ...balances import balances, settle
from ...models import AuditEvent, Bill, BillLine, BillLineShare, Category, Person
from ...splitting import households_in_order
from ..deps import AdminDep, DbDep
from ..schemas import (
    AuditOut,
    AuditPage,
    BalanceOut,
    Balances,
    CategoryTotal,
    HouseholdAmount,
    MonthTotal,
    SettingsIn,
    SettingsOut,
    Summary,
    TransferOut,
)

router = APIRouter(tags=["overview"])


@router.get("/balances")
async def get_balances(db: DbDep) -> Balances:
    """Every household's balance, and the transfers that would settle them."""
    positions = await balances(
        db, include_adjustments=await get_setting(db, "reconciliation_enabled")
    )
    return Balances(
        households=[
            BalanceOut(
                household_id=p.household_id,
                name=p.name,
                paid_cents=p.paid_cents,
                share_cents=p.share_cents,
                adjustment_cents=p.adjustment_cents,
                sent_cents=p.sent_cents,
                received_cents=p.received_cents,
                balance_cents=p.balance_cents,
            )
            for p in positions
        ],
        transfers=[
            TransferOut(from_id=t.from_id, to_id=t.to_id, amount_cents=t.amount_cents)
            for t in settle(positions)
        ],
    )


async def _years(db) -> list[int]:
    rows = await db.execute(
        select(func.distinct(extract("year", Bill.date))).where(Bill.deleted_at.is_(None))
    )
    return sorted({int(year) for year in rows.scalars()}, reverse=True)


@router.get("/reports/summary")
async def summary(db: DbDep, year: int | None = None) -> Summary:
    """A year's costs by category and by month, each with every household's share.

    Without a year, the latest year that has bills, or this one.
    """
    years = await _years(db)
    year = year or (years[0] if years else date.today().year)
    households = [h.id for h in await households_in_order(db)]
    rows = await db.execute(
        select(
            BillLine.category_id,
            Category.name,
            extract("month", Bill.date),
            BillLineShare.household_id,
            func.sum(BillLineShare.amount_cents),
        )
        .join(Bill, Bill.id == BillLine.bill_id)
        .join(Category, Category.id == BillLine.category_id)
        .join(BillLineShare, BillLineShare.line_id == BillLine.id)
        .where(Bill.deleted_at.is_(None), extract("year", Bill.date) == year)
        .group_by(
            BillLine.category_id,
            Category.name,
            extract("month", Bill.date),
            BillLineShare.household_id,
        )
    )
    by_category: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    names: dict[int, str] = {}
    by_month: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for category_id, name, month, household_id, cents in rows.all():
        names[category_id] = name
        by_category[category_id][household_id] += cents
        by_month[int(month)][household_id] += cents

    def amounts(totals: dict[int, int]) -> list[HouseholdAmount]:
        return [HouseholdAmount(household_id=h, amount_cents=totals.get(h, 0)) for h in households]

    overall: dict[int, int] = defaultdict(int)
    for totals in by_category.values():
        for household_id, cents in totals.items():
            overall[household_id] += cents
    return Summary(
        year=year,
        years=years,
        total_cents=sum(overall.values()),
        shares=amounts(overall),
        categories=sorted(
            (
                CategoryTotal(
                    category_id=category_id,
                    name=names[category_id],
                    total_cents=sum(totals.values()),
                    shares=amounts(totals),
                )
                for category_id, totals in by_category.items()
            ),
            key=lambda c: (-c.total_cents, c.name),
        ),
        months=[
            MonthTotal(month=month, total_cents=sum(totals.values()), shares=amounts(totals))
            for month, totals in sorted(by_month.items())
        ],
    )


def _euros(cents: int) -> str:
    """Cents as a plain decimal a spreadsheet reads in any locale: 1235 → "12.35"."""
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


@router.get("/reports/bills.csv", response_class=Response)
async def bills_csv(db: DbDep, year: int | None = None) -> Response:
    """Every bill line of a year (or of all years), one row each, with each household's share."""
    households = await households_in_order(db)
    conditions = [Bill.deleted_at.is_(None)]
    if year is not None:
        conditions.append(extract("year", Bill.date) == year)
    bills = (
        await db.execute(select(Bill).where(*conditions).order_by(Bill.date, Bill.id))
    ).scalars()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["date", "supplier", "description", "invoice", "category", "line", "amount", "paid by"]
        + [h.name for h in households]
    )
    payer = {h.id: h.name for h in households}
    for bill in bills:
        for line in bill.lines:
            shares = {s.household_id: s.amount_cents for s in line.shares}
            writer.writerow(
                [
                    bill.date.isoformat(),
                    bill.supplier,
                    bill.description,
                    bill.invoice_number or "",
                    line.category.name,
                    line.description,
                    _euros(line.amount_cents),
                    payer[bill.paid_by_id],
                ]
                + [_euros(shares.get(h.id, 0)) for h in households]
            )
    name = f"bills-{year}.csv" if year else "bills.csv"
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/audit")
async def audit_log(
    db: DbDep,
    entity: str | None = None,
    entity_id: int | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> AuditPage:
    """Who changed what, newest first; open to everyone, so every change is visible to all."""
    conditions = []
    if entity is not None:
        conditions.append(AuditEvent.entity == entity)
    if entity_id is not None:
        conditions.append(AuditEvent.entity_id == entity_id)
    total = (await db.execute(select(func.count(AuditEvent.id)).where(*conditions))).scalar_one()
    rows = await db.execute(
        select(AuditEvent, Person.name)
        .outerjoin(Person, Person.id == AuditEvent.person_id)
        .where(*conditions)
        .order_by(AuditEvent.at.desc(), AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return AuditPage(
        items=[
            AuditOut(
                id=event.id,
                at=event.at,
                person_id=event.person_id,
                person_name=name,
                action=event.action,
                entity=event.entity,
                entity_id=event.entity_id,
                before=event.before,
                after=event.after,
            )
            for event, name in rows.all()
        ],
        total=total,
    )


@router.get("/settings")
async def get_settings(db: DbDep) -> SettingsOut:
    """The app's settings."""
    return SettingsOut(reconciliation_enabled=await get_setting(db, "reconciliation_enabled"))


@router.put("/settings")
async def put_settings(body: SettingsIn, admin: AdminDep, db: DbDep) -> SettingsOut:
    """Change the app's settings."""
    before = SettingsOut(reconciliation_enabled=await get_setting(db, "reconciliation_enabled"))
    await set_setting(db, "reconciliation_enabled", body.reconciliation_enabled)
    after = SettingsOut(reconciliation_enabled=body.reconciliation_enabled)
    record(db, admin, "update", "settings", None, before=before, after=after)
    return after
