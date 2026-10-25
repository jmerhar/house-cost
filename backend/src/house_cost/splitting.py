"""Which rule splits a cost, and the shares it gives each household."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Household, SplitRule
from .money import allocate


class NoRule(LookupError):
    """No rule for the category is in force on the date, so the cost cannot be split."""

    def __init__(self, category_id: int, on: date) -> None:
        super().__init__(f"category {category_id} has no rule in force on {on.isoformat()}")
        self.category_id = category_id
        self.on = on


@dataclass(frozen=True)
class Share:
    """One household's part of a cost."""

    household_id: int
    amount_cents: int


async def rule_in_force(session: AsyncSession, category_id: int, on: date) -> SplitRule:
    """The category's rule with the latest effective date on or before ``on``.

    A rule effective on 1 January splits a bill dated 1 January; the rule before it splits one
    dated 31 December.
    """
    rule = (
        await session.execute(
            select(SplitRule)
            .where(SplitRule.category_id == category_id, SplitRule.effective_from <= on)
            .order_by(SplitRule.effective_from.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if rule is None:
        raise NoRule(category_id, on)
    return rule


async def households_in_order(session: AsyncSession) -> list[Household]:
    """Every household, in the order that decides who gets a contested rounding cent."""
    return list(
        (await session.execute(select(Household).order_by(Household.position, Household.id)))
        .scalars()
        .all()
    )


def split(
    amount_cents: int, basis_points: dict[int, int], households: Sequence[Household]
) -> list[Share]:
    """Split an amount by shares in basis points, keyed by household id.

    Every household in ``households`` gets a share, zero for one the shares do not name; a
    household named in the shares but missing from ``households`` is an error, since its share
    would otherwise go unpaid.
    """
    known = {household.id for household in households}
    unknown = set(basis_points) - known
    if unknown:
        raise ValueError(f"shares name unknown households: {sorted(unknown)}")
    weights = [basis_points.get(household.id, 0) for household in households]
    parts = allocate(amount_cents, weights)
    return [Share(household.id, part) for household, part in zip(households, parts, strict=True)]


def rule_weights(rule: SplitRule) -> dict[int, int]:
    """A rule's shares, as basis points keyed by household id."""
    return {share.household_id: share.basis_points for share in rule.shares}
