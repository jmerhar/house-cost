"""Categories, their split rules, and a preview of how a cost would be split."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError

from ...audit import record
from ...models import BillLine, Category, Household, SplitRule, SplitRuleShare
from ...splitting import NoRule, households_in_order, rule_in_force, rule_weights, split
from ..deps import AdminDep, DbDep, get_or_404
from ..schemas import (
    CategoryIn,
    CategoryOut,
    LineShare,
    RuleIn,
    RuleOut,
    SplitPreview,
)

router = APIRouter(tags=["categories"])


@router.get("/categories")
async def list_categories(db: DbDep) -> list[CategoryOut]:
    """Every category, by name."""
    rows = await db.execute(select(Category).order_by(Category.name))
    return [CategoryOut.model_validate(row) for row in rows.scalars()]


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(body: CategoryIn, admin: AdminDep, db: DbDep) -> CategoryOut:
    """Add a category. Nothing can be filed under it until it has a rule."""
    category = Category(**body.model_dump())
    db.add(category)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "name_taken") from None
    out = CategoryOut.model_validate(category)
    record(db, admin, "create", "category", category.id, after=out)
    return out


@router.put("/categories/{category_id}")
async def update_category(
    category_id: int, body: CategoryIn, admin: AdminDep, db: DbDep
) -> CategoryOut:
    """Rename, describe or deactivate a category."""
    category = await get_or_404(db, Category, category_id)
    before = CategoryOut.model_validate(category)
    for key, value in body.model_dump().items():
        setattr(category, key, value)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "name_taken") from None
    out = CategoryOut.model_validate(category)
    record(db, admin, "update", "category", category.id, before=before, after=out)
    return out


def _rule_out(rule: SplitRule, in_use: bool) -> RuleOut:
    return RuleOut.model_validate(rule).model_copy(update={"in_use": in_use})


async def _in_use(db, rule_id: int) -> bool:
    return bool(
        (await db.execute(select(exists().where(BillLine.rule_id == rule_id)))).scalar_one()
    )


@router.get("/rules")
async def list_rules(db: DbDep, category_id: int | None = None) -> list[RuleOut]:
    """Every rule, or one category's, oldest first."""
    statement = select(SplitRule).order_by(SplitRule.category_id, SplitRule.effective_from)
    if category_id is not None:
        statement = statement.where(SplitRule.category_id == category_id)
    used = set((await db.execute(select(BillLine.rule_id).distinct())).scalars().all())
    return [_rule_out(rule, rule.id in used) for rule in (await db.execute(statement)).scalars()]


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(body: RuleIn, admin: AdminDep, db: DbDep) -> RuleOut:
    """Add a rule for a category from a date. Bills already split keep their split."""
    await get_or_404(db, Category, body.category_id)
    for share in body.shares:
        if await db.get(Household, share.household_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_household")
    rule = SplitRule(
        category_id=body.category_id,
        effective_from=body.effective_from,
        note=body.note,
        created_by_id=admin.id,
        shares=[
            SplitRuleShare(household_id=s.household_id, basis_points=s.basis_points)
            for s in body.shares
            if s.basis_points > 0
        ],
    )
    db.add(rule)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "rule_exists_on_date") from None
    await db.refresh(rule, ["shares"])
    out = _rule_out(rule, False)
    record(db, admin, "create", "rule", rule.id, after=out)
    return out


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int, admin: AdminDep, db: DbDep) -> None:
    """Remove a rule entered by mistake; one that has split a bill cannot be removed."""
    rule = await get_or_404(db, SplitRule, rule_id)
    if await _in_use(db, rule_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "rule_in_use")
    record(db, admin, "delete", "rule", rule.id, before=_rule_out(rule, False))
    await db.delete(rule)


@router.get("/split-preview")
async def split_preview(
    db: DbDep,
    category_id: int,
    on: date,
    amount_cents: int = Query(ge=-100_000_000, le=100_000_000),
) -> SplitPreview:
    """How an amount in a category would be split on a date: what a bill line would get."""
    try:
        rule = await rule_in_force(db, category_id, on)
    except NoRule:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "no_rule") from None
    shares = split(amount_cents, rule_weights(rule), await households_in_order(db))
    return SplitPreview(
        rule_id=rule.id,
        shares=[
            LineShare(household_id=s.household_id, amount_cents=s.amount_cents) for s in shares
        ],
    )
