"""Adding the app to a home screen: the manifest, and the icons it and the page name."""

import re
import struct
from pathlib import Path

from house_cost.api.manifest import language, manifest

WEB = Path(__file__).resolve().parents[2] / "frontend"


def png(path: Path) -> tuple[int, int, int]:
    """A PNG's width, height and colour type, from its header."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", path
    width, height, _, colour = struct.unpack(">IIBB", data[16:26])
    return width, height, colour


async def test_the_manifest_opens_the_app_on_its_own(client) -> None:
    response = await client.get("/manifest.webmanifest")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/manifest+json"
    found = response.json()
    assert (found["name"], found["start_url"], found["scope"], found["display"]) == (
        "House costs",
        "/",
        "/",
        "standalone",
    )
    purposes = {(icon["sizes"], icon["purpose"]) for icon in found["icons"]}
    # What Chrome asks of an installable app: a 192 and a 512 icon, and one it may crop.
    assert {("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")} <= purposes


async def test_the_manifest_is_in_the_browsers_language(client) -> None:
    portuguese = await client.get(
        "/manifest.webmanifest", headers={"Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8"}
    )

    assert (portuguese.json()["name"], portuguese.json()["lang"]) == ("Despesas da casa", "pt-PT")
    assert portuguese.headers["content-language"] == "pt-PT"
    assert portuguese.headers["cache-control"] == "no-cache"
    assert portuguese.headers["vary"] == "Accept-Language"


def test_the_browsers_first_known_language_is_taken() -> None:
    assert [language(h) for h in (None, "", "de-DE,pt;q=0.5", "en-GB,pt", "fr", "pt-BR")] == [
        "en",
        "en",
        "pt-PT",
        "en",
        "en",
        "pt-PT",
    ]


def test_every_icon_named_exists_at_its_size_and_is_opaque() -> None:
    """A home screen fills a transparent icon with a colour of its own, so none may have alpha."""
    named = [(icon["src"], icon["sizes"]) for icon in manifest("en")["icons"]]  # type: ignore[union-attr]
    page = (WEB / "index.html").read_text(encoding="utf-8")
    touch = re.search(r'rel="apple-touch-icon" href="([^"]+)"', page)
    assert touch is not None
    # iOS asks for 180 px.
    named.append((touch.group(1), "180x180"))
    for src, sizes in named:
        width, height, colour = png(WEB / "public" / src.lstrip("/"))
        assert f"{width}x{height}" == sizes, src
        # Colour types 4 and 6 carry alpha.
        assert colour not in (4, 6), src


def test_the_page_links_the_manifest() -> None:
    page = (WEB / "index.html").read_text(encoding="utf-8")

    assert '<link rel="manifest" href="/manifest.webmanifest" />' in page
    assert '<meta name="apple-mobile-web-app-capable" content="yes" />' in page
