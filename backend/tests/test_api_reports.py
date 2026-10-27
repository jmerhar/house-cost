"""The yearly summary, the CSV export, and the audit log."""

import csv
import io

import pytest
from helpers import Agreement, bill, ok


@pytest.fixture
async def year_of_bills(client, agreement: Agreement) -> None:
    for payload in (
        bill(
            "2026-10-01",
            agreement.owners,
            (agreement.electricity, 15054),
            supplier="EDP",
            description="Sep–Oct",
        ),
        bill("2026-10-05", agreement.lucia, (agreement.road, 10000)),
        bill("2026-11-23", agreement.owners, (agreement.electricity, 28759), (agreement.smas, 101)),
        bill("2027-01-10", agreement.lucia, (agreement.smas, 4868)),
    ):
        await ok(client.post("/api/bills", json=payload), 201)


class TestSummary:
    async def test_a_years_costs_by_category_and_month(
        self, client, agreement: Agreement, year_of_bills
    ) -> None:
        summary = await ok(client.get("/api/reports/summary", params={"year": 2026}))

        assert summary["year"] == 2026
        assert summary["years"] == [2027, 2026]
        assert summary["total_cents"] == 15054 + 10000 + 28759 + 101
        assert [(c["name"], c["total_cents"]) for c in summary["categories"]] == [
            ("Electricity", 43813),
            ("Road upkeep", 10000),
            ("SMAS", 101),
        ]
        road = summary["categories"][1]
        assert road["shares"] == [
            {"household_id": agreement.lucia, "amount_cents": 4000},
            {"household_id": agreement.owners, "amount_cents": 6000},
        ]
        assert [(m["month"], m["total_cents"]) for m in summary["months"]] == [
            (10, 25054),
            (11, 28860),
        ]
        assert sum(s["amount_cents"] for s in summary["shares"]) == summary["total_cents"]

    async def test_without_a_year_the_latest_with_bills(self, client, year_of_bills) -> None:
        assert (await ok(client.get("/api/reports/summary")))["year"] == 2027

    async def test_with_no_bills_this_year_and_nothing_in_it(self, client, agreement) -> None:
        summary = await ok(client.get("/api/reports/summary"))
        assert (summary["years"], summary["total_cents"], summary["categories"]) == ([], 0, [])


class TestCsv:
    async def test_one_row_per_line_with_each_households_share(self, client, year_of_bills) -> None:
        response = await client.get("/api/reports/bills.csv", params={"year": 2026})

        assert response.headers["content-type"].startswith("text/csv")
        assert 'filename="bills-2026.csv"' in response.headers["content-disposition"]
        rows = list(csv.reader(io.StringIO(response.text)))
        assert rows[0] == [
            "date",
            "supplier",
            "description",
            "invoice",
            "category",
            "line",
            "amount",
            "paid by",
            "Lúcia",
            "Tiago + Marta",
        ]
        assert rows[1] == [
            "2026-10-01",
            "EDP",
            "Sep–Oct",
            "",
            "Electricity",
            "",
            "150.54",
            "Tiago + Marta",
            "75.27",
            "75.27",
        ]
        assert len(rows) == 1 + 4

    async def test_every_year_and_negative_amounts(
        self, client, agreement: Agreement, year_of_bills
    ) -> None:
        await ok(
            client.post(
                "/api/bills", json=bill("2027-02-01", agreement.lucia, (agreement.smas, -5))
            ),
            201,
        )
        response = await client.get("/api/reports/bills.csv")

        assert 'filename="bills.csv"' in response.headers["content-disposition"]
        last = list(csv.reader(io.StringIO(response.text)))[-1]
        assert last[6:] == ["-0.05", "Lúcia", "-0.03", "-0.02"]


class TestAudit:
    async def test_every_change_is_recorded_with_who_made_it(
        self, client, member, agreement: Agreement
    ) -> None:
        created = await ok(
            member.post(
                "/api/bills", json=bill("2026-10-01", agreement.owners, (agreement.road, 100))
            ),
            201,
        )
        await ok(
            member.put(
                f"/api/bills/{created['id']}",
                json=bill("2026-10-01", agreement.owners, (agreement.road, 200)),
            )
        )
        await member.delete(f"/api/bills/{created['id']}")

        page = await ok(
            client.get("/api/audit", params={"entity": "bill", "entity_id": created["id"]})
        )

        assert [(e["action"], e["person_name"]) for e in page["items"]] == [
            ("delete", "Tiago"),
            ("update", "Tiago"),
            ("create", "Tiago"),
        ]
        update = page["items"][1]
        assert (update["before"]["total_cents"], update["after"]["total_cents"]) == (100, 200)
        assert page["total"] == 3
        assert {entry["exists"] for entry in page["items"]} == {False}

    async def test_entries_say_whether_their_bill_is_still_there(
        self, client, agreement: Agreement
    ) -> None:
        kept = await ok(
            client.post(
                "/api/bills", json=bill("2026-10-01", agreement.owners, (agreement.road, 1))
            ),
            201,
        )
        gone = await ok(
            client.post(
                "/api/bills", json=bill("2026-10-02", agreement.owners, (agreement.road, 2))
            ),
            201,
        )
        await client.delete(f"/api/bills/{gone['id']}")
        page = await ok(client.get("/api/audit", params={"limit": 500}))
        exists = {(e["entity"], e["entity_id"], e["action"]): e["exists"] for e in page["items"]}

        assert exists[("bill", kept["id"], "create")] is True
        assert exists[("bill", gone["id"], "create")] is False
        assert all(e["exists"] for e in page["items"] if e["entity"] != "bill")

    async def test_the_setup_and_the_agreement_are_in_it(
        self, client, agreement: Agreement
    ) -> None:
        page = await ok(client.get("/api/audit", params={"limit": 500}))
        kinds = {(e["action"], e["entity"]) for e in page["items"]}

        assert {
            ("create", "household"),
            ("create", "person"),
            ("create", "category"),
            ("create", "rule"),
        } <= kinds
        assert (await ok(client.get("/api/audit", params={"limit": 2, "offset": 1})))["items"][0][
            "id"
        ] == page["items"][1]["id"]
