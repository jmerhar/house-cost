"""Reading a bill's file into a proposal, and the readings bills record."""

import asyncio

import httpx
import pytest
from helpers import Agreement, bill, ok
from synthetic import meo_bill, meo_energia_bill, pdf


@pytest.fixture
async def meo_energia(client, agreement: Agreement) -> dict:
    """MEO Energia and the electricity service the house has with it."""
    supplier = await ok(
        client.post(
            "/api/suppliers",
            json={
                "name": "MEO Energia",
                "nif": "506743357",
                "default_category_id": agreement.electricity,
            },
        ),
        201,
    )
    service = await ok(
        client.post(
            "/api/services",
            json={
                "supplier_id": supplier["id"],
                "name": "Electricity",
                "identifiers": {"CPE": "PT0002 0000 9999 9999 ZZ"},
                "ends_on": "2026-11-30",
            },
        ),
        201,
    )
    return {"supplier": supplier, "service": service}


async def read(client: httpx.AsyncClient, data: bytes, name: str = "bill.pdf") -> httpx.Response:
    return await client.post(
        "/api/bills/read", files={"file": (name, data, "application/octet-stream")}
    )


class TestReading:
    async def test_proposes_a_bill_from_the_qr_code_and_the_page(
        self, client, meo_energia, agreement
    ) -> None:
        proposal = await ok(read(client, meo_energia_bill()))

        assert proposal["supplier_id"] == meo_energia["supplier"]["id"]
        assert proposal["service_id"] == meo_energia["service"]["id"]
        assert (proposal["date"], proposal["invoice_number"], proposal["total_cents"]) == (
            "2026-10-18",
            "FT FA.MEA26/100001",
            28759,
        )
        assert (proposal["period_start"], proposal["period_end"], proposal["due_date"]) == (
            "2026-09-13",
            "2026-10-16",
            "2026-11-03",
        )
        assert proposal["lines"] == [
            {"description": "", "amount_cents": 28759, "category_id": agreement.electricity}
        ]
        assert proposal["readings"] == [
            {"quantity": "electricity_kwh", "value": 1284.0, "unit_price": 0.1525}
        ]
        assert proposal["service_changes"] == {
            "ends_on": "2026-12-11",
            "renews_automatically": None,
            "lock_in_until": None,
        }
        assert proposal["sources"]["total_cents"] == "qr"
        assert (proposal["text_source"], proposal["warnings"], proposal["duplicate_bill_id"]) == (
            "text",
            [],
            None,
        )

    async def test_a_bill_already_entered_is_pointed_out(
        self, client, meo_energia, agreement
    ) -> None:
        created = await ok(
            client.post(
                "/api/bills",
                json=bill(
                    "2026-10-18",
                    agreement.owners,
                    (agreement.electricity, 28759),
                    invoice_number="FA MEA26/100 001",
                    supplier="MEO Energia",
                ),
            ),
            201,
        )
        assert (await ok(read(client, meo_energia_bill())))["duplicate_bill_id"] == created["id"]

    async def test_the_same_file_attached_to_a_bill_is_pointed_out(
        self, client, meo_energia, agreement
    ) -> None:
        data = meo_energia_bill(qr=None)
        created = await ok(
            client.post(
                "/api/bills", json=bill("2026-10-18", agreement.owners, (agreement.electricity, 1))
            ),
            201,
        )
        await ok(
            client.post(
                "/api/attachments",
                files={"file": ("bill.pdf", data, "application/pdf")},
                data={"bill_id": str(created["id"])},
            ),
            201,
        )
        assert (await ok(read(client, data)))["duplicate_bill_id"] == created["id"]

    async def test_an_itemised_bill_proposes_its_lines(self, client, agreement) -> None:
        await ok(client.post("/api/suppliers", json={"name": "MEO", "nif": "504615947"}), 201)
        proposal = await ok(read(client, meo_bill()))

        assert [(line["description"], line["amount_cents"]) for line in proposal["lines"]] == [
            ("Package", 1838),
            ("Mobile", 61),
            ("Activation", 99),
        ]
        assert proposal["service_id"] is None
        assert proposal["service_changes"]["lock_in_until"] is None

    async def test_a_suppliers_only_service_is_assumed(self, client, agreement) -> None:
        supplier = await ok(
            client.post("/api/suppliers", json={"name": "MEO", "nif": "504615947"}), 201
        )
        service = await ok(
            client.post(
                "/api/services",
                json={
                    "supplier_id": supplier["id"],
                    "name": "M4",
                    "lock_in_until": "2027-01-01",
                    "renews_automatically": False,
                },
            ),
            201,
        )
        proposal = await ok(read(client, meo_bill()))

        assert proposal["service_id"] == service["id"]
        assert proposal["service_changes"] == {
            "ends_on": None,
            "renews_automatically": None,
            "lock_in_until": "2027-07-28",
        }

    async def test_what_the_service_already_says_is_not_proposed_again(
        self, client, meo_energia
    ) -> None:
        service = meo_energia["service"]
        await ok(
            client.put(f"/api/services/{service['id']}", json={**service, "ends_on": "2026-12-11"})
        )

        changes = (await ok(read(client, meo_energia_bill())))["service_changes"]
        assert changes == {"ends_on": None, "renews_automatically": None, "lock_in_until": None}

    async def test_a_bill_from_nobody_on_file(self, client, admin) -> None:
        proposal = await ok(
            read(client, pdf(["Fatura N.o: FT 9/9 de 01/02/2027", "Total a pagar: 12,00"]))
        )

        assert (proposal["supplier_id"], proposal["service_id"], proposal["total_cents"]) == (
            None,
            None,
            1200,
        )
        assert proposal["lines"] == [{"description": "", "amount_cents": 1200, "category_id": None}]

    async def test_a_file_with_nothing_readable_proposes_nothing(self, client, admin) -> None:
        proposal = await ok(read(client, pdf(["hello there, nothing to see"])))
        assert (proposal["total_cents"], proposal["lines"]) == (None, [])

    async def test_refusals(self, client, admin, app) -> None:
        text = await read(client, b"<html>", "page.pdf")
        broken = await read(client, b"%PDF-1.7 broken")
        app.state.services.settings.max_upload_bytes = 10
        large = await read(client, meo_energia_bill())

        assert (text.status_code, text.json()["detail"]) == (415, "unsupported_file")
        assert (broken.status_code, broken.json()["detail"]) == (422, "unreadable")
        assert (large.status_code, large.json()["detail"]) == (413, "too_large")

    async def test_reading_that_takes_too_long_gives_up(self, client, admin, monkeypatch) -> None:
        monkeypatch.setattr("house_cost.api.routers.reading.READ_SECONDS", 0.01)

        def slow(*args):
            import time

            time.sleep(0.2)

        monkeypatch.setattr("house_cost.api.routers.reading.extract", slow)
        response = await read(client, meo_energia_bill())

        assert (response.status_code, response.json()["detail"]) == (504, "read_timeout")
        await asyncio.sleep(0.3)  # let the abandoned thread finish before the test's loop closes


