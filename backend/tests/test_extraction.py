"""Reading bills: the fiscal QR code, text helpers, OCR, the parsers and the pipeline."""

import os
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest
from PIL import Image
from synthetic import MEO_ENERGIA_QR, meo_bill, meo_energia_bill, pdf, qr_png, scanned

from house_cost.extraction import atcud, ocr
from house_cost.extraction.parsers import Findings, generic, meo, meo_energia, parse
from house_cost.extraction.pipeline import Extraction, _balance, extract
from house_cost.extraction.text import after, cents, day, nifs, number, plain

KNOWN = {"506743357", "504615947"}

#: OCR needs Tesseract: required where REQUIRE_TESSERACT is set (CI and the image's checks),
#: skipped on a machine without it.
needs_tesseract = pytest.mark.skipif(
    shutil.which("tesseract") is None and not os.environ.get("REQUIRE_TESSERACT"),
    reason="tesseract is not installed",
)


def _file(tmp_path: Path, data: bytes, name: str = "bill") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


class TestAtcud:
    def test_reads_the_invoices_fields(self) -> None:
        code = atcud.parse(MEO_ENERGIA_QR)

        assert code == atcud.Atcud(
            issuer_nif="506743357",
            customer_nif="123456789",
            kind="FT",
            on=date(2026, 10, 18),
            number="FT FA.MEA26/100001",
            atcud="K7QX2M4T-100001",
            tax_cents=5330,
            total_cents=28759,
        )

    @pytest.mark.parametrize(
        "text", ["https://example.com", "A:12345*O:1.00", "A:506743357*B:x", "", "A:506743357"]
    )
    def test_anything_else_is_not_one(self, text: str) -> None:
        assert atcud.parse(text) is None

    def test_odd_values_are_left_out(self) -> None:
        code = atcud.parse("A:506743357*B:Consumidor final*F:20261340*O:abc")

        assert (code.customer_nif, code.on, code.total_cents) == (None, None, None)
        assert atcud.parse("A:506743357*F:2026*O:1").on is None

    def test_finds_the_code_in_an_image(self) -> None:
        import io

        image = Image.open(io.BytesIO(qr_png(MEO_ENERGIA_QR)))
        assert atcud.find([image]).total_cents == 28759
        assert atcud.find([Image.new("L", (100, 100), 255)]) is None
        assert atcud.find([Image.open(io.BytesIO(qr_png("not an invoice")))]) is None


class TestText:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("287,59", 28759),
            ("1 284,00", 128400),
            ("1.234,56", 123456),
            ("19.98", 1998),
            ("17,663", 1766),
            ("0,805", 81),
            ("-0,501", -50),
            ("5", 500),
            ("abc", None),
            ("1,2,3", None),
        ],
    )
    def test_cents(self, text: str, expected: int | None) -> None:
        assert cents(text) == expected

    def test_number(self) -> None:
        assert number("1 284,00") == 1284.0
        assert number("0,1525") == 0.1525
        assert number("12.5") == 12.5
        assert number("x") is None

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("18/10/2026", date(2026, 10, 18)),
            ("3-11-2026", date(2026, 11, 3)),
            ("21 setembro 2026", date(2026, 9, 21)),
            ("28 jul 2027", date(2027, 7, 28)),
            ("1 de Março de 2027", date(2027, 3, 1)),
            ("31/02/2026", None),
            ("23 blah 2026", None),
            ("tomorrow", None),
        ],
    )
    def test_day(self, text: str, expected: date | None) -> None:
        assert day(text) == expected

    def test_plain_folds_accents_and_odd_euro_signs(self) -> None:
        assert plain("Período de Faturação Nº \x80 5") == "periodo de faturacao no € 5"

    def test_after_finds_a_value_on_the_line_or_the_next(self) -> None:
        assert after("Total a pagar: € 287,59", "total a pagar") == "287,59"
        assert after("Total a pagar\n€ 9,99", "total a pagar") == "9,99"
        assert after("Nothing here", "total a pagar") is None

    def test_nifs(self) -> None:
        assert nifs("NIPC 506 743 357 · 504615947 · 12345678 · 1234567890") == {
            "506743357",
            "504615947",
        }


