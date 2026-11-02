"""Setting and clearing the session cookie, and describing the person it logs in."""

from fastapi import Request, Response
from jigkit.auth import clear_session_cookie, issue_session_cookie
from sqlalchemy.ext.asyncio import AsyncSession

from ..audit import get_setting
from ..auth import SESSION_LIFETIME
from ..config import Settings
from ..models import Person
from ..notify import EVENTS
from .deps import SESSION_COOKIE
from .schemas import Me


def issue(response: Response, request: Request, settings: Settings, token: str) -> None:
    """Put a session token in the browser: HttpOnly, SameSite=Lax, for the session's lifetime."""
    issue_session_cookie(
        response,
        request,
        name=SESSION_COOKIE,
        token=token,
        max_age_seconds=int(SESSION_LIFETIME.total_seconds()),
        secure=settings.cookie_secure,
    )


def clear(response: Response, request: Request, settings: Settings) -> None:
    """Remove the session token from the browser."""
    clear_session_cookie(response, request, name=SESSION_COOKIE, secure=settings.cookie_secure)


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
