"""The web app manifest: what a phone needs to add the app to its home screen as an app."""

from fastapi import Request
from jigkit.web import manifest_router

from ..audit import get_setting
from ..db import session_scope

#: The app's name and description in each language the interface has.
WORDS = {
    "en": ("House costs", "Shared running costs of the house, split between the households"),
    "pt-PT": ("Despesas da casa", "As despesas partilhadas da casa, divididas entre as famílias"),
}
#: The splash screen behind the icon while the app opens, and the colour of the system bars.
BACKGROUND = "#f7f6f2"
THEME = "#2f6f5e"


async def site_title(request: Request) -> str | None:
    """The name an admin gave the app, if any."""
    async with session_scope(request.app.state.services.sessionmaker) as db:
        return await get_setting(db, "site_title")


router = manifest_router(WORDS, background_color=BACKGROUND, theme_color=THEME, name=site_title)
