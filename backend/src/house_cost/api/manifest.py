"""The web app manifest: what a phone needs to add the app to its home screen as an app."""

from typing import Annotated

from fastapi import APIRouter, Header, Response
from fastapi.responses import JSONResponse

router = APIRouter()

#: The app's name and description in each language the interface has.
WORDS = {
    "en": ("House costs", "Shared running costs of the house, split between the households"),
    "pt-PT": ("Despesas da casa", "As despesas partilhadas da casa, divididas entre as famílias"),
}
#: The splash screen behind the icon while the app opens, and the colour of the system bars.
BACKGROUND = "#f7f6f2"
THEME = "#2f6f5e"


def language(accept_language: str | None) -> str:
    """The interface's language that the browser prefers: Portuguese if it asks for any, else
    English."""
    for part in (accept_language or "").split(","):
        tag = part.split(";")[0].strip().lower()
        if tag == "pt" or tag.startswith("pt-"):
            return "pt-PT"
        if tag == "en" or tag.startswith("en-"):
            return "en"
    return "en"


def manifest(lang: str) -> dict[str, object]:
    """The manifest, its words in ``lang``."""
    name, description = WORDS[lang]
    icon = "/icons/icon-{size}.png"
    return {
        "name": name,
        "short_name": name,
        "description": description,
        "lang": lang,
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": BACKGROUND,
        "theme_color": THEME,
        "icons": [
            {
                "src": icon.format(size=192),
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": icon.format(size=512),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            # The same drawing: it keeps to the centre, so a launcher's crop leaves it whole.
            {
                "src": icon.format(size=512),
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
    }


@router.get("/manifest.webmanifest", include_in_schema=False)
async def get_manifest(accept_language: Annotated[str | None, Header()] = None) -> Response:
    """The manifest, in the browser's language, since the browser fetches it itself and sends no
    session or account language with it."""
    lang = language(accept_language)
    return JSONResponse(
        manifest(lang),
        media_type="application/manifest+json",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Language": lang,
            "Vary": "Accept-Language",
        },
    )
