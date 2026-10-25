"""Annual reconciliation: off by default, and when on, adjustments that settle the difference."""

import pytest
from helpers import Agreement, bill, ok


@pytest.fixture
async def enabled(client, agreement: Agreement) -> Agreement:
    await ok(client.put("/api/settings", json={"reconciliation_enabled": True}))
    return agreement


@pytest.fixture
async def year(client, enabled: Agreement) -> Agreement:
    """A year of electricity and road bills, split by the agreement's rules."""
    for payload in (
        bill("2026-10-01", enabled.owners, (enabled.electricity, 10001)),
        bill("2026-11-01", enabled.graca, (enabled.electricity, 20000), (enabled.road, 10000)),
        bill("2027-01-05", enabled.graca, (enabled.electricity, 5000)),
    ):
        await ok(client.post("/api/bills", json=payload), 201)
    return enabled


def _draft(agreement: Agreement, graca_bp: int = 6000) -> dict:
    """2026's electricity reconciled at 60/40, as a winter of the kiln might have it."""
    return {
        "period_start": "2026-01-01",
        "period_end": "2026-12-31",
        "note": "Kiln winter",
        "shares": [
            {
                "category_id": agreement.electricity,
                "household_id": agreement.graca,
                "basis_points": graca_bp,
            },
            {
                "category_id": agreement.electricity,
                "household_id": agreement.owners,
                "basis_points": 10000 - graca_bp,
            },
        ],
    }


async def test_absent_while_switched_off(client, agreement: Agreement) -> None:
    assert (await client.get("/api/reconciliations")).status_code == 404
    assert (await client.post("/api/reconciliations", json=_draft(agreement))).status_code == 404


async def test_a_draft_shows_the_adjustment_it_would_write(client, year: Agreement) -> None:
    draft = await ok(client.post("/api/reconciliations", json=_draft(year)), 201)

    assert draft["status"] == "draft"
    assert draft["bill_count"] == 2
    lines = {line["household_id"]: line for line in draft["lines"]}
    # 2026's electricity is 30 001 cents, charged 15 001 / 15 000; at 60/40 it is 18 001 / 12 000.
    assert lines[year.graca] == {
        "household_id": year.graca,
        "charged_cents": 15001,
        "reconciled_cents": 18001,
        "adjustment_cents": 3000,
    }
    assert lines[year.owners]["adjustment_cents"] == -3000
    # Nothing is written while it is a draft.
    balances = await ok(client.get("/api/balances"))
    assert {h["adjustment_cents"] for h in balances["households"]} == {0}


async def test_closing_writes_adjustments_that_balances_count(client, year: Agreement) -> None:
    draft = await ok(client.post("/api/reconciliations", json=_draft(year)), 201)
    before = {
        h["household_id"]: h["balance_cents"]
        for h in (await ok(client.get("/api/balances")))["households"]
    }

    closed = await ok(client.post(f"/api/reconciliations/{draft['id']}/close"))

    assert closed["status"] == "closed" and closed["closed_at"]
    after = {h["household_id"]: h for h in (await ok(client.get("/api/balances")))["households"]}
    assert after[year.graca]["adjustment_cents"] == 3000
    assert after[year.graca]["balance_cents"] == before[year.graca] - 3000
    assert after[year.owners]["balance_cents"] == before[year.owners] + 3000
    assert sum(h["balance_cents"] for h in after.values()) == 0


async def test_a_closed_period_locks_its_bills(client, year: Agreement) -> None:
    draft = await ok(client.post("/api/reconciliations", json=_draft(year)), 201)
    await ok(client.post(f"/api/reconciliations/{draft['id']}/close"))
    bills = (await ok(client.get("/api/bills")))["items"]
    in_period = next(b for b in bills if b["date"] == "2026-10-01")
    after_period = next(b for b in bills if b["date"] == "2027-01-05")

    assert in_period["locked"] is True and after_period["locked"] is False
    edits = [
        await client.put(
            f"/api/bills/{in_period['id']}",
            json=bill("2026-10-01", year.owners, (year.electricity, 1)),
        ),
        await client.delete(f"/api/bills/{in_period['id']}"),
        await client.post(
            "/api/bills", json=bill("2026-06-01", year.owners, (year.electricity, 1))
        ),
        await client.put(
            f"/api/bills/{after_period['id']}",
            json=bill("2026-12-01", year.graca, (year.electricity, 1)),
        ),
        await client.post(
            "/api/attachments",
            files={"file": ("x.pdf", b"%PDF-1.7", "application/pdf")},
            data={"bill_id": str(in_period["id"])},
        ),
    ]
    assert [(r.status_code, r.json()["detail"]) for r in edits] == [(409, "period_closed")] * 5


