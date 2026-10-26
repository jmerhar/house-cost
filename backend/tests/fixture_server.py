"""Serve the real application over a throwaway database, for the Bruno collection.

    python -m tests.fixture_server PORT

Run from backend/ by bin/test-bruno.sh. The database is migrated exactly as the container's
entrypoint migrates it, then filled through the API itself with the agreement's example: two
households, the electricity and road rules, MEO Energia and its electricity service, and a bill
in each category. Log in as `lucia` with
the password in FIXTURE_PASSWORD.
"""

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx
import uvicorn

from house_cost.api.app import create_app
from house_cost.auth import WRITE_HEADER, WRITE_HEADER_VALUE
from house_cost.config import Settings

BACKEND = Path(__file__).resolve().parents[1]
FIXTURE_PASSWORD = "correct horse battery"


async def seed(settings: Settings) -> None:
    """Set the app up and enter the example through its own API."""
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://fixture",
            headers={WRITE_HEADER: WRITE_HEADER_VALUE},
        ) as api:

            async def post(path: str, body: dict) -> dict:
                response = await api.post(path, json=body)
                response.raise_for_status()
                return response.json()

            me = await post(
                "/api/setup",
                {
                    "household_name": "Lúcia",
                    "name": "Lúcia",
                    "login": "lucia",
                    "password": FIXTURE_PASSWORD,
                },
            )
            lucia = me["household_id"]
            owners = await post("/api/households", {"name": "Tiago + Marta", "position": 1})
            owners = owners["id"]
            for name, split in (("Electricity", (5000, 5000)), ("Road upkeep", (4000, 6000))):
                category = await post("/api/categories", {"name": name})
                await post(
                    "/api/rules",
                    {
                        "category_id": category["id"],
                        "effective_from": "2026-09-05",
                        "note": "Agreement of 5 Sep 2026",
                        "shares": [
                            {"household_id": lucia, "basis_points": split[0]},
                            {"household_id": owners, "basis_points": split[1]},
                        ],
                    },
                )
                if name == "Electricity":
                    supplier = await post(
                        "/api/suppliers",
                        {
                            "name": "MEO Energia",
                            "nif": "506743357",
                            "default_category_id": category["id"],
                        },
                    )
                    service = await post(
                        "/api/services",
                        {
                            "supplier_id": supplier["id"],
                            "name": "Electricity at the Quinta",
                            "ends_on": "2026-12-11",
                            "notice_days": 30,
                        },
                    )
                    await post(
                        "/api/bills",
                        {
                            "date": "2026-10-18",
                            "supplier": "MEO Energia",
                            "service_id": service["id"],
                            "paid_by_id": owners,
                            "lines": [{"category_id": category["id"], "amount_cents": 28759}],
                        },
                    )
                else:
                    await post(
                        "/api/bills",
                        {
                            "date": "2026-10-05",
                            "description": "Gravel",
                            "paid_by_id": lucia,
                            "lines": [{"category_id": category["id"], "amount_cents": 10000}],
                        },
                    )


def main(port: int) -> None:
    """Migrate and fill a fresh database, then serve the API on loopback until interrupted."""
    with tempfile.TemporaryDirectory() as scratch:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env={"DATA_DIR": scratch, "PATH": ""},
            check=True,
        )
        settings = Settings(data_dir=Path(scratch), static_dir=None)
        asyncio.run(seed(settings))
        uvicorn.run(create_app(settings), host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main(int(sys.argv[1]))
