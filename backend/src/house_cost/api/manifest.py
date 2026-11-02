"""The web app manifest: what a phone needs to add the app to its home screen as an app."""

from typing import Annotated

from fastapi import APIRouter, Header, Response
from jigkit.web import manifest_response, preferred_language, web_manifest

from ..audit import get_setting
from .deps import DbDep

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
    """The interface's language the browser prefers: Portuguese if it asks for any, else English."""
    return preferred_language(accept_language, WORDS, "en")


def manifest(lang: str, title: str = "") -> dict[str, object]:
    """The manifest, its words in ``lang``, and named ``title`` when the app has one set."""
    name, description = WORDS[lang]
    return web_manifest(
        name=title or name,
        description=description,
        lang=lang,
        background_color=BACKGROUND,
        theme_color=THEME,
    )


@router.get("/manifest.webmanifest", include_in_schema=False)
async def get_manifest(
    db: DbDep, accept_language: Annotated[str | None, Header()] = None
) -> Response:
    """The manifest, in the browser's language, since the browser fetches it itself and sends no
    session or account language with it."""
    lang = language(accept_language)
    return manifest_response(manifest(lang, await get_setting(db, "site_title")))
