"""Passwords, sessions and the login throttle, on jigkit.auth.

jigkit hashes passwords (Argon2id, at least ten characters), keeps sessions as hashed tokens with
a sliding expiry, and throttles failed logins per address. What is house-cost's own: sessions
belong to people, and a deactivated person's sessions count as ended.
"""

from datetime import datetime, timedelta

from jigkit.auth import (
    LoginThrottle,
    PasswordTooShort,
    burn_password_check,
    hash_password,
    verify_password,
)
from jigkit.auth.sessions import SessionStore
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Person, Session

__all__ = [
    "MIN_PASSWORD_LENGTH",
    "SESSION_LIFETIME",
    "WRITE_HEADER_VALUE",
    "LoginThrottle",
    "PasswordTooShort",
    "burn_password_check",
    "end_sessions",
    "find_session",
    "hash_password",
    "open_session",
    "verify_password",
]

#: The shortest password accepted.
MIN_PASSWORD_LENGTH = 10
#: How long a login lasts without being used; each use extends it.
SESSION_LIFETIME = timedelta(days=90)
#: How stale a session's expiry may grow before a request writes a new one, so an active browser
#: does not cost a write on every request.
SESSION_REFRESH = timedelta(days=1)
#: The value of the X-Requested-With header every write must carry (jigkit's write guard). A
#: browser will not send a custom header across origins without a CORS preflight, which this app
#: never grants, so a page elsewhere cannot forge it.
WRITE_HEADER_VALUE = "house-cost"

#: Opens, finds and ends people's sessions.
SESSIONS = SessionStore(
    Session, owner="person_id", lifetime=SESSION_LIFETIME, refresh=SESSION_REFRESH
)


async def open_session(db: AsyncSession, person: Person, user_agent: str) -> str:
    """Start a session for ``person`` and return its token, which only the browser keeps."""
    return await SESSIONS.open(db, person.id, user_agent)


async def find_session(db: AsyncSession, token: str, now: datetime | None = None) -> Session | None:
    """The live session a token belongs to, extended when it has gone stale, or None.

    A session whose person has been deactivated counts as ended.
    """
    session = await SESSIONS.find(db, token, now)
    if session is None or not session.person.active:
        return None
    return session


async def end_sessions(db: AsyncSession, person_id: int, *, keep: int | None = None) -> None:
    """End every session of a person, except ``keep`` when given."""
    await SESSIONS.end_all(db, person_id, keep=keep)
