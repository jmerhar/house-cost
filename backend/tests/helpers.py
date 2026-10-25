"""Helpers the API tests share: the test password, response checks and request builders."""

from collections.abc import Awaitable
from dataclasses import dataclass

import httpx

PASSWORD = "correct horse battery"


@dataclass
class Agreement:
    """The cost-sharing agreement, as fixtures set it up: two households and their rules."""

    lucia: int
    owners: int
    electricity: int
    smas: int
    road: int
    upkeep: int


async def ok(response: Awaitable[httpx.Response] | httpx.Response, status: int = 200) -> dict:
    """The JSON of a response that must have ``status``."""
    if not isinstance(response, httpx.Response):
        response = await response
    assert response.status_code == status, response.text
    return response.json() if response.content else {}


def bill(on: str, paid_by: int, *lines: tuple[int, int], **fields) -> dict:
    """A bill's JSON: its date, payer and (category, cents) lines."""
    return {
        "date": on,
        "paid_by_id": paid_by,
        "lines": [{"category_id": category, "amount_cents": cents} for category, cents in lines],
        **fields,
    }


def shares_of(line: dict) -> dict[int, int]:
    """A line's shares as {household id: cents}."""
    return {share["household_id"]: share["amount_cents"] for share in line["shares"]}
