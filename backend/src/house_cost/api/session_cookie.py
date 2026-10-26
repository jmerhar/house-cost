"""Setting and clearing the session cookie, and describing the person it logs in."""

from fastapi import Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import get_setting
from ..auth import SESSION_LIFETIME
from ..config import Settings
from ..models import Person
from ..notify import EVENTS
from .deps import SESSION_COOKIE
from .schemas import Me


def is_secure(request: Request, settings: Settings) -> bool:
    """Whether the cookie gets the Secure flag: as configured, else when the request is HTTPS."""
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    return request.url.scheme == "https"


def issue(response: Response, request: Request, settings: Settings, token: str) -> None:
    """Put a session token in the browser.

    HttpOnly, so no script can read it; SameSite=Lax, so a page elsewhere cannot send it with a
    write, while a link to the app from an email still arrives logged in.
    """
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=is_secure(request, settings),
        path="/",
    )


def clear(response: Response, request: Request, settings: Settings) -> None:
    """Remove the session token from the browser."""
    response.delete_cookie(
        SESSION_COOKIE, httponly=True, samesite="lax", secure=is_secure(request, settings), path="/"
    )


async def describe(
    db: AsyncSession,
    person: Person,
    claude_enabled: bool,
    notify_channels: list[str],
    phone_country_code: str,
) -> Me:
    """The person logged in, as the interface sees them, and what the app can do for them."""
    return Me(
        id=person.id,
        name=person.name,
        login=person.login,
        role=person.role,
        language=person.language,
        household_id=person.household_id,
        active=person.active,
        household_name=person.household.name,
        reconciliation_enabled=await get_setting(db, "reconciliation_enabled"),
        claude_enabled=claude_enabled,
        email=person.email,
        phone=person.phone,
        notify_channels=notify_channels,
        phone_country_code=phone_country_code,
        notify_on={event: person.notify_on.get(event, True) for event in EVENTS},
    )
