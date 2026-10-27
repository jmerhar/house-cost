"""Suppliers, services, and the document library with its search."""

import httpx
import pytest
from helpers import Agreement, bill, ok
from synthetic import image_only_pdf, pdf

from house_cost.config import Settings

CONTRACT = pdf(
    ["CONDICOES GERAIS CONTRATO FORNECIMENTO DE ENERGIA ELETRICA", "MEO Energia"],
    [
        "4. Duracao, renovacao e cessacao do contrato",
        "pre-aviso maximo de 1 (um) mes",
        "Sem fidelizacao",
    ],
)


@pytest.fixture
async def meo(client, agreement: Agreement) -> dict:
    return await ok(
        client.post(
            "/api/suppliers",
            json={
                "name": "MEO Energia",
                "nif": "506 743 357",
                "default_category_id": agreement.electricity,
            },
        ),
        201,
    )


@pytest.fixture
async def electricity(client, meo: dict, agreement: Agreement) -> dict:
    return await ok(
        client.post(
            "/api/services",
            json={
                "supplier_id": meo["id"],
                "name": "Electricity at the Quinta",
                "identifiers": {"CPE": "PT0002000000000000XX", "Cliente": "123"},
                "default_category_id": agreement.electricity,
                "starts_on": "2026-09-13",
                "ends_on": "2026-12-11",
                "renews_automatically": True,
                "notice_days": 30,
                "billed_every_days": 30,
            },
        ),
        201,
    )


async def _upload(
    client: httpx.AsyncClient, data: bytes, name: str = "contract.pdf", **fields
) -> httpx.Response:
    form = {
        "title": "MEO Energia contract",
        "kind": "contract",
        **{k: str(v) for k, v in fields.items()},
    }
    return await client.post(
        "/api/documents", files={"file": (name, data, "application/pdf")}, data=form
    )


class TestSuppliers:
    async def test_a_supplier_keeps_its_nif_without_spaces(
        self, client, meo: dict, agreement
    ) -> None:
        assert (meo["nif"], meo["default_category_id"]) == ("506743357", agreement.electricity)
        assert [s["name"] for s in await ok(client.get("/api/suppliers"))] == ["MEO Energia"]

    async def test_names_and_nifs_are_unique(self, client, meo: dict) -> None:
        by_name = await client.post("/api/suppliers", json={"name": "MEO Energia"})
        by_nif = await client.post("/api/suppliers", json={"name": "Other", "nif": "506743357"})

        assert (by_name.status_code, by_name.json()["detail"]) == (409, "supplier_exists")
        assert by_nif.status_code == 409

    @pytest.mark.parametrize("nif", ["12345", "50674335X", "5067433571"])
    async def test_a_nif_is_nine_digits(self, client, admin, nif: str) -> None:
        assert (
            await client.post("/api/suppliers", json={"name": "X", "nif": nif})
        ).status_code == 422

    async def test_anyone_may_correct_a_supplier(self, member, meo: dict) -> None:
        corrected = await ok(
            member.put(f"/api/suppliers/{meo['id']}", json={"name": "MEO Energia, S.A.", "nif": ""})
        )
        assert (corrected["name"], corrected["nif"]) == ("MEO Energia, S.A.", None)

    async def test_an_unknown_category_or_supplier_is_refused(self, client, meo: dict) -> None:
        bad_category = await client.post(
            "/api/suppliers", json={"name": "Y", "default_category_id": 999}
        )
        missing = await client.put("/api/suppliers/999", json={"name": "Z"})
        clash = await client.post("/api/suppliers", json={"name": "SMAS"})
        renamed = await client.put(
            f"/api/suppliers/{clash.json()['id']}", json={"name": "MEO Energia"}
        )

        assert (bad_category.status_code, bad_category.json()["detail"]) == (
            422,
            "unknown_category",
        )
        assert missing.status_code == 404
        assert (renamed.status_code, renamed.json()["detail"]) == (409, "supplier_exists")


