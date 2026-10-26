"""Shared fixtures.

Every test runs against its own temporary data directory and SQLite file, so no test sees
another's rows and none touches a developer's real database. The API is driven the way the
interface drives it: setup and login through their endpoints, writes with the write header.
"""

import tempfile
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from helpers import PASSWORD, Agreement, ok

from house_cost.api.app import create_app
from house_cost.auth import WRITE_HEADER, WRITE_HEADER_VALUE
from house_cost.config import Settings
from house_cost.models import Base


@pytest.fixture
def data_dir() -> Iterator[Path]:
    """A throwaway data directory."""
    with tempfile.TemporaryDirectory() as directory:
        yield Path(directory)


#: The notification channels the tests' deployment offers.
MAIL_URL = "mailto://mail.test/?from=house-cost@house.test"
SIGNAL_URL = "signal://signal.test:8080/+351210000000"


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    """Settings pointed at the throwaway directory, serving no built frontend."""
    return Settings(
        data_dir=data_dir,
        static_dir=None,
        scheduler_enabled=False,
        notify_email_url=MAIL_URL,
        notify_signal_url=SIGNAL_URL,
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    """The application with its lifespan running and its schema created from the models.

    ``create_all`` rather than the migrations: test_migrations.py checks separately that the
    migrations produce exactly this schema.
    """
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        async with application.state.services.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield application


def _client(app: FastAPI, *, write_header: bool = True) -> httpx.AsyncClient:
    headers = {WRITE_HEADER: WRITE_HEADER_VALUE} if write_header else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://house-cost.test", headers=headers
    )


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """A browser talking to the application, sending the write header as the interface does."""
    async with _client(app) as client:
        yield client


@pytest.fixture
async def new_client(app: FastAPI) -> AsyncIterator[Callable[..., httpx.AsyncClient]]:
    """Open further browsers, each with its own cookies."""
    opened: list[httpx.AsyncClient] = []

    def open_one(*, write_header: bool = True) -> httpx.AsyncClient:
        client = _client(app, write_header=write_header)
        opened.append(client)
        return client

    yield open_one
    for client in opened:
        await client.aclose()


@pytest.fixture
async def admin(client: httpx.AsyncClient) -> dict:
    """Set the app up through its first-run endpoint; ``client`` is then logged in as the admin."""
    response = await client.post(
        "/api/setup",
        json={"household_name": "Lúcia", "name": "Lúcia", "login": "lucia", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def agreement(client: httpx.AsyncClient, admin: dict) -> Agreement:
    """The agreement of 5 Sep 2026: electricity and SMAS 50/50, road upkeep 40/60, other upkeep
    0/100, between Lúcia's household and the owners'."""
    owners = await ok(
        client.post("/api/households", json={"name": "Tiago + Marta", "position": 1}), 201
    )
    lucia = admin["household_id"]
    ids = {}
    for key, name, split in (
        ("electricity", "Electricity", (5000, 5000)),
        ("smas", "SMAS", (5000, 5000)),
        ("road", "Road upkeep", (4000, 6000)),
        ("upkeep", "Other upkeep and major works", (0, 10000)),
    ):
        category = await ok(client.post("/api/categories", json={"name": name}), 201)
        ids[key] = category["id"]
        await ok(
            client.post(
                "/api/rules",
                json={
                    "category_id": category["id"],
                    "effective_from": "2026-09-05",
                    "shares": [
                        {"household_id": lucia, "basis_points": split[0]},
                        {"household_id": owners["id"], "basis_points": split[1]},
                    ],
                },
            ),
            201,
        )
    return Agreement(lucia=lucia, owners=owners["id"], **ids)


@pytest.fixture
async def member(client: httpx.AsyncClient, agreement: Agreement, new_client) -> httpx.AsyncClient:
    """A browser logged in as Tiago, an ordinary member of the owners' household."""
    await ok(
        client.post(
            "/api/people",
            json={
                "name": "Tiago",
                "login": "tiago",
                "household_id": agreement.owners,
                "password": PASSWORD,
            },
        ),
        201,
    )
    browser = new_client()
    await ok(browser.post("/api/auth/login", json={"login": "tiago", "password": PASSWORD}))
    return browser
