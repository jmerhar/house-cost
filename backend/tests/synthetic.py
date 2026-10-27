"""PDFs made in the tests, standing in for real bills and contracts, which hold personal details
and stay out of the repository."""

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def pdf(*pages: list[str]) -> bytes:
    """A PDF with a text layer: each page's lines, top to bottom."""
    out = io.BytesIO()
    page = canvas.Canvas(out, pagesize=A4)
    for lines in pages:
        y = 800
        for line in lines:
            page.drawString(50, y, line)
            y -= 16
        page.showPage()
    page.save()
    return out.getvalue()


def image_only_pdf() -> bytes:
    """A PDF with a page and no text on it, as a scan is."""
    out = io.BytesIO()
    page = canvas.Canvas(out, pagesize=A4)
    page.rect(50, 50, 200, 200, fill=1)
    page.showPage()
    page.save()
    return out.getvalue()


def qr_png(text: str) -> bytes:
    """A QR code holding ``text``, as a PNG."""
    import segno

    out = io.BytesIO()
    segno.make(text, micro=False).save(out, kind="png", scale=6, border=4)
    return out.getvalue()


#: The fiscal QR code of MEO Energia's example invoice: issuer NIF, date, number, VAT and total.
MEO_ENERGIA_QR = (
    "A:506743357*B:123456789*C:PT*D:FT*E:N*F:20261018*G:FT FA.MEA26/100001*H:K7QX2M4T-100001"
    "*I1:PT*I3:3.40*I4:0.20*I7:230.89*I8:53.10*N:53.30*O:287.59*Q:Xy7Q*R:0030"
)

#: The text of MEO Energia's electricity bill, laid out as its first two pages are.
MEO_ENERGIA_PAGES = [
    [
        "MEO Energia - Comercializacao de Energia, S.A.",
        "Sede: Av. Fontes Pereira de Melo, 40 Lisboa - NIPC 506 743 357",
        "Fatura: FA MEA26/100 001 de 18/10/2026",
        "Periodo de faturacao: 13/09/2026 a 16/10/2026",
        "Data limite de pagamento: 03/11/2026",
        "CPE (Codigo Ponto de Entrega): PT0002000099999999ZZ",
        "Vigencia do contrato: Termina a 11/12/2026 (renovacao automatica)",
        "Fidelizacao: Nao aplicavel",
        "Total a pagar: EUR 287,59",
    ],
    [
        "CONSUMO",
        "Consumo em Simples | 13/09/2026 | 16/10/2026 | 1 284,00 (kWh) | € 0,1525 | € 195,81",
        "TOTAL | € 287,59",
    ],
]


def meo_energia_bill(*, qr: str | None = MEO_ENERGIA_QR, total: str = "287,59") -> bytes:
    """An electricity bill as MEO Energia lays it out, with its QR code unless ``qr`` is None."""
    from reportlab.lib.utils import ImageReader

    out = io.BytesIO()
    page = canvas.Canvas(out, pagesize=A4)
    for number, lines in enumerate(MEO_ENERGIA_PAGES):
        y = 800
        for line in lines:
            page.drawString(40, y, line.replace("287,59", total))
            y -= 16
        if number == 0 and qr:
            page.drawImage(ImageReader(io.BytesIO(qr_png(qr))), 380, 620, width=160, height=160)
        page.showPage()
    page.save()
    return out.getvalue()


#: MEO's telecom invoice: its first page and the detail page with its groups of items.
MEO_PAGES = [
    [
        "MEO - Servicos de Comunicacoes e Multimedia, S.A. NIPC 504 615 947",
        "Fatura No: FT A/100000001",
        "Data de Emissao: 21 setembro 2026",
        "Debito bancario a partir de 13 outubro 2026 Valor a Pagar € 19,98",
    ],
    [
        "Total Adesoes € 0,990",
        "Ativacao MEO Net Segura-oferta 3 meses 15 set 0,990 23,00",
        "M4 (TV+NET 500+VOZ+MOVEL 5GB) 14 set a 30 set 31,250 23,00",
        "Mensalidade de cartao adicional 14 set a 30 set 4,410 23,00",
        "Total Pacotes € 18,372",
        "Total Telemovel € 0,612",
        "Total Equipamentos € 0,000",
        "TOTAL DA FATURA O valor foi arredondado para centimos de euro. € 19,98",
        "Periodo de fidelizacao a decorrer no servico 1700000001 , ate 28 jul 2027.",
    ],
]


def meo_bill() -> bytes:
    """MEO's telecom invoice, with its items in groups."""
    return pdf(*MEO_PAGES)


def scanned(lines: list[str], *, qr: str | None = None, as_pdf: bool = True) -> bytes:
    """A page with no text layer, only an image of ``lines`` (and a QR code), as a scan or a photo
    of a bill is: a PDF wrapping the image, or the PNG itself."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("L", (1700, 2200), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=44)
    y = 120
    for line in lines:
        draw.text((100, y), line, fill=0, font=font)
        y += 80
    if qr:
        image.paste(
            Image.open(io.BytesIO(qr_png(qr))).convert("L").resize((500, 500)), (1100, 1500)
        )
    png = io.BytesIO()
    image.save(png, format="PNG")
    if not as_pdf:
        return png.getvalue()
    from reportlab.lib.utils import ImageReader

    out = io.BytesIO()
    page = canvas.Canvas(out, pagesize=A4)
    page.drawImage(ImageReader(io.BytesIO(png.getvalue())), 0, 0, width=A4[0], height=A4[1])
    page.showPage()
    page.save()
    return out.getvalue()
