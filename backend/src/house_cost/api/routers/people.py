"""Households and the people in them. Anyone may list them; only an admin changes them."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ... import contacts
from ...audit import record
from ...auth import end_sessions, hash_password
from ...models import Household, Person, Role
from ..deps import AdminDep, DbDep, PersonDep, ServicesDep, get_or_404
from ..schemas import (
    HouseholdIn,
    HouseholdOut,
    PersonDetail,
    PersonIn,
    PersonOut,
    PersonUpdate,
)

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


def person_detail(person: Person, viewer: Person) -> PersonDetail:
    """``person`` as ``viewer`` may see them: with contacts for an admin or themselves."""
    out = PersonDetail.model_validate(PersonOut.model_validate(person), from_attributes=True)
    if viewer.is_admin or viewer.id == person.id:
        out.email, out.phone = person.email, person.phone
    return out


def set_contacts(person: Person, email: str | None, phone: str | None, country: str) -> None:
    """Set the contacts given, checked and normalised; None leaves one as it is."""
    try:
        if email is not None:
            person.email = contacts.email(email)
        if phone is not None:
            person.phone = contacts.phone(phone, country)
    except contacts.InvalidContact as invalid:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, invalid.code) from None


@router.get("/people")
async def list_people(db: DbDep, viewer: PersonDep) -> list[PersonDetail]:
    """Everyone who can log in, by name."""
    rows = await db.execute(select(Person).order_by(Person.name, Person.id))
    return [person_detail(row, viewer) for row in rows.scalars()]


async def _require_household(db: AsyncSession, household_id: int) -> None:
    if await db.get(Household, household_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_household")


@router.post("/people", status_code=status.HTTP_201_CREATED)
async def create_person(
    body: PersonIn, admin: AdminDep, db: DbDep, services: ServicesDep
) -> PersonDetail:
    """Give someone a login, with a first password they can change themselves."""
    await _require_household(db, body.household_id)
    fields = body.model_dump(exclude={"password", "email", "phone"})
    person = Person(**fields, password_hash=hash_password(body.password))
    set_contacts(person, body.email, body.phone, services.settings.phone_country_code)
    db.add(person)
    await _flush_unique(db, "login_taken")
    record(db, admin, "create", "person", person.id, after=PersonOut.model_validate(person))
    return person_detail(person, admin)


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
    person_id: int, body: PersonUpdate, admin: AdminDep, db: DbDep, services: ServicesDep
) -> PersonDetail:
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
    for key, value in body.model_dump(exclude={"password", "email", "phone"}).items():
        setattr(person, key, value)
    set_contacts(person, body.email, body.phone, services.settings.phone_country_code)
    if body.password is not None:
        person.password_hash = hash_password(body.password)
    if body.password is not None or not body.active:
        await end_sessions(db, person.id)
    await _flush_unique(db, "login_taken")
    out = PersonOut.model_validate(person)
    record(db, admin, "update", "person", person.id, before=before, after=out)
    return person_detail(person, admin)
