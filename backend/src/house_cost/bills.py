"""Splitting a bill's lines, and the periods closed reconciliations have locked."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .audit import get_setting
from .models import Bill, BillLine, BillLineShare, Category, Household, Reconciliation
from .models import ReconciliationStatus as Status
from .splitting import Share, rule_in_force, rule_weights, split


@dataclass(frozen=True)
class LineDraft:
    """A line as it was asked for: an existing line's id, or None for a new one."""

    id: int | None
    description: str
    category_id: int
    amount_cents: int


class UnknownLine(LookupError):
    """A line id that does not belong to the bill being changed."""


class UnknownCategory(LookupError):
    """A line names a category that does not exist."""


async def locked_periods(db: AsyncSession) -> list[tuple[date, date]]:
    """The periods of closed reconciliations, whose bills cannot change.

    None while reconciliation is switched off, when closed reconciliations have no effect.
    """
    if not await get_setting(db, "reconciliation_enabled"):
        return []
    rows = await db.execute(
        select(Reconciliation.period_start, Reconciliation.period_end).where(
            Reconciliation.status == Status.CLOSED
        )
    )
    return [(start, end) for start, end in rows.all()]


def is_locked(on: date, periods: Sequence[tuple[date, date]]) -> bool:
    """Whether a date falls within one of ``periods``."""
    return any(start <= on <= end for start, end in periods)


async def set_lines(
    db: AsyncSession,
    bill: Bill,
    drafts: Sequence[LineDraft],
    households: Sequence[Household],
    *,
    date_changed: bool,
) -> None:
    """Make ``drafts`` the bill's lines, and its total their sum.

    A draft naming an existing line keeps that line's shares and rule when its category and
    amount are unchanged and the bill's date is the same, so a rule added since does not quietly
    re-split a bill someone only corrected the description of. Anything else is split afresh by
    the rule in force on the bill's date.
    """
    existing = {line.id: line for line in bill.lines}
    lines: list[BillLine] = []
    for position, draft in enumerate(drafts):
        if await db.get(Category, draft.category_id) is None:
            raise UnknownCategory(draft.category_id)
        if draft.id is not None:
            if draft.id not in existing:
                raise UnknownLine(draft.id)
            line = existing[draft.id]
            unchanged = (
                not date_changed
                and line.category_id == draft.category_id
                and line.amount_cents == draft.amount_cents
            )
        else:
            line = BillLine()
            unchanged = False
        line.position = position
        line.description = draft.description
        if not unchanged:
            rule = await rule_in_force(db, draft.category_id, bill.date)
            line.category_id = draft.category_id
            line.amount_cents = draft.amount_cents
            line.rule_id = rule.id
            _replace_shares(line, split(draft.amount_cents, rule_weights(rule), households))
        lines.append(line)
    bill.lines = lines
    bill.total_cents = sum(line.amount_cents for line in lines)


def _replace_shares(line: BillLine, shares: Sequence[Share]) -> None:
    """Give ``line`` exactly these shares, updating rows in place.

    A share's key is its line and household, so dropping a row and adding one for the same
    household in a single flush would insert the new row before deleting the old one and break
    that key.
    """
    current = {share.household_id: share for share in line.shares}
    kept = []
    for share in shares:
        row = current.pop(share.household_id, None)
        if row is None:
            row = BillLineShare(household_id=share.household_id)
        row.amount_cents = share.amount_cents
        kept.append(row)
    line.shares = kept
