"""Passwords, sessions, the login throttle, and the check that a write came from the interface."""

import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Person, Session, utcnow

#: The shortest password accepted.
MIN_PASSWORD_LENGTH = 10
#: How long a login lasts without being used; each use extends it.
SESSION_LIFETIME = timedelta(days=90)
#: How stale a session's expiry may grow before a request writes a new one, so an active browser
#: does not cost a write on every request.
SESSION_REFRESH = timedelta(days=1)
#: The header every write must carry. A browser will not send a custom header across origins
#: without a CORS preflight, which this app never grants, so a page elsewhere cannot forge it.
WRITE_HEADER = "X-Requested-With"
WRITE_HEADER_VALUE = "house-cost"

_hasher = PasswordHasher()


class PasswordTooShort(ValueError):
    """A new password is shorter than ``MIN_PASSWORD_LENGTH``."""


def hash_password(password: str) -> str:
    """An Argon2id hash of ``password``."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordTooShort(f"a password needs at least {MIN_PASSWORD_LENGTH} characters")
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Whether ``password`` matches the hash; any malformed hash simply does not match."""
    try:
        return _hasher.verify(password_hash, password)
    except Argon2Error, InvalidHashError:
        return False


#: Verified against when a login names nobody, so an unknown login takes as long to refuse as a
#: wrong password and timing does not reveal which logins exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    """Spend the time a real password check takes, for a login that names nobody."""
    verify_password(_DUMMY_HASH, password)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def open_session(db: AsyncSession, person: Person, user_agent: str) -> str:
    """Start a session for ``person`` and return its token, which only the browser keeps."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(
        Session(
            token_hash=_digest(token),
            person_id=person.id,
            created_at=now,
            last_seen_at=now,
            expires_at=now + SESSION_LIFETIME,
            user_agent=user_agent[:300],
        )
    )
    await db.flush()
    return token


async def find_session(db: AsyncSession, token: str, now: datetime | None = None) -> Session | None:
    """The live session a token belongs to, extended when it has gone stale, or None.

    A session whose person has been deactivated counts as ended.
    """
    now = now or utcnow()
    session = (
        await db.execute(select(Session).where(Session.token_hash == _digest(token)))
    ).scalar_one_or_none()
    if session is None or session.expires_at <= now or not session.person.active:
        return None
    if now - session.last_seen_at >= SESSION_REFRESH:
        session.last_seen_at = now
        session.expires_at = now + SESSION_LIFETIME
    return session


async def end_sessions(db: AsyncSession, person_id: int, *, keep: int | None = None) -> None:
    """End every session of a person, except ``keep`` when given."""
    statement = delete(Session).where(Session.person_id == person_id)
    if keep is not None:
        statement = statement.where(Session.id != keep)
    await db.execute(statement)


class LoginThrottle:
    """Failed logins per client address in a sliding minute; past the limit, logins are refused.

    In memory, so a restart forgets it, which costs an attacker nothing they could not get by
    waiting a minute anyway.
    """

    def __init__(self, per_minute: int, clock=time.monotonic) -> None:
        self.per_minute = per_minute
        self._clock = clock
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, address: str) -> deque[float]:
        window = self._failures[address]
        cutoff = self._clock() - 60
        while window and window[0] <= cutoff:
            window.popleft()
        return window

    def blocked(self, address: str) -> bool:
        """Whether ``address`` has used up its failed attempts for now."""
        return len(self._recent(address)) >= self.per_minute

    def failed(self, address: str) -> None:
        """Count a failed login from ``address``."""
        self._recent(address).append(self._clock())

    def succeeded(self, address: str) -> None:
        """Forget ``address``'s failures after it logs in."""
        self._failures.pop(address, None)


def origin_allowed(origin: str | None, host: str | None, public_url: str | None) -> bool:
    """Whether a write's Origin header is this app's own.

    No Origin at all is allowed: browsers send one on every cross-origin write, so its absence
    means a same-origin request or a client that is not a browser, and the custom write header
    still has to be there. Otherwise the origin must be the configured public URL's, or name the
    host the request was sent to.
    """
    if origin is None:
        return True
    if origin == "null":
        return False
    allowed = set()
    if public_url:
        parts = urlsplit(public_url)
        allowed.add(f"{parts.scheme}://{parts.netloc}".lower())
    if host:
        allowed.update({f"http://{host}".lower(), f"https://{host}".lower()})
    return origin.lower() in allowed
