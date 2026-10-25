"""Shared fixtures.

Every test runs against its own temporary data directory and SQLite file, so no test sees
another's rows and none touches a developer's real database.
"""

import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from house_cost.api.app import create_app
from house_cost.config import Settings


@pytest.fixture
def data_dir() -> Iterator[Path]:
    """A throwaway data directory."""
    with tempfile.TemporaryDirectory() as directory:
        yield Path(directory)


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    """Settings pointed at the throwaway directory, serving no built frontend."""
    return Settings(data_dir=data_dir, static_dir=None)


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    """The application with its lifespan running, as uvicorn would run it."""
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """A client talking to the application in-process."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://house-cost.test") as client:
        yield client