class TestParsers:
    def test_generic_reads_what_invoices_share(self) -> None:
        found = generic(
            "Fatura N.º: FT 2026/42\nData de emissão: 03/02/2027\nTotal a pagar: 48,68 €\n"
            "Data limite de pagamento: 20/02/2027\nPeríodo de faturação: 01/01/2027 a 31/01/2027"
        )
        assert (found.invoice_number, found.on, found.total_cents) == (
            "FT 2026/42",
            date(2027, 2, 3),
            4868,
        )
        assert (found.due_date, found.period_start, found.period_end) == (
            date(2027, 2, 20),
            date(2027, 1, 1),
            date(2027, 1, 31),
        )

    def test_generic_reads_nothing_from_nothing(self) -> None:
        assert generic("hello") == Findings()

    def test_meo_energia_reads_consumption_cpe_and_contract(self) -> None:
        text = "\n".join(line for page in meo_energia_text() for line in page)
        found = meo_energia(text)

        assert found.readings[0].value == 1284.0 and found.readings[0].unit_price == 0.1525
        assert found.identifiers == {"CPE": "PT0002000099999999ZZ"}
        assert (found.ends_on, found.renews_automatically, found.lock_in_until) == (
            date(2026, 12, 11),
            True,
            None,
        )

    def test_meo_energia_reads_a_fixed_term_and_a_lock_in(self) -> None:
        found = meo_energia(
            "Termina a 01/06/2027\nFidelização: até 01/06/2027\nConsumo em Simples 10 (kWh) x"
        )
        assert (found.ends_on, found.renews_automatically, found.lock_in_until) == (
            date(2027, 6, 1),
            False,
            date(2027, 6, 1),
        )
        assert found.readings == []

    def test_meo_reads_its_groups_and_lock_in(self) -> None:
        found = meo("\n".join(line for page in meo_text() for line in page))

        assert found.total_cents == 1998
        assert found.lines == [("Package", 1837), ("Mobile", 61), ("Activation", 99)]
        assert found.lock_in_until == date(2027, 7, 28)
        assert found.identifiers == {"Serviço": "1700000001"}

    def test_the_supplier_picks_the_parser(self) -> None:
        text = "Consumo em Simples 1 (kWh) € 0,10\nTotal a pagar 1,00"
        assert parse(text, "506743357").readings
        assert not parse(text, "999999999").readings
        assert not parse(text, None).readings


def meo_energia_text():
    from synthetic import MEO_ENERGIA_PAGES

    return MEO_ENERGIA_PAGES


def meo_text():
    from synthetic import MEO_PAGES

    return MEO_PAGES


class TestOcr:
    def test_text_with_too_few_letters_or_vowels_is_unusable(self) -> None:
        assert ocr.unusable("")
        assert ocr.unusable("12 34 / 56")
        assert not ocr.unusable("TOTAL | € 287,59")
        assert ocr.unusable("dddd ddddd dd ddddddd dddd ddddd dddddd dddddd ddd dd")
        assert not ocr.unusable("Fatura de eletricidade do periodo de setembro a outubro")

    def test_without_tesseract_it_says_so(self, monkeypatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda _: None)
        ocr.languages.cache_clear()
        try:
            with pytest.raises(ocr.OcrUnavailable):
                ocr.languages()
            with pytest.raises(ocr.OcrUnavailable):
                ocr.read(Image.new("L", (10, 10)))
        finally:
            ocr.languages.cache_clear()

    def test_languages_fall_back_to_english(self, monkeypatch) -> None:
        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/tesseract")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **_k: subprocess.CompletedProcess(a, 0, stdout="List:\nosd\n"),
        )
        ocr.languages.cache_clear()
        try:
            assert ocr.languages() == "eng"
        finally:
            ocr.languages.cache_clear()

    def test_a_page_that_takes_too_long_reads_as_nothing(self, monkeypatch) -> None:
        def slow(*args, **kwargs):
            if "--list-langs" in args[0]:
                return subprocess.CompletedProcess(args, 0, stdout="eng\n")
            raise subprocess.TimeoutExpired(args[0], 1)

        monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/tesseract")
        monkeypatch.setattr(subprocess, "run", slow)
        ocr.languages.cache_clear()
        try:
            assert ocr.read(Image.new("L", (10, 10))) == ""
        finally:
            ocr.languages.cache_clear()


