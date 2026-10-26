"""Logging in and out, and a person's own account and sessions."""

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from ...audit import record
from ...auth import (
    burn_password_check,
    end_sessions,
    find_session,
    hash_password,
    open_session,
    verify_password,
)
from ...models import Person, Session
from ...notify.messages import language, render
from .. import session_cookie
from ..deps import SESSION_COOKIE, DbDep, PersonDep, ServicesDep, SessionDep
from ..schemas import LoginIn, Me, MeUpdate, PersonOut, SessionOut, TestSent

router = APIRouter(prefix="/auth", tags=["account"])


def client_address(request: Request) -> str:
    """The address a request came from, as the login throttle counts it (after the proxy's
    X-Forwarded-For, when the proxy is trusted)."""
    return request.client.host if request.client else "unknown"


@router.post("/login")
async def log_in(
    body: LoginIn, request: Request, response: Response, db: DbDep, services: ServicesDep
) -> Me:
    """Log in with a login and password.

    A wrong password and an unknown login are refused alike, and take as long, so the answer
    does not reveal which logins exist. Too many failures from one address are refused with 429
    for a minute.
    """
    address = client_address(request)
    if services.throttle.blocked(address):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too_many_attempts")
    person = (
        await db.execute(select(Person).where(Person.login == body.login, Person.active))
    ).scalar_one_or_none()
    if person is None:
        burn_password_check(body.password)
    if person is None or not verify_password(person.password_hash, body.password):
        services.throttle.failed(address)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_login")
    services.throttle.succeeded(address)
    token = await open_session(db, person, request.headers.get("user-agent", ""))
    session_cookie.issue(response, request, services.settings, token)
    return await session_cookie.describe(db, person)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def log_out(request: Request, db: DbDep, services: ServicesDep) -> Response:
    """End this browser's session, if it has one."""
    token = request.cookies.get(SESSION_COOKIE)
    session = await find_session(db, token) if token else None
    if session is not None:
        await db.delete(session)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    session_cookie.clear(response, request, services.settings)
    return response


@router.get("/me")
async def me(person: PersonDep, db: DbDep) -> Me:
    """The person logged in."""
    return await session_cookie.describe(db, person)


@router.patch("/me")
async def update_me(body: MeUpdate, session: SessionDep, db: DbDep) -> Me:
    """Change one's own name, language or password.

    A new password needs the current one, and ends every other session of this person.
    """
    person = session.person
    before = PersonOut.model_validate(person)
    person.name = body.name
    person.language = body.language
    if body.apprise_urls is not None:
        person.apprise_urls = body.apprise_urls.strip()
    if body.notify_on is not None:
        person.notify_on = dict(body.notify_on)
    if body.new_password is not None:
        if body.current_password is None or not verify_password(
            person.password_hash, body.current_password
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "wrong_password")
        person.password_hash = hash_password(body.new_password)
        await end_sessions(db, person.id, keep=session.id)
    record(
        db,
        person,
        "update",
        "person",
        person.id,
        before=before,
        after=PersonOut.model_validate(person),
    )
    return await session_cookie.describe(db, person)


@router.post("/me/test-notification")
async def test_notification(person: PersonDep, services: ServicesDep) -> TestSent:
    """Send a test notification to this person's own URLs."""
    if not person.urls:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "no_urls")
    title, body = render("test", language(person.language))
    return TestSent(sent=await services.sender.send(person.urls, title, body))


@router.get("/sessions")
async def sessions(session: SessionDep, db: DbDep) -> list[SessionOut]:
    """Every browser this person is logged in on, most recently used first."""
    rows = (
        await db.execute(
            select(Session)
            .where(Session.person_id == session.person_id)
            .order_by(Session.last_seen_at.desc())
        )
    ).scalars()
    return [
        SessionOut.model_validate(row).model_copy(update={"current": row.id == session.id})
        for row in rows
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def end_session(session_id: int, session: SessionDep, db: DbDep) -> None:
    """Log one of this person's other browsers out."""
    target = await db.get(Session, session_id)
    if target is None or target.person_id != session.person_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    await db.delete(target)
