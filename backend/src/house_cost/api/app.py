"""The application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from jigkit.web import health_router, install_security_headers, install_write_guard, mount_spa
from sqlalchemy import text

from .. import __version__
from ..auth import WRITE_HEADER_VALUE
from ..config import Settings, get_settings
from . import manifest
from .deps import build_services, get_person
from .routers import (
    account,
    attachments,
    bills,
    categories,
    documents,
    overview,
    passkeys,
    people,
    reading,
    reconciliations,
    services,
    settlements,
    setup,
)

logger = logging.getLogger(__name__)

API_PREFIX = "/api"

#: Routers open without a session (beside the health check): first-run setup, and logging in.
#: Their routes that act on an account ask for the session themselves.
PUBLIC_ROUTERS = (setup, account, passkeys)
#: Every other router, mounted so that each of its routes needs a session.
PROTECTED_ROUTERS = (
    people,
    categories,
    reading,
    bills,
    settlements,
    attachments,
    services,
    documents,
    overview,
    reconciliations,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application for ``settings``, or for the environment's when none are given."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        services = build_services(settings)
        app.state.services = services
        services.scheduler.start()
        try:
            yield
        finally:
            await services.scheduler.stop()
            await services.engine.dispose()

    app = FastAPI(
        title="House costs",
        summary="A shared house's running costs, split between households",
        version=__version__,
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.include_router(
        health_router(check_database, version=__version__, revision=settings.revision),
        prefix=API_PREFIX,
    )
    for module in PUBLIC_ROUTERS:
        app.include_router(module.router, prefix=API_PREFIX)
    for module in PROTECTED_ROUTERS:
        app.include_router(module.router, prefix=API_PREFIX, dependencies=[Depends(get_person)])
    # Every write needs the interface's header and, with an Origin, the app's own; with the
    # SameSite=Lax session cookie this is the second of two locks against cross-site writes.
    install_write_guard(
        app, value=WRITE_HEADER_VALUE, public_url=settings.public_url, prefix=API_PREFIX
    )
    install_security_headers(app)
    # Outside /api and before the interface's fallback, which would otherwise answer for it.
    app.include_router(manifest.router)
    mount_spa(app, settings.static_dir, api_prefix=API_PREFIX)
    return app


async def check_database(request: Request) -> None:
    """Run a trivial query, raising if the database cannot answer."""
    async with request.app.state.services.engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