class TestPipeline:
    def test_a_pdf_with_text_and_a_qr_code(self, tmp_path: Path) -> None:
        result = extract(_file(tmp_path, meo_energia_bill()), "application/pdf", KNOWN)
        found = result.findings

        assert (result.issuer_nif, result.text_source) == ("506743357", "text")
        assert (found.invoice_number, found.on, found.total_cents) == (
            "FT FA.MEA26/100001",
            date(2026, 10, 18),
            28759,
        )
        assert result.sources["total_cents"] == "qr" and result.sources["period_start"] == "text"
        assert result.sources["readings"] == "text"
        assert result.warnings == []

    def test_a_page_total_that_disagrees_with_the_qr_code_is_flagged(self, tmp_path: Path) -> None:
        result = extract(
            _file(tmp_path, meo_energia_bill(total="300,00")), "application/pdf", KNOWN
        )

        assert result.findings.total_cents == 28759
        assert result.warnings == ["total_mismatch"]

    def test_without_a_qr_code_the_supplier_is_found_by_its_nif(self, tmp_path: Path) -> None:
        result = extract(_file(tmp_path, meo_bill()), "application/pdf", KNOWN)

        assert result.issuer_nif == "504615947"
        assert result.findings.lines == [("Package", 1838), ("Mobile", 61), ("Activation", 99)]
        assert result.sources["lines"] == "text"

    def test_a_supplier_with_a_parser_is_read_in_full_before_it_is_on_file(
        self, tmp_path: Path
    ) -> None:
        result = extract(_file(tmp_path, meo_bill()), "application/pdf", set())

        assert (result.issuer_nif, result.supplier_name) == ("504615947", "MEO")
        assert result.findings.lines == [("Package", 1838), ("Mobile", 61), ("Activation", 99)]

    def test_a_supplier_on_file_comes_before_one_only_known_to_the_parsers(
        self, tmp_path: Path
    ) -> None:
        data = pdf(["MEO NIPC 504615947", "Faturado por 501234567", "Total a pagar: 5,00"])
        result = extract(_file(tmp_path, data), "application/pdf", {"501234567"})

        assert (result.issuer_nif, result.supplier_name) == ("501234567", None)

    def test_an_unknown_suppliers_bill_gets_the_generic_parser(self, tmp_path: Path) -> None:
        result = extract(
            _file(tmp_path, pdf(["Fatura N.o: FT 9/9 de 01/02/2027", "Total a pagar: 12,00"])),
            "application/pdf",
            KNOWN,
        )
        assert (result.issuer_nif, result.findings.total_cents) == (None, 1200)

    @needs_tesseract
    def test_a_scan_is_read_by_ocr(self, tmp_path: Path) -> None:
        data = scanned(
            [
                "MEO - NIPC 504 615 947",
                "Fatura No: FT A/100000001",
                "Data de Emissao: 21 setembro 2026",
                "Valor a Pagar € 19,98",
            ]
        )
        result = extract(_file(tmp_path, data), "application/pdf", KNOWN)

        assert (result.text_source, result.issuer_nif) == ("ocr", "504615947")
        assert (result.findings.total_cents, result.findings.on) == (1998, date(2026, 9, 21))

    @needs_tesseract
    def test_a_photo_is_read_by_ocr_and_its_qr_code(self, tmp_path: Path) -> None:
        data = scanned(
            ["Fatura: X de 18/10/2026", "Total a pagar: 287,59"], qr=MEO_ENERGIA_QR, as_pdf=False
        )
        result = extract(_file(tmp_path, data), "image/png", KNOWN)

        assert (result.text_source, result.issuer_nif, result.findings.total_cents) == (
            "ocr",
            "506743357",
            28759,
        )

    def test_a_scan_still_gets_its_qr_code_without_tesseract(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setattr(shutil, "which", lambda _: None)
        ocr.languages.cache_clear()
        try:
            data = scanned(["unreadable without OCR"], qr=MEO_ENERGIA_QR)
            result = extract(_file(tmp_path, data), "application/pdf", KNOWN)
        finally:
            ocr.languages.cache_clear()

        assert (result.findings.total_cents, result.sources["total_cents"]) == (28759, "qr")

    def test_an_image_that_will_not_open_reads_as_nothing(self, tmp_path: Path) -> None:
        result = extract(_file(tmp_path, b"\x89PNG\r\n\x1a\nbroken"), "image/png", KNOWN)

        assert (result.text_source, result.findings) == ("none", Findings())

    def test_lines_that_miss_the_total_by_more_than_rounding_are_dropped(self) -> None:
        extraction = Extraction(findings=Findings(total_cents=1000, lines=[("A", 500), ("B", 400)]))
        extraction.sources["lines"] = "text"
        _balance(extraction)

        assert extraction.findings.lines == []
        assert extraction.warnings == ["lines_dropped"]
        assert "lines" not in extraction.sources

    def test_balancing_leaves_lines_without_a_total_alone(self) -> None:
        extraction = Extraction(findings=Findings(lines=[("A", 500)]))
        _balance(extraction)
        assert extraction.findings.lines == [("A", 500)]


#: Real bills, kept out of the repository, read when `make test-samples` points SAMPLES_DIR at
#: them; samples/expected.json there says what each must give, by file name.
SAMPLES = Path(os.environ.get("SAMPLES_DIR", "")) if os.environ.get("SAMPLES_DIR") else None


@pytest.mark.skipif(SAMPLES is None, reason="SAMPLES_DIR is not set")
def test_real_samples() -> None:  # pragma: no cover - runs only against local, private files
    import json

    expected = json.loads((SAMPLES / "expected.json").read_text())
    for name, want in expected.items():
        result = extract(SAMPLES / name, want.pop("content_type", "application/pdf"), KNOWN)
        got = {
            "issuer_nif": result.issuer_nif,
            "total_cents": result.findings.total_cents,
            "on": str(result.findings.on),
            "invoice_number": result.findings.invoice_number,
            "lines": [list(line) for line in result.findings.lines],
            "kwh": result.findings.readings[0].value if result.findings.readings else None,
            "lock_in_until": str(result.findings.lock_in_until),
            "ends_on": str(result.findings.ends_on),
        }
        assert {key: got[key] for key in want} == want, name
