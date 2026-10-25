"""Households and the people in them. Anyone may list them; only an admin changes them."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import record
from ...auth import end_sessions, hash_password
from ...models import Household, Person, Role
from ..deps import AdminDep, DbDep, get_or_404
from ..schemas import HouseholdIn, HouseholdOut, PersonIn, PersonOut, PersonUpdate

router = APIRouter(tags=["people"])


async def _flush_unique(db: AsyncSession, conflict: str) -> None:
    """Flush, turning a uniqueness violation into a 409 named ``conflict``."""
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, conflict) from None


@router.get("/households")
async def list_households(db: DbDep) -> list[HouseholdOut]:
    """Every household, in their configured order."""
    rows = await db.execute(select(Household).order_by(Household.position, Household.id))
    return [HouseholdOut.model_validate(row) for row in rows.scalars()]


@router.post("/households", status_code=status.HTTP_201_CREATED)
async def create_household(body: HouseholdIn, admin: AdminDep, db: DbDep) -> HouseholdOut:
    """Add a household. It owes nothing until a rule gives it a share."""
    household = Household(**body.model_dump())
    db.add(household)
    await _flush_unique(db, "name_taken")
    out = HouseholdOut.model_validate(household)
    record(db, admin, "create", "household", household.id, after=out)
    return out


@router.put("/households/{household_id}")
async def update_household(
    household_id: int, body: HouseholdIn, admin: AdminDep, db: DbDep
) -> HouseholdOut:
    """Rename, reorder or deactivate a household. Its history stays as it is."""
    household = await get_or_404(db, Household, household_id)
    before = HouseholdOut.model_validate(household)
    for key, value in body.model_dump().items():
        setattr(household, key, value)
    await _flush_unique(db, "name_taken")
    out = HouseholdOut.model_validate(household)
    record(db, admin, "update", "household", household.id, before=before, after=out)
    return out


@router.get("/people")
async def list_people(db: DbDep) -> list[PersonOut]:
    """Everyone who can log in, by name."""
    rows = await db.execute(select(Person).order_by(Person.name, Person.id))
    return [PersonOut.model_validate(row) for row in rows.scalars()]


async def _require_household(db: AsyncSession, household_id: int) -> None:
    if await db.get(Household, household_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_household")


@router.post("/people", status_code=status.HTTP_201_CREATED)
async def create_person(body: PersonIn, admin: AdminDep, db: DbDep) -> PersonOut:
    """Give someone a login, with a first password they can change themselves."""
    await _require_household(db, body.household_id)
    fields = body.model_dump(exclude={"password"})
    person = Person(**fields, password_hash=hash_password(body.password))
    db.add(person)
    await _flush_unique(db, "login_taken")
    out = PersonOut.model_validate(person)
    record(db, admin, "create", "person", person.id, after=out)
    return out


async def _other_active_admins(db: AsyncSession, person_id: int) -> int:
    return (
        await db.execute(
            select(func.count(Person.id)).where(
                Person.role == Role.ADMIN, Person.active, Person.id != person_id
            )
        )
    ).scalar_one()


@router.put("/people/{person_id}")
async def update_person(
    person_id: int, body: PersonUpdate, admin: AdminDep, db: DbDep
) -> PersonOut:
    """Change someone's details, role or household, deactivate them, or reset their password.

    The last active admin cannot be demoted or deactivated, so the app always has one. A reset
    password or a deactivation ends the person's sessions.
    """
    person = await get_or_404(db, Person, person_id)
    await _require_household(db, body.household_id)
    losing_admin = (
        person.is_admin and person.active and (body.role != Role.ADMIN or not body.active)
    )
    if losing_admin and await _other_active_admins(db, person.id) == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "last_admin")
    before = PersonOut.model_validate(person)
    for key, value in body.model_dump(exclude={"password"}).items():
        setattr(person, key, value)
    if body.password is not None:
        person.password_hash = hash_password(body.password)
    if body.password is not None or not body.active:
        await end_sessions(db, person.id)
    await _flush_unique(db, "login_taken")
    out = PersonOut.model_validate(person)
    record(db, admin, "update", "person", person.id, before=before, after=out)
    return out
