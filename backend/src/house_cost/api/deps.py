"""Request dependencies and the services the application holds for its lifetime."""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ..auth import LoginThrottle, find_session
from ..claude import Claude
from ..config import Settings
from ..db import create_engine, create_sessionmaker, session_scope
from ..models import Person, Session
from ..notify import AppriseSender, Sender
from ..passkeys import Ceremonies
from ..scheduler import Scheduler

#: The cookie a browser's session token travels in.
SESSION_COOKIE = "hc_session"


@dataclass
class Services:
    """What the application builds once at startup and closes at shutdown."""

    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]
    throttle: LoginThrottle
    sender: Sender
    scheduler: Scheduler
    #: Present only when an Anthropic API key is set.
    claude: Claude | None = None
    #: Passkey challenges waiting for the authenticator's answer.
    ceremonies: Ceremonies = field(default_factory=Ceremonies)
    #: Held while the first administrator is created, so two browsers racing through setup
    #: cannot both become one.
    setup_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def build_services(settings: Settings) -> Services:
    """Build the services for ``settings``. Opens no connection until one is used."""
    engine = create_engine(settings)
    sessionmaker = create_sessionmaker(engine)
    sender = AppriseSender()
    return Services(
        settings=settings,
        engine=engine,
        sessionmaker=sessionmaker,
        throttle=LoginThrottle(settings.login_attempts_per_minute),
        sender=sender,
        scheduler=Scheduler(settings, engine, sessionmaker, sender),
        claude=Claude(key, settings.claude_model) if (key := settings.claude_key) else None,
    )


def get_services(request: Request) -> Services:
    """The services the running application was started with."""
    return request.app.state.services


def get_claude(request: Request) -> Claude:
    """Claude, for the routes that need it; without an API key they answer 404."""
    claude = get_services(request).claude
    if claude is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "claude_off")
    return claude


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """A session for one request, committed when the handler succeeds and rolled back if not."""
    async with session_scope(get_services(request).sessionmaker) as session:
        yield session


ServicesDep = Annotated[Services, Depends(get_services)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
ClaudeDep = Annotated[Claude, Depends(get_claude)]


async def get_session(request: Request, db: DbDep) -> Session:
    """The browser's live session; without one the request is refused with 401."""
    token = request.cookies.get(SESSION_COOKIE)
    session = await find_session(db, token) if token else None
    if session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    return session


SessionDep = Annotated[Session, Depends(get_session)]


async def get_person(session: SessionDep) -> Person:
    """The person logged in."""
    return session.person


PersonDep = Annotated[Person, Depends(get_person)]


async def get_admin(person: PersonDep) -> Person:
    """The person logged in, who must be an administrator."""
    if not person.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin_only")
    return person


AdminDep = Annotated[Person, Depends(get_admin)]


async def get_or_404[T](db: AsyncSession, model: type[T], ident: int) -> T:
    """The row of ``model`` with primary key ``ident``, or a 404."""
    row = await db.get(model, ident)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return row
