"""First-run setup: the first administrator and their household.

Open to whoever arrives first while nobody exists, and closed for good once someone does. A new
deployment should therefore stay unreachable from outside until it has been set up.
"""

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import record
from ...auth import hash_password, open_session
from ...models import Household, Person, Role
from .. import session_cookie
from ..deps import DbDep, ServicesDep
from ..schemas import HouseholdOut, Me, PersonOut, SetupIn, SetupState

logger = logging.getLogger(__name__)
router = APIRouter(tags=["setup"])


async def setup_required(db: AsyncSession) -> bool:
    """Whether nobody exists yet, so the next visitor sets the app up."""
    return (await db.execute(select(func.count(Person.id)))).scalar_one() == 0


@router.get("/setup")
async def setup_state(db: DbDep) -> SetupState:
    """Whether the app still needs setting up."""
    return SetupState(required=await setup_required(db))


@router.post("/setup", status_code=status.HTTP_201_CREATED)
async def set_up(
    body: SetupIn, request: Request, response: Response, db: DbDep, services: ServicesDep
) -> Me:
    """Create the first household and its administrator, and log them in."""
    async with services.setup_lock:
        if not await setup_required(db):
            raise HTTPException(status.HTTP_409_CONFLICT, "already_set_up")
        household = Household(name=body.household_name, position=0)
        db.add(household)
        await db.flush()
        person = Person(
            name=body.name,
            login=body.login,
            password_hash=hash_password(body.password),
            role=Role.ADMIN,
            language=body.language,
            household_id=household.id,
        )
        db.add(person)
        await db.flush()
        await db.refresh(person, ["household"])
        record(
            db,
            person,
            "create",
            "household",
            household.id,
            after=HouseholdOut.model_validate(household),
        )
        record(db, person, "create", "person", person.id, after=PersonOut.model_validate(person))
        token = await open_session(db, person, request.headers.get("user-agent", ""))
        # Committed while still holding the lock, so a racing setup sees this person.
        await db.commit()
    logger.info("set up: %s is the first administrator", person.login)
    session_cookie.issue(response, request, services.settings, token)
    return await session_cookie.describe(
        db,
        person,
        services.claude is not None,
        services.notifier.channels,
        services.settings.phone_country_code,
    )
