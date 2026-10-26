"""The application factory."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..auth import WRITE_HEADER, WRITE_HEADER_VALUE, origin_allowed
from ..config import Settings, get_settings
from . import manifest
from .deps import build_services, get_person
from .routers import (
    account,
    attachments,
    bills,
    categories,
    documents,
    health,
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

#: Built assets carry a content hash in their names, so a browser may keep them for good.
IMMUTABLE = "public, max-age=31536000, immutable"

#: Methods that change something, which only the app's own interface may send.
WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Routers open without a session: the health check, first-run setup, and logging in. Their
#: routes that act on an account ask for the session themselves.
PUBLIC_ROUTERS = (health, setup, account, passkeys)
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
    for module in PUBLIC_ROUTERS:
        app.include_router(module.router, prefix=API_PREFIX)
    for module in PROTECTED_ROUTERS:
        app.include_router(module.router, prefix=API_PREFIX, dependencies=[Depends(get_person)])
    _guard_writes(app, settings)
    # Outside /api and before the interface's fallback, which would otherwise answer for it.
    app.include_router(manifest.router)
    _mount_frontend(app, settings.static_dir)
    return app


def _guard_writes(app: FastAPI, settings: Settings) -> None:
    """Refuse a write under /api unless it plainly comes from the app's own interface.

    Every write must carry the custom write header, which a page on another site cannot add
    without a CORS preflight the app never grants, and any Origin it has must be the app's own.
    The session cookie is SameSite=Lax as well, so this is the second of two locks.
    """

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method in WRITES and request.url.path.startswith(f"{API_PREFIX}/"):
            if request.headers.get(WRITE_HEADER) != WRITE_HEADER_VALUE:
                return JSONResponse({"detail": "missing_write_header"}, status_code=403)
            if not origin_allowed(
                request.headers.get("origin"), request.headers.get("host"), settings.public_url
            ):
                return JSONResponse({"detail": "foreign_origin"}, status_code=403)
        return await call_next(request)


def _mount_frontend(app: FastAPI, directory: Path | None) -> None:
    """Serve the built single-page app, when one is present.

    Absent, as in the dev stack where Vite serves the app and proxies the API, the application is
    the API alone.
    """
    if directory is None or not (directory / "index.html").is_file():
        logger.info("no built frontend at %s; serving the API only", directory)
        return
    root = directory.resolve()
    index = root / "index.html"

    @app.middleware("http")
    async def cache_assets(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/assets/") and response.status_code == 200:
            response.headers["Cache-Control"] = IMMUTABLE
        return response

    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        """Serve a file of the built app if there is one, and the app's shell otherwise.

        Client-side routes such as /bills are not files, so they get the shell, which reads the
        URL and renders the view. Registered last, so every API route matches first; a path under
        /api that matched nothing is a 404, not the shell, so a mistyped endpoint fails loudly.
        """
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = (root / path).resolve()
        # Confined to the build directory, so ../ cannot reach anything else on disk.
        if path and root in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
