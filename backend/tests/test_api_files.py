"""Attaching files to bills and settlements."""

import hashlib

import httpx
import pytest
from helpers import Agreement, bill, ok

from house_cost.config import Settings
from house_cost.storage import path_for, sniff

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@pytest.fixture
async def a_bill(client, agreement: Agreement) -> dict:
    return await ok(
        client.post(
            "/api/bills", json=bill("2026-10-18", agreement.owners, (agreement.electricity, 28759))
        ),
        201,
    )


async def _upload(
    client: httpx.AsyncClient, data: bytes, name: str = "bill.pdf", **owner
) -> httpx.Response:
    return await client.post(
        "/api/attachments",
        files={"file": (name, data, "application/octet-stream")},
        data={key: str(value) for key, value in owner.items()},
    )


class TestSniff:
    @pytest.mark.parametrize(
        ("head", "kind"),
        [
            (PDF, "application/pdf"),
            (b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg"),
            (PNG, "image/png"),
            (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
            (b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00", "image/heic"),
            (b"XXXX\x00\x00\x00\x00WEBPVP8 ", None),
            (b"<html><script>", None),
            (b"\x00\x00\x00\x18ftypisom", None),
        ],
    )
    def test_recognises_what_it_accepts_by_content(self, head: bytes, kind: str | None) -> None:
        assert sniff(head) == kind


class TestAttachments:
    async def test_a_pdf_is_attached_stored_once_and_served_safely(
        self, client, a_bill: dict, settings: Settings
    ) -> None:
        first = await ok(
            _upload(client, PDF, "../../FT A 100000001.pdf", bill_id=a_bill["id"]), 201
        )
        second = await ok(_upload(client, PDF, "copy.pdf", bill_id=a_bill["id"]), 201)

        assert (first["filename"], first["content_type"], first["size"]) == (
            "FT A 100000001.pdf",
            "application/pdf",
            len(PDF),
        )
        digest = hashlib.sha256(PDF).hexdigest()
        assert path_for(settings.files_dir, digest).read_bytes() == PDF
        assert len(list(settings.files_dir.rglob("*"))) == 2  # one directory, one file
        listed = await ok(client.get(f"/api/bills/{a_bill['id']}"))
        assert [a["id"] for a in listed["attachments"]] == [first["id"], second["id"]]

        response = await client.get(f"/api/attachments/{first['id']}")
        assert response.content == PDF
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-security-policy"].startswith("sandbox")
        assert "FT%20A%20100000001.pdf" in response.headers["content-disposition"]

    async def test_something_that_is_not_a_document_is_refused_and_not_kept(
        self, client, a_bill: dict, settings: Settings
    ) -> None:
        response = await _upload(
            client, b"<html><script>alert(1)</script>", "bill.pdf", bill_id=a_bill["id"]
        )

        assert (response.status_code, response.json()["detail"]) == (415, "unsupported_file")
        assert [p for p in settings.files_dir.rglob("*") if p.is_file()] == []

    async def test_refusing_a_file_keeps_bytes_another_attachment_holds(
        self, client, a_bill: dict, settings: Settings, monkeypatch
    ) -> None:
        await ok(_upload(client, PDF, bill_id=a_bill["id"]), 201)
        # The same bytes refused as unsupported: the file stays, since an attachment holds it.
        monkeypatch.setattr("house_cost.api.routers.attachments.sniff", lambda _head: None)
        assert (await _upload(client, PDF, bill_id=a_bill["id"])).status_code == 415
        assert path_for(settings.files_dir, hashlib.sha256(PDF).hexdigest()).is_file()

    async def test_a_file_over_the_limit_is_refused(
        self, client, a_bill: dict, settings: Settings, app
    ) -> None:
        app.state.services.settings.max_upload_bytes = 1024
        response = await _upload(client, PDF + b"\0" * 2048, bill_id=a_bill["id"])

        assert (response.status_code, response.json()["detail"]) == (413, "too_large")
        assert [p for p in settings.files_dir.rglob("*") if p.is_file()] == []

    async def test_a_photo_of_a_transfer_goes_on_a_settlement(
        self, client, agreement: Agreement
    ) -> None:
        settlement = await ok(
            client.post(
                "/api/settlements",
                json={
                    "date": "2026-11-01",
                    "from_id": agreement.owners,
                    "to_id": agreement.lucia,
                    "amount_cents": 100,
                },
            ),
            201,
        )
        photo = await ok(_upload(client, PNG, "receipt.png", settlement_id=settlement["id"]), 201)

        assert photo["content_type"] == "image/png"
        listed = await ok(client.get("/api/settlements"))
        assert listed[0]["attachments"][0]["id"] == photo["id"]

    @pytest.mark.parametrize("owner", [{}, {"bill_id": 1, "settlement_id": 1}])
    async def test_a_file_belongs_to_exactly_one_thing(self, client, a_bill: dict, owner) -> None:
        response = await _upload(client, PDF, **owner)
        assert (response.status_code, response.json()["detail"]) == (422, "one_owner")

    async def test_a_deleted_or_missing_owner_takes_nothing(self, client, a_bill: dict) -> None:
        await client.delete(f"/api/bills/{a_bill['id']}")
        assert (await _upload(client, PDF, bill_id=a_bill["id"])).status_code == 404
        assert (await _upload(client, PDF, settlement_id=999)).status_code == 404

    async def test_detached_but_the_bytes_stay(
        self, client, a_bill: dict, settings: Settings
    ) -> None:
        attached = await ok(_upload(client, PDF, bill_id=a_bill["id"]), 201)

        assert (await client.delete(f"/api/attachments/{attached['id']}")).status_code == 204
        assert (await client.get(f"/api/attachments/{attached['id']}")).status_code == 404
        assert (await ok(client.get(f"/api/bills/{a_bill['id']}")))["attachments"] == []
        assert path_for(settings.files_dir, hashlib.sha256(PDF).hexdigest()).is_file()

    async def test_a_file_missing_from_disk_is_a_404(
        self, client, a_bill: dict, settings: Settings
    ) -> None:
        attached = await ok(_upload(client, PDF, bill_id=a_bill["id"]), 201)
        path_for(settings.files_dir, hashlib.sha256(PDF).hexdigest()).unlink()

        response = await client.get(f"/api/attachments/{attached['id']}")
        assert (response.status_code, response.json()["detail"]) == (404, "file_missing")


async def test_a_large_scan_is_stored_whole(client, a_bill: dict, settings: Settings) -> None:
    # Larger than one read, so it arrives in several chunks.
    scan = PDF + bytes(range(256)) * 6000
    attached = await ok(_upload(client, scan, "scan.pdf", bill_id=a_bill["id"]), 201)

    assert attached["size"] == len(scan)
    assert (await client.get(f"/api/attachments/{attached['id']}")).content == scan
