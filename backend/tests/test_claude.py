"""Claude, when an API key is set: through the real SDK, against a stand-in for the API."""

import base64
import json
from pathlib import Path

import httpx2
import pytest
from helpers import ok
from synthetic import meo_energia_bill, pdf
from test_api_papers import _upload
from test_api_reading import read

from house_cost.claude import BillRead, Claude, ClaudeFailed, LineRead, cents_or_none, day_or_none
from house_cost.config import Settings
from house_cost.extraction.parsers import Findings
from house_cost.extraction.pipeline import Extraction, merge_claude, worth_asking_claude

#: A bill from a supplier no parser knows: the generic reading finds its total, not its number.
UNKNOWN_BILL = pdf(["Aguas do Vale, S.A.", "Data de emissao 02-10-2026", "Total a pagar 41,30 EUR"])


class Api:
    """Answers the Messages API as Claude would, and keeps what each request asked."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.status = 200
        self.content: list[dict] = []
        self.stop_reason = "end_turn"

    def answer(self, value: dict) -> None:
        """Answer with ``value`` as the structured output."""
        self.content = [{"type": "text", "text": json.dumps(value)}]

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content))
        if self.status != 200:
            error = {"type": "invalid_request_error", "message": "no"}
            return httpx2.Response(self.status, json={"type": "error", "error": error})
        message = {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-opus-5-5",
            "content": self.content,
            "stop_reason": self.stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
        }
        return httpx2.Response(200, json=message)


@pytest.fixture
def api() -> Api:
    return Api()


@pytest.fixture
def claude(api: Api) -> Claude:
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(api.handler))
    return Claude("test-key", "claude-opus-5-5", http_client=client)


@pytest.fixture
def with_claude(app, claude: Claude) -> Claude:
    app.state.services.claude = claude
    return claude


class TestClient:
    async def test_a_bill_is_sent_as_a_pdf_and_read_into_its_schema(self, claude, api) -> None:
        api.answer({"supplier_name": "Águas do Vale", "total": "41.30", "lines": []})
        read_back = await claude.read_bill(b"%PDF-1.7 bill", "application/pdf")

        assert (read_back.supplier_name, read_back.total) == ("Águas do Vale", "41.30")
        sent = api.requests[0]
        assert sent["model"] == "claude-opus-5-5"
        document = sent["messages"][0]["content"][0]
        assert document["type"] == "document"
        assert base64.b64decode(document["source"]["data"]) == b"%PDF-1.7 bill"
        assert sent["output_config"]["format"]["type"] == "json_schema"

    async def test_a_photo_is_sent_as_an_image(self, claude, api) -> None:
        api.answer({"summary": "Fine."})
        await claude.read_terms(b"\x89PNG", "image/png", "pt-PT")

        content = api.requests[0]["messages"][0]["content"]
        assert content[0]["type"] == "image"
        assert "European Portuguese" in content[1]["text"]

    async def test_a_refusal_or_an_error_is_a_failure_with_its_reason(self, claude, api) -> None:
        api.answer({"summary": "x"})
        api.stop_reason = "refusal"
        with pytest.raises(ClaudeFailed) as declined:
            await claude.read_terms(b"%PDF", "application/pdf", "en")
        api.status = 400
        with pytest.raises(ClaudeFailed) as failed:
            await claude.read_bill(b"%PDF", "application/pdf")
        with pytest.raises(ClaudeFailed) as failed_question:
            await claude.ask(b"%PDF", "application/pdf", "Why?", "en")

        assert (declined.value.code, failed.value.code) == ("claude_declined", "claude_failed")
        assert failed_question.value.code == "claude_failed"

    async def test_an_answer_cites_its_pages(self, claude, api) -> None:
        api.content = [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": "The lock-in lasts "},
            {
                "type": "text",
                "text": "24 months.",
                "citations": [
                    {
                        "type": "page_location",
                        "cited_text": " Período de fidelização: 24 meses ",
                        "document_index": 0,
                        "document_title": None,
                        "start_page_number": 2,
                        "end_page_number": 3,
                    }
                ],
            },
        ]
        answer = await claude.ask(b"%PDF", "application/pdf", "How long is the lock-in?", "en")

        assert answer.text == "The lock-in lasts 24 months."
        assert [(c.page, c.quote) for c in answer.citations] == [
            (2, "Período de fidelização: 24 meses")
        ]
        document = api.requests[0]["messages"][0]["content"][0]
        assert document["citations"] == {"enabled": True}

    async def test_a_refused_question(self, claude, api) -> None:
        api.stop_reason = "refusal"
        with pytest.raises(ClaudeFailed, match="claude_declined"):
            await claude.ask(b"%PDF", "application/pdf", "Why?", "en")


class TestValues:
    @pytest.mark.parametrize(
        ("text", "cents"),
        [
            ("287.59", 28759),
            ("€ 1 234,50", 123450),
            ("1.234,50", 123450),
            ("1,234.50", 123450),
            ("41", 4100),
            ("about forty", None),
            (None, None),
        ],
    )
    def test_euros_as_claude_may_write_them(self, text, cents) -> None:
        assert cents_or_none(text) == cents

    def test_dates_only_as_iso(self) -> None:
        assert [day_or_none(v) for v in ("2026-10-18", "18/10/2026", "", None)] == [
            day_or_none("2026-10-18"),
            None,
            None,
            None,
        ]
        assert str(day_or_none(" 2026-10-18 ")) == "2026-10-18"


class TestMerge:
    def test_fills_only_what_is_missing_and_says_so(self) -> None:
        extraction = Extraction(
            findings=Findings(total_cents=4130), sources={"total_cents": "text"}
        )
        merge_claude(
            extraction,
            BillRead(
                supplier_name=" Águas do Vale ",
                supplier_nif="505 000 000",
                invoice_number=" FT 2026/77 ",
                date="2026-10-02",
                period_start="not a date",
                total="99.00",
                lines=[
                    LineRead(description="Água", amount="30.00"),
                    LineRead(description="Saneamento", amount="11.31"),
                ],
            ),
        )

        findings = extraction.findings
        assert (findings.total_cents, extraction.sources["total_cents"]) == (4130, "text")
        assert (findings.invoice_number, str(findings.on)) == ("FT 2026/77", "2026-10-02")
        assert findings.period_start is None
        assert (extraction.issuer_nif, extraction.supplier_name) == ("505000000", "Águas do Vale")
        assert findings.lines == [("Água", 2999), ("Saneamento", 1131)]
        assert {extraction.sources[k] for k in ("invoice_number", "on", "issuer_nif", "lines")} == {
            "claude"
        }

    def test_what_the_page_gave_stands(self) -> None:
        extraction = Extraction(
            findings=Findings(invoice_number="FT A/1"), sources={"invoice_number": "text"}
        )
        merge_claude(extraction, BillRead(invoice_number="FT B/2"))

        assert (extraction.findings.invoice_number, extraction.sources["invoice_number"]) == (
            "FT A/1",
            "text",
        )

    def test_lines_that_do_not_make_the_total_are_dropped(self) -> None:
        extraction = Extraction(findings=Findings(total_cents=4130))
        merge_claude(extraction, BillRead(lines=[LineRead(description="Água", amount="10.00")]))

        assert extraction.findings.lines == []
        assert "lines_dropped" in extraction.warnings

    def test_unreadable_lines_and_a_wrong_nif_are_left_out(self) -> None:
        extraction = Extraction(findings=Findings())
        merge_claude(
            extraction,
            BillRead(
                supplier_nif="12345", total="5.00", lines=[LineRead(description="Água", amount="?")]
            ),
        )

        assert (extraction.issuer_nif, extraction.findings.lines) == (None, [])
        assert extraction.findings.total_cents == 500

    def test_claude_is_asked_only_where_it_could_add_something(self) -> None:
        complete = Findings(on=day_or_none("2026-10-18"), invoice_number="A/1", total_cents=1)
        assert not worth_asking_claude(Extraction(findings=complete, issuer_nif="506743357"))
        assert worth_asking_claude(Extraction(findings=complete, issuer_nif="500000000"))
        assert worth_asking_claude(Extraction(findings=Findings(), issuer_nif="506743357"))


class TestReadingABill:
    async def test_claude_fills_in_a_bill_no_parser_knows(
        self, client, admin, with_claude, api
    ) -> None:
        api.answer(
            {
                "supplier_name": "Águas do Vale",
                "supplier_nif": "505000000",
                "invoice_number": "FT 2026/77",
                "date": "2026-10-01",
                "total": "41.30",
                "lines": [],
            }
        )
        proposal = await ok(read(client, UNKNOWN_BILL))

        assert proposal["supplier_name"] == "Águas do Vale"
        assert (proposal["invoice_number"], proposal["sources"]["invoice_number"]) == (
            "FT 2026/77",
            "claude",
        )
        # The page's own date and total stand.
        assert (proposal["date"], proposal["total_cents"]) == ("2026-10-02", 4130)
        assert proposal["sources"]["total_cents"] == "text"

    async def test_a_failed_request_leaves_the_local_reading(
        self, client, admin, with_claude, api
    ) -> None:
        api.status = 400
        proposal = await ok(read(client, UNKNOWN_BILL))

        assert proposal["total_cents"] == 4130
        assert "claude_failed" in proposal["warnings"]

    async def test_a_bill_read_in_full_does_not_ask(
        self, client, admin, with_claude, api, agreement
    ) -> None:
        await ok(
            client.post("/api/suppliers", json={"name": "MEO Energia", "nif": "506743357"}), 201
        )
        await ok(read(client, meo_energia_bill()))

        assert api.requests == []


class TestDocuments:
    async def test_without_a_key_the_routes_do_not_exist(self, client, admin) -> None:
        document = await ok(_upload(client, pdf(["Contrato"])), 201)
        me = await ok(client.get("/api/auth/me"))
        refused = await client.post(f"/api/documents/{document['id']}/terms")

        assert me["claude_enabled"] is False
        assert (refused.status_code, refused.json()["detail"]) == (404, "claude_off")

    async def test_a_contracts_terms_are_proposed(self, client, admin, with_claude, api) -> None:
        document = await ok(_upload(client, pdf(["Contrato"])), 201)
        api.answer(
            {
                "service_name": "Internet",
                "supplier_name": "MEO",
                "starts_on": "2025-07-28",
                "ends_on": "2027-07-28",
                "renews_automatically": True,
                "lock_in_until": "28/07/2027",
                "notice_days": 0,
                "billed_every_days": 30,
                "summary": " 24 months' lock-in. ",
            }
        )
        terms = await ok(client.post(f"/api/documents/{document['id']}/terms"))

        assert (await ok(client.get("/api/auth/me")))["claude_enabled"] is True
        assert terms == {
            "service_name": "Internet",
            "supplier_name": "MEO",
            "starts_on": "2025-07-28",
            "ends_on": "2027-07-28",
            "renews_automatically": True,
            "lock_in_until": None,
            "notice_days": None,
            "billed_every_days": 30,
            "summary": "24 months' lock-in.",
        }

    async def test_a_question_is_answered_in_the_persons_language(
        self, client, admin, with_claude, api
    ) -> None:
        document = await ok(_upload(client, pdf(["Contrato"])), 201)
        await ok(client.patch("/api/auth/me", json={"name": "Lúcia", "language": "pt-PT"}))
        api.content = [{"type": "text", "text": "24 meses."}]
        answer = await ok(
            client.post(f"/api/documents/{document['id']}/ask", json={"question": " Fidelização? "})
        )

        assert answer == {"text": "24 meses.", "citations": []}
        prompt = api.requests[0]["messages"][0]["content"][1]["text"]
        assert "European Portuguese" in prompt and prompt.endswith("Fidelização?")

    async def test_refusals_and_missing_files(self, client, admin, with_claude, api, app) -> None:
        document = await ok(_upload(client, pdf(["Contrato"])), 201)
        blank = await client.post(f"/api/documents/{document['id']}/ask", json={"question": " "})
        api.stop_reason = "refusal"
        declined = await client.post(f"/api/documents/{document['id']}/terms")
        api.status = 400
        failed = await client.post(f"/api/documents/{document['id']}/ask", json={"question": "?"})
        for path in Path(app.state.services.settings.files_dir).rglob("*"):
            if path.is_file():
                path.unlink()
        missing = await client.post(f"/api/documents/{document['id']}/terms")

        assert blank.status_code == 422
        assert (declined.status_code, declined.json()["detail"]) == (502, "claude_declined")
        assert (failed.status_code, failed.json()["detail"]) == (502, "claude_failed")
        assert (missing.status_code, missing.json()["detail"]) == (404, "file_missing")


class TestSettings:
    def test_the_key_from_the_variable_or_a_file(self, data_dir: Path) -> None:
        secret = data_dir / "key"
        secret.write_text("sk-from-file\n")
        empty = data_dir / "empty"
        empty.write_text("\n")

        assert Settings(anthropic_api_key=" sk-direct ").claude_key == "sk-direct"
        assert Settings(anthropic_api_key="", anthropic_api_key_file=secret).claude_key == (
            "sk-from-file"
        )
        assert Settings(anthropic_api_key_file=empty).claude_key is None
        assert Settings(anthropic_api_key="", anthropic_api_key_file="").claude_key is None

    def test_a_key_builds_claude(self, data_dir: Path) -> None:
        from house_cost.api.deps import build_services

        assert build_services(Settings(data_dir=data_dir)).claude is None
        with_key = build_services(Settings(data_dir=data_dir, anthropic_api_key="sk-test"))
        assert with_key.claude is not None and with_key.claude.model == "claude-opus-5-5"
