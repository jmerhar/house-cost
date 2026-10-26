"""The endpoint the container's health check calls."""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from ... import __version__
from ..deps import DbDep, ServicesDep

router = APIRouter(tags=["health"])


class Health(BaseModel):
    """The application's state as the health check sees it."""

    status: str
    database: str
    version: str
    #: The commit the running image was built from, when it was built by CI.
    revision: str | None


@router.get("/health")
async def health(db: DbDep, services: ServicesDep) -> Health:
    """Report that the process is up and its database answers.

    Unauthenticated, and it queries the database rather than returning a constant: a container
    that answers while its database cannot be opened is not healthy.
    """
    await db.execute(text("SELECT 1"))
    return Health(
        status="ok",
        database="connected",
        version=__version__,
        revision=services.settings.revision,
    )
