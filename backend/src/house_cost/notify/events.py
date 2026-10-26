"""What sets notifications off: a bill added, a price changed, a contract ending, a bill missing."""

import logging
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db import session_scope
from ..models import Bill, BillReading, Person, Service, Supplier
from . import Notifier, once
from .messages import day, days, every, money, price, within, word

logger = logging.getLogger(__name__)

#: How many days before a contract's end or lock-in people are reminded of it.
REMINDER_DAYS = (30, 7)
#: How late a regular bill may be before its absence is pointed out.
GRACE_DAYS = 7
#: Unit prices this close are the same price.
PRICE_TOLERANCE = 0.00005


async def _people(db: AsyncSession) -> list[Person]:
    return list((await db.execute(select(Person).where(Person.active))).scalars())


def _label(bill: Bill) -> str:
    """What a bill is called in a message: its supplier, else its description, else its category."""
    return bill.supplier or bill.description or (bill.lines[0].category.name if bill.lines else "")


async def bill_added(
    sessionmaker: async_sessionmaker[AsyncSession], notifier: Notifier, bill_id: int, actor_id: int
) -> None:
    """Tell the other households of a new bill, and everyone of a unit price it changed.

    Runs after the bill is saved and the request answered; a failure here is logged, as the bill
    itself is already safe.
    """
    try:
        async with session_scope(sessionmaker) as db:
            bill = await db.get(Bill, bill_id)
            actor = await db.get(Person, actor_id)
            if bill is None or actor is None:
                return
            people = await _people(db)
            others = [p for p in people if p.household_id != actor.household_id]

            def share(person: Person) -> int:
                return sum(
                    s.amount_cents
                    for line in bill.lines
                    for s in line.shares
                    if s.household_id == person.household_id
                )

            await notifier.send_to(
                others,
                "new_bill",
                "new_bill",
                lambda person, lang: {
                    "person": actor.name,
                    "supplier": _label(bill),
                    "date": day(bill.date, lang),
                    "amount": money(bill.total_cents, lang),
                    "share": money(share(person), lang),
                },
            )
            await _price_changes(db, notifier, bill, people)
    except Exception:  # noqa: BLE001 - see the docstring
        logger.exception("notifying of bill %s failed", bill_id)


async def _price_changes(
    db: AsyncSession, notifier: Notifier, bill: Bill, people: list[Person]
) -> None:
    """Tell everyone when a reading's unit price differs from the service's previous bill, naming
    the service's supplier."""
    if bill.service_id is None:
        return
    supplier = (
        await db.execute(select(Supplier.name).join(Service).where(Service.id == bill.service_id))
    ).scalar_one()
    for reading in bill.readings:
        if reading.unit_price is None:
            continue
        previous = (
            await db.execute(
                select(BillReading.unit_price)
                .join(Bill, Bill.id == BillReading.bill_id)
                .where(
                    Bill.service_id == bill.service_id,
                    Bill.deleted_at.is_(None),
                    Bill.id != bill.id,
                    Bill.date <= bill.date,
                    BillReading.quantity == reading.quantity,
                    BillReading.unit_price.is_not(None),
                )
                .order_by(Bill.date.desc(), Bill.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if previous is None or abs(previous - reading.unit_price) < PRICE_TOLERANCE:
            continue
        if not await once(db, f"price:{bill.id}:{reading.quantity}"):
            continue
        unit = "kWh" if reading.quantity == "electricity_kwh" else "m³"
        await notifier.send_to(
            people,
            "price_change",
            "price_change",
            lambda _person, lang, r=reading, old=previous, u=unit: {
                "supplier": supplier,
                "quantity": word(r.quantity, lang),
                "date": day(bill.date, lang),
                "new": price(r.unit_price, lang),
                "old": price(old, lang),
                "unit": u,
            },
        )


async def contract_reminders(db: AsyncSession, notifier: Notifier, today: date) -> None:
    """Remind everyone of contracts ending and lock-ins expiring, 30 and 7 days ahead.

    Each reminder is sent once. A service first seen inside the 7-day window gets only that
    reminder, not the 30-day one as well.
    """
    people = await _people(db)
    rows = await db.execute(select(Service, Supplier).join(Supplier).where(Service.active))
    for service, supplier in rows.all():
        for field, message in (("ends_on", "contract_ends"), ("lock_in_until", "lock_in_ends")):
            when: date | None = getattr(service, field)
            if when is None:
                continue
            left = (when - today).days
            due = [ahead for ahead in REMINDER_DAYS if 0 <= left <= ahead]
            if not due:
                continue
            keys = [f"{message}:{service.id}:{when.isoformat()}:{ahead}" for ahead in due]
            fresh = [await once(db, key) for key in keys]
            if not fresh[-1]:
                continue
            await notifier.send_to(
                people,
                "contract",
                message,
                lambda _person, lang, s=service, w=when, n=left, sup=supplier: {
                    "service": s.name,
                    "supplier": sup.name,
                    "when": within(n, lang),
                    "date": day(w, lang),
                    "ends": word("renews" if s.renews_automatically else "ends", lang),
                    "notice": (
                        days(s.notice_days, lang)
                        if s.notice_days is not None
                        else word("unknown", lang)
                    ),
                },
            )


async def missing_bills(db: AsyncSession, notifier: Notifier, today: date) -> None:
    """Point out a regular bill that has not come a week after it was due, once per gap."""
    people = await _people(db)
    rows = await db.execute(
        select(Service, Supplier, func.max(Bill.date))
        .join(Supplier, Supplier.id == Service.supplier_id)
        .join(Bill, (Bill.service_id == Service.id) & Bill.deleted_at.is_(None))
        .where(Service.active, Service.billed_every_days.is_not(None))
        .group_by(Service.id, Supplier.id)
    )
    for service, supplier, last in rows.all():
        if today <= last + timedelta(days=service.billed_every_days + GRACE_DAYS):
            continue
        if not await once(db, f"missing:{service.id}:{last.isoformat()}"):
            continue
        await notifier.send_to(
            people,
            "missing_bill",
            "missing_bill",
            lambda _person, lang, s=service, sup=supplier, d=last: {
                "supplier": sup.name,
                "service": s.name,
                "date": day(d, lang),
                "every": every(s.billed_every_days, lang),
            },
        )