class TestReadings:
    async def test_bills_keep_their_readings_and_list_them(
        self, client, meo_energia, agreement
    ) -> None:
        service_id = meo_energia["service"]["id"]
        created = await ok(
            client.post(
                "/api/bills",
                json=bill(
                    "2026-10-18",
                    agreement.owners,
                    (agreement.electricity, 28759),
                    service_id=service_id,
                    period_end="2026-10-16",
                    readings=[{"quantity": "electricity_kwh", "value": 1284, "unit_price": 0.1525}],
                ),
            ),
            201,
        )
        await ok(
            client.post(
                "/api/bills", json=bill("2026-11-01", agreement.lucia, (agreement.road, 100))
            ),
            201,
        )

        assert created["readings"] == [
            {"quantity": "electricity_kwh", "value": 1284.0, "unit_price": 0.1525}
        ]
        points = await ok(client.get("/api/readings"))
        assert [(p["bill_id"], p["value"], p["period_end"]) for p in points] == [
            (created["id"], 1284.0, "2026-10-16")
        ]
        assert await ok(client.get("/api/readings", params={"service_id": 999})) == []
        assert len(await ok(client.get("/api/readings", params={"service_id": service_id}))) == 1

        corrected = await ok(
            client.put(
                f"/api/bills/{created['id']}",
                json=bill("2026-10-18", agreement.owners, (agreement.electricity, 28759)),
            )
        )
        assert corrected["readings"] == []

    async def test_a_reading_must_be_a_known_quantity(self, client, agreement) -> None:
        response = await client.post(
            "/api/bills",
            json=bill(
                "2026-10-18",
                agreement.owners,
                (agreement.electricity, 1),
                readings=[{"quantity": "gas", "value": 1}],
            ),
        )
        assert response.status_code == 422


def test_invoice_numbers_are_compared_by_their_tails() -> None:
    from house_cost.api.routers.reading import _same_number

    assert _same_number("FA MEA26/100 001", "FT FA.MEA26/100001")
    assert not _same_number("FT A/1", "FT A/2")
    assert not _same_number(None, "FT A/1")
    assert not _same_number("FT A/", "FT B/")
