"""Splitting a period's bills again by reconciled shares, and the difference each household owes."""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Bill, Reconciliation
from .splitting import households_in_order, split


@dataclass(frozen=True)
class Position:
    """One household over a reconciliation's period, in cents.

    ``charged`` is what its bills' splits gave it in the reconciled categories, ``reconciled``
    what the reconciled shares give it; ``adjustment`` is the difference, positive when it owes
    more.
    """

    household_id: int
    charged: int
    reconciled: int

    @property
    def adjustment(self) -> int:
        """What the household owes on top of its bills' splits; negative when it is owed."""
        return self.reconciled - self.charged


async def reconcile(db: AsyncSession, reconciliation: Reconciliation) -> tuple[list[Position], int]:
    """Every household's position over the period, and how many bills it touches.

    Only lines in categories the reconciliation gives shares for are split again; the rest keep
    their split and do not count. The adjustments add up to zero, since both splits divide the
    same lines.
    """
    weights: dict[int, dict[int, int]] = defaultdict(dict)
    for share in reconciliation.shares:
        weights[share.category_id][share.household_id] = share.basis_points
    households = await households_in_order(db)
    charged: dict[int, int] = defaultdict(int)
    reconciled: dict[int, int] = defaultdict(int)
    bills = (
        await db.execute(
            select(Bill).where(
                Bill.deleted_at.is_(None),
                Bill.date >= reconciliation.period_start,
                Bill.date <= reconciliation.period_end,
            )
        )
    ).scalars()
    touched = 0
    for bill in bills:
        lines = [line for line in bill.lines if line.category_id in weights]
        touched += bool(lines)
        for line in lines:
            for share in line.shares:
                charged[share.household_id] += share.amount_cents
            for share in split(line.amount_cents, weights[line.category_id], households):
                reconciled[share.household_id] += share.amount_cents
    positions = [
        Position(household_id=h.id, charged=charged[h.id], reconciled=reconciled[h.id])
        for h in households
    ]
    return positions, touched