async def test_a_closed_reconciliation_is_final(client, year: Agreement) -> None:
    draft = await ok(client.post("/api/reconciliations", json=_draft(year)), 201)
    await ok(client.post(f"/api/reconciliations/{draft['id']}/close"))

    for response in (
        await client.put(f"/api/reconciliations/{draft['id']}", json=_draft(year, 5000)),
        await client.post(f"/api/reconciliations/{draft['id']}/close"),
        await client.delete(f"/api/reconciliations/{draft['id']}"),
    ):
        assert (response.status_code, response.json()["detail"]) == (409, "already_closed")
    overlapping = await client.post(
        "/api/reconciliations",
        json={**_draft(year), "period_start": "2026-12-01", "period_end": "2027-03-31"},
    )
    assert (overlapping.status_code, overlapping.json()["detail"]) == (
        409,
        "overlaps_closed_period",
    )


async def test_a_draft_can_be_changed_and_discarded(client, year: Agreement) -> None:
    draft = await ok(client.post("/api/reconciliations", json=_draft(year)), 201)
    changed = await ok(client.put(f"/api/reconciliations/{draft['id']}", json=_draft(year, 5000)))

    assert {line["adjustment_cents"] for line in changed["lines"]} == {0}
    assert [r["id"] for r in await ok(client.get("/api/reconciliations"))] == [draft["id"]]
    assert (await client.delete(f"/api/reconciliations/{draft['id']}")).status_code == 204
    assert (await client.get(f"/api/reconciliations/{draft['id']}")).status_code == 404


async def test_switching_it_off_sets_aside_the_adjustments_and_the_locks(
    client, year: Agreement
) -> None:
    draft = await ok(client.post("/api/reconciliations", json=_draft(year)), 201)
    await ok(client.post(f"/api/reconciliations/{draft['id']}/close"))
    await ok(client.put("/api/settings", json={"reconciliation_enabled": False}))

    balances = await ok(client.get("/api/balances"))
    assert {h["adjustment_cents"] for h in balances["households"]} == {0}
    assert sum(h["balance_cents"] for h in balances["households"]) == 0
    bills = (await ok(client.get("/api/bills")))["items"]
    assert {b["locked"] for b in bills} == {False}
    assert (await client.get(f"/api/reconciliations/{draft['id']}")).status_code == 404


async def test_the_shares_must_add_up_and_name_known_things(client, enabled: Agreement) -> None:
    uneven = _draft(enabled)
    uneven["shares"][0]["basis_points"] = 1
    unknown_category = _draft(enabled)
    for share in unknown_category["shares"]:
        share["category_id"] = 999
    unknown_household = _draft(enabled)
    unknown_household["shares"][1]["household_id"] = 999
    backwards = {**_draft(enabled), "period_start": "2027-01-01", "period_end": "2026-01-01"}

    assert (await client.post("/api/reconciliations", json=uneven)).status_code == 422
    assert (await client.post("/api/reconciliations", json=unknown_category)).json()[
        "detail"
    ] == "unknown_category"
    assert (await client.post("/api/reconciliations", json=unknown_household)).json()[
        "detail"
    ] == "unknown_household"
    assert (await client.post("/api/reconciliations", json=backwards)).status_code == 422


async def test_members_may_look_but_not_reconcile(client, member, year: Agreement) -> None:
    draft = await ok(client.post("/api/reconciliations", json=_draft(year)), 201)

    assert (await ok(member.get(f"/api/reconciliations/{draft['id']}")))["id"] == draft["id"]
    assert (await member.post(f"/api/reconciliations/{draft['id']}/close")).status_code == 403