class TestDeleting:
    async def test_an_unused_supplier_and_service_can_be_deleted(
        self, client, member, meo: dict, electricity: dict
    ) -> None:
        busy = await member.delete(f"/api/suppliers/{meo['id']}")
        assert (busy.status_code, busy.json()["detail"]) == (409, "supplier_in_use")
        assert [s["in_use"] for s in await ok(client.get("/api/suppliers"))] == [True]
        assert [s["in_use"] for s in await ok(client.get("/api/services"))] == [False]

        await ok(member.delete(f"/api/services/{electricity['id']}"), 204)
        assert [s["in_use"] for s in await ok(client.get("/api/suppliers"))] == [False]
        await ok(member.delete(f"/api/suppliers/{meo['id']}"), 204)

        assert await ok(client.get("/api/services")) == []
        assert await ok(client.get("/api/suppliers")) == []
        log = await ok(client.get("/api/audit", params={"limit": 2}))
        assert [(e["action"], e["entity"], e["before"]["name"]) for e in log["items"]] == [
            ("delete", "supplier", "MEO Energia"),
            ("delete", "service", "Electricity at the Quinta"),
        ]
        gone = await member.delete(f"/api/suppliers/{meo['id']}")
        assert gone.status_code == 404

    async def test_a_service_with_a_bill_is_kept_until_the_bill_is_deleted(
        self, client, electricity: dict, agreement: Agreement
    ) -> None:
        created = await ok(
            client.post(
                "/api/bills",
                json=bill(
                    "2026-10-18",
                    agreement.owners,
                    (agreement.electricity, 100),
                    service_id=electricity["id"],
                ),
            ),
            201,
        )
        assert [s["in_use"] for s in await ok(client.get("/api/services"))] == [True]
        busy = await client.delete(f"/api/services/{electricity['id']}")
        assert (busy.status_code, busy.json()["detail"]) == (409, "service_in_use")

        await ok(client.delete(f"/api/bills/{created['id']}"), 204)

        assert [s["in_use"] for s in await ok(client.get("/api/services"))] == [False]
        await ok(client.delete(f"/api/services/{electricity['id']}"), 204)

    async def test_a_document_keeps_its_service(self, client, electricity: dict) -> None:
        await ok(_upload(client, CONTRACT, service_id=electricity["id"]), 201)
        refused = await client.delete(f"/api/services/{electricity['id']}")

        assert (refused.status_code, refused.json()["detail"]) == (409, "service_in_use")

    async def test_a_document_keeps_its_supplier(self, client, meo: dict) -> None:
        await ok(_upload(client, CONTRACT, supplier_id=meo["id"]), 201)
        refused = await client.delete(f"/api/suppliers/{meo['id']}")

        assert (refused.status_code, refused.json()["detail"]) == (409, "supplier_in_use")
        assert [s["in_use"] for s in await ok(client.get("/api/suppliers"))] == [True]


class TestServices:
    async def test_a_service_keeps_what_its_contract_says(self, client, electricity: dict) -> None:
        assert electricity["identifiers"] == {"CPE": "PT0002000000000000XX", "Cliente": "123"}
        assert (
            electricity["ends_on"],
            electricity["notice_days"],
            electricity["lock_in_until"],
        ) == (
            "2026-12-11",
            30,
            None,
        )
        assert [s["name"] for s in await ok(client.get("/api/services"))] == [
            "Electricity at the Quinta"
        ]

    async def test_corrected_and_ended(self, member, electricity: dict) -> None:
        changed = await ok(
            member.put(
                f"/api/services/{electricity['id']}",
                json={**electricity, "lock_in_until": "2027-07-28", "active": False},
            )
        )
        assert (changed["lock_in_until"], changed["active"]) == ("2027-07-28", False)

    async def test_needs_a_known_supplier_and_category(self, client, meo: dict) -> None:
        no_supplier = await client.post("/api/services", json={"supplier_id": 999, "name": "X"})
        no_category = await client.post(
            "/api/services",
            json={"supplier_id": meo["id"], "name": "X", "default_category_id": 999},
        )
        missing = await client.put(
            "/api/services/999", json={"supplier_id": meo["id"], "name": "X"}
        )

        assert (no_supplier.status_code, no_supplier.json()["detail"]) == (422, "unknown_supplier")
        assert no_category.json()["detail"] == "unknown_category"
        assert missing.status_code == 404

    async def test_a_bill_names_the_service_it_is_for(
        self, client, electricity: dict, agreement: Agreement
    ) -> None:
        created = await ok(
            client.post(
                "/api/bills",
                json=bill(
                    "2026-10-18",
                    agreement.owners,
                    (agreement.electricity, 100),
                    service_id=electricity["id"],
                ),
            ),
            201,
        )
        unknown = await client.post(
            "/api/bills",
            json=bill("2026-10-18", agreement.owners, (agreement.electricity, 100), service_id=999),
        )

        assert created["service_id"] == electricity["id"]
        assert (unknown.status_code, unknown.json()["detail"]) == (422, "unknown_service")


