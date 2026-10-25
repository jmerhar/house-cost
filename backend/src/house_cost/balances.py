"""What each household has paid and owes, and the transfers that would settle everyone up."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Adjustment,
    Bill,
    BillLine,
    BillLineShare,
    Reconciliation,
    ReconciliationStatus,
    Settlement,
)
from .splitting import households_in_order


@dataclass(frozen=True)
class HouseholdBalance:
    """One household's position, in cents.

    ``balance`` is what the others owe it: positive means it is owed money, negative that it owes.
    """

    household_id: int
    name: str
    paid_cents: int
    share_cents: int
    adjustment_cents: int
    sent_cents: int
    received_cents: int

    @property
    def balance_cents(self) -> int:
        """Paid, less its share and adjustments, plus what it sent, less what it received."""
        return (
            self.paid_cents
            - self.share_cents
            - self.adjustment_cents
            + self.sent_cents
            - self.received_cents
        )


@dataclass(frozen=True)
class Transfer:
    """A payment from one household to another that would settle part of the balances."""

    from_id: int
    to_id: int
    amount_cents: int


async def balances(session: AsyncSession, *, include_adjustments: bool) -> list[HouseholdBalance]:
    """Every household's balance over all bills and settlements not deleted.

    Adjustments from closed reconciliations count only when ``include_adjustments`` is set,
    which follows whether reconciliation is switched on.
    """

    async def totals(statement) -> dict[int, int]:
        return dict((await session.execute(statement)).all())

    live_bill = Bill.deleted_at.is_(None)
    paid = await totals(
        select(Bill.paid_by_id, func.sum(Bill.total_cents))
        .where(live_bill)
        .group_by(Bill.paid_by_id)
    )
    shares = await totals(
        select(BillLineShare.household_id, func.sum(BillLineShare.amount_cents))
        .join(BillLine, BillLine.id == BillLineShare.line_id)
        .join(Bill, Bill.id == BillLine.bill_id)
        .where(live_bill)
        .group_by(BillLineShare.household_id)
    )
    live_settlement = Settlement.deleted_at.is_(None)
    sent = await totals(
        select(Settlement.from_id, func.sum(Settlement.amount_cents))
        .where(live_settlement)
        .group_by(Settlement.from_id)
    )
    received = await totals(
        select(Settlement.to_id, func.sum(Settlement.amount_cents))
        .where(live_settlement)
        .group_by(Settlement.to_id)
    )
    adjustments: dict[int, int] = {}
    if include_adjustments:
        adjustments = await totals(
            select(Adjustment.household_id, func.sum(Adjustment.amount_cents))
            .join(Reconciliation, Reconciliation.id == Adjustment.reconciliation_id)
            .where(Reconciliation.status == ReconciliationStatus.CLOSED)
            .group_by(Adjustment.household_id)
        )

    return [
        HouseholdBalance(
            household_id=household.id,
            name=household.name,
            paid_cents=paid.get(household.id, 0),
            share_cents=shares.get(household.id, 0),
            adjustment_cents=adjustments.get(household.id, 0),
            sent_cents=sent.get(household.id, 0),
            received_cents=received.get(household.id, 0),
        )
        for household in await households_in_order(session)
    ]


def settle(positions: list[HouseholdBalance]) -> list[Transfer]:
    """Transfers that bring every balance to zero, few of them and largest first.

    Repeatedly pays the largest creditor from the largest debtor. Each step clears at least one
    of the two, so n households need at most n - 1 transfers. Ties go to the household listed
    first, so the suggestion is the same every time it is asked for.
    """
    creditors = [[p.balance_cents, i, p.household_id] for i, p in enumerate(positions)]
    debtors = [[-c[0], c[1], c[2]] for c in creditors if c[0] < 0]
    creditors = [c for c in creditors if c[0] > 0]
    transfers: list[Transfer] = []
    while creditors and debtors:
        creditors.sort(key=lambda c: (-c[0], c[1]))
        debtors.sort(key=lambda d: (-d[0], d[1]))
        creditor, debtor = creditors[0], debtors[0]
        amount = min(creditor[0], debtor[0])
        transfers.append(Transfer(from_id=debtor[2], to_id=creditor[2], amount_cents=amount))
        creditor[0] -= amount
        debtor[0] -= amount
        creditors = [c for c in creditors if c[0] > 0]
        debtors = [d for d in debtors if d[0] > 0]
    return transfers
