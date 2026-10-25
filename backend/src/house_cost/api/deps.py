"""Request dependencies and the services the application holds for its lifetime."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ..config import Settings
from ..db import create_engine, create_sessionmaker, session_scope


@dataclass
class Services:
    """What the application builds once at startup and closes at shutdown."""

    settings: Settings
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]


def build_services(settings: Settings) -> Services:
    """Build the services for ``settings``. Opens no connection until one is used."""
    engine = create_engine(settings)
    return Services(settings=settings, engine=engine, sessionmaker=create_sessionmaker(engine))


def get_services(request: Request) -> Services:
    """The services the running application was started with."""
    return request.app.state.services


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """A session for one request, committed when the handler succeeds and rolled back if not."""
    async with session_scope(get_services(request).sessionmaker) as session:
        yield session


ServicesDep = Annotated[Services, Depends(get_services)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