class TestDocuments:
    async def test_a_pdfs_text_is_read_and_searched(
        self, client, meo: dict, electricity: dict
    ) -> None:
        kept = await ok(
            _upload(
                client,
                CONTRACT,
                dated="2026-09-05",
                supplier_id=meo["id"],
                service_id=electricity["id"],
            ),
            201,
        )

        assert (kept["pages"], kept["has_text"], kept["kind"], kept["dated"]) == (
            2,
            True,
            "contract",
            "2026-09-05",
        )
        found = await ok(client.get("/api/documents", params={"q": "PRE-AVISO"}))
        assert [d["id"] for d in found] == [kept["id"]]
        assert "pre-aviso maximo de 1 (um) mes" in found[0]["excerpt"]
        assert found[0]["excerpt"].startswith("…")
        assert await ok(client.get("/api/documents", params={"q": "nowhere"})) == []

    async def test_listed_newest_first_and_narrowed(
        self, client, meo: dict, electricity: dict
    ) -> None:
        older = await ok(_upload(client, CONTRACT, dated="2026-01-01"), 201)
        newer = await ok(
            _upload(
                client,
                pdf(["Tarifa Social"]),
                title="Tarifa social",
                kind="info",
                supplier_id=meo["id"],
            ),
            201,
        )

        assert [d["id"] for d in await ok(client.get("/api/documents"))] == [
            newer["id"],
            older["id"],
        ]
        assert [
            d["id"] for d in await ok(client.get("/api/documents", params={"kind": "info"}))
        ] == [newer["id"]]
        by_supplier = await ok(client.get("/api/documents", params={"supplier_id": meo["id"]}))
        assert [d["id"] for d in by_supplier] == [newer["id"]]
        assert (
            await ok(client.get("/api/documents", params={"service_id": electricity["id"]})) == []
        )
        assert (await ok(client.get("/api/documents", params={"q": "social"})))[0][
            "excerpt"
        ] == "Tarifa Social"

    async def test_a_scan_is_kept_without_text(self, client, admin) -> None:
        kept = await ok(_upload(client, image_only_pdf(), "scan.pdf"), 201)
        assert (kept["has_text"], kept["pages"]) == (False, 1)

    async def test_a_photo_is_kept_and_a_pdf_pdfium_cannot_read_still_is(
        self, client, admin
    ) -> None:
        photo = await ok(
            _upload(client, b"\x89PNG\r\n\x1a\n" + bytes(32), "leaflet.png", title="Leaflet"), 201
        )
        broken = await ok(_upload(client, b"%PDF-1.7 truncated", "broken.pdf", title="Broken"), 201)

        assert (photo["content_type"], photo["pages"]) == ("image/png", None)
        assert (broken["has_text"], broken["pages"]) == (False, None)

    async def test_the_file_is_served_in_the_sandbox(self, client, admin) -> None:
        kept = await ok(_upload(client, CONTRACT), 201)
        response = await client.get(f"/api/documents/{kept['id']}/file")

        assert response.content == CONTRACT
        assert response.headers["content-security-policy"].startswith("sandbox")
        assert (await ok(client.get(f"/api/documents/{kept['id']}")))["filename"] == "contract.pdf"

    async def test_details_are_corrected_and_the_document_removed(
        self, client, member, meo: dict, settings: Settings
    ) -> None:
        kept = await ok(_upload(client, CONTRACT), 201)
        changed = await ok(
            member.put(
                f"/api/documents/{kept['id']}",
                json={
                    "title": "Conditions",
                    "kind": "terms",
                    "supplier_id": meo["id"],
                    "notes": "Signed copy",
                },
            )
        )
        assert (changed["title"], changed["kind"], changed["supplier_id"]) == (
            "Conditions",
            "terms",
            meo["id"],
        )

        assert (await member.delete(f"/api/documents/{kept['id']}")).status_code == 204
        assert (await client.get(f"/api/documents/{kept['id']}")).status_code == 404
        assert any(p.is_file() for p in settings.files_dir.rglob("*"))

    async def test_refusals(self, client, admin, settings: Settings, app) -> None:
        text = await _upload(client, b"<html>", "page.pdf")
        bad_date = await _upload(client, CONTRACT, dated="yesterday")
        bad_supplier = await _upload(client, CONTRACT, supplier_id=999)
        bad_service = await client.put("/api/documents/1", json={"title": "x"})
        app.state.services.settings.max_upload_bytes = 10
        too_large = await _upload(client, CONTRACT)

        assert (text.status_code, text.json()["detail"]) == (415, "unsupported_file")
        assert (bad_date.status_code, bad_date.json()["detail"]) == (422, "invalid")
        assert (bad_supplier.status_code, bad_supplier.json()["detail"]) == (
            422,
            "unknown_supplier",
        )
        assert bad_service.status_code == 404
        assert (too_large.status_code, too_large.json()["detail"]) == (413, "too_large")
        assert [p for p in settings.files_dir.rglob("*") if p.is_file()] == []

    async def test_refusing_bytes_a_document_holds_keeps_them(
        self, client, admin, settings: Settings, monkeypatch
    ) -> None:
        await ok(_upload(client, CONTRACT), 201)
        monkeypatch.setattr("house_cost.api.routers.documents.sniff", lambda _head: None)

        assert (await _upload(client, CONTRACT)).status_code == 415
        assert len([p for p in settings.files_dir.rglob("*") if p.is_file()]) == 1

    async def test_an_unknown_service_is_refused_and_a_missing_file_is_a_404(
        self, client, admin, settings: Settings
    ) -> None:
        kept = await ok(_upload(client, CONTRACT), 201)
        bad = await client.put(
            f"/api/documents/{kept['id']}", json={"title": "x", "service_id": 999}
        )
        for path in settings.files_dir.rglob("*"):
            if path.is_file():
                path.unlink()

        assert (bad.status_code, bad.json()["detail"]) == (422, "unknown_service")
        missing = await client.get(f"/api/documents/{kept['id']}/file")
        assert (missing.status_code, missing.json()["detail"]) == (404, "file_missing")


async def test_a_title_match_has_no_excerpt(client, admin) -> None:
    await ok(_upload(client, CONTRACT, title="Electricity agreement"), 201)
    found = await ok(client.get("/api/documents", params={"q": "agreement"}))

    assert [d["title"] for d in found] == ["Electricity agreement"]
    assert found[0]["excerpt"] == ""
