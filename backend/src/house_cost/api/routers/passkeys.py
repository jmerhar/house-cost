"""Adding passkeys to an account, and logging in with one."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from jigkit.auth.passkeys import (
    LABEL_LENGTH,
    Party,
    PasskeyRejected,
    authentication_options,
    clear_ceremony,
    hold_ceremony,
    new_user_handle,
    parse_login,
    request_party,
    verify_login,
    verify_registration,
)
from jigkit.auth.passkeys import registration_options as passkey_options
from pydantic import BaseModel, Field
from sqlalchemy import select

from ...audit import record
from ...auth import open_session
from ...models import Passkey, Person, utcnow
from .. import session_cookie
from ..deps import DbDep, ServicesDep, SessionDep
from ..schemas import Me, Out
from .account import client_address

router = APIRouter(prefix="/auth", tags=["passkeys"])

#: The name the site goes by on a person's device when they add a passkey.
RP_NAME = "House costs"
#: The cookie a ceremony's key travels in, sent only to the routes that finish one.
CEREMONY_COOKIE = "hc_webauthn"
CEREMONY_PATH = "/api/auth"


class PasskeyOut(Out):
    id: int
    label: str
    created_at: datetime
    last_used_at: datetime | None


class PasskeyIn(BaseModel):
    """A passkey to add: the authenticator's answer, as the browser serialises it."""

    label: str = Field(min_length=1, max_length=LABEL_LENGTH)
    credential: dict[str, Any]


class PasskeyLogin(BaseModel):
    credential: dict[str, Any]


def _party(request: Request, services) -> Party:
    return request_party(request, services.settings.public_url)


def _hold(response: Response, request: Request, services, key: str) -> None:
    hold_ceremony(
        response,
        request,
        key,
        name=CEREMONY_COOKIE,
        path=CEREMONY_PATH,
        secure=services.settings.cookie_secure,
    )


@router.get("/passkeys")
async def list_passkeys(session: SessionDep, db: DbDep) -> list[PasskeyOut]:
    """The passkeys on this person's account."""
    rows = await db.execute(
        select(Passkey).where(Passkey.person_id == session.person_id).order_by(Passkey.created_at)
    )
    return [PasskeyOut.model_validate(row) for row in rows.scalars()]


@router.post("/passkeys/options")
async def registration_options(
    request: Request, response: Response, session: SessionDep, db: DbDep, services: ServicesDep
) -> dict[str, Any]:
    """Start adding a passkey: the options a browser hands its authenticator.

    The passkey is discoverable, so it can log in without a login typed first, and the
    authenticator is told which of this person's passkeys it already holds.
    """
    person = session.person
    if person.webauthn_handle is None:
        person.webauthn_handle = new_user_handle()
    owned = (
        await db.execute(select(Passkey.credential_id).where(Passkey.person_id == person.id))
    ).scalars()
    options = passkey_options(
        _party(request, services),
        rp_name=RP_NAME,
        user_handle=person.webauthn_handle,
        user_name=person.login,
        display_name=person.name,
        exclude=owned,
    )
    _hold(response, request, services, services.ceremonies.start(options.challenge, person.id))
    return options.public_key


@router.post("/passkeys", status_code=status.HTTP_201_CREATED)
async def add_passkey(
    body: PasskeyIn, request: Request, session: SessionDep, db: DbDep, services: ServicesDep
) -> PasskeyOut:
    """Finish adding a passkey, from the authenticator's answer to the challenge."""
    ceremony = services.ceremonies.finish(request.cookies.get(CEREMONY_COOKIE))
    if ceremony is None or ceremony.owner_id != session.person_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "passkey_expired")
    try:
        verified = verify_registration(
            _party(request, services), body.credential, ceremony.challenge
        )
    except PasskeyRejected:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "passkey_rejected") from None
    existing = await db.execute(
        select(Passkey.id).where(Passkey.credential_id == verified.credential_id)
    )
    if existing.first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "passkey_exists")
    passkey = Passkey(
        person_id=session.person_id,
        credential_id=verified.credential_id,
        public_key=verified.public_key,
        sign_count=verified.sign_count,
        transports=verified.transports,
        label=body.label,
    )
    db.add(passkey)
    await db.flush()
    out = PasskeyOut.model_validate(passkey)
    record(db, session.person, "create", "passkey", passkey.id, after=out)
    return out


@router.delete("/passkeys/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_passkey(passkey_id: int, session: SessionDep, db: DbDep) -> None:
    """Remove one of this person's passkeys; it can no longer log in."""
    passkey = await db.get(Passkey, passkey_id)
    if passkey is None or passkey.person_id != session.person_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    record(
        db,
        session.person,
        "delete",
        "passkey",
        passkey.id,
        before=PasskeyOut.model_validate(passkey),
    )
    await db.delete(passkey)


@router.post("/passkey-login/options")
async def login_options(
    request: Request, response: Response, services: ServicesDep
) -> dict[str, Any]:
    """Start logging in with a passkey. Names nobody: the authenticator offers whichever of its
    passkeys belong to this site."""
    options = authentication_options(_party(request, services))
    _hold(response, request, services, services.ceremonies.start(options.challenge, None))
    return options.public_key


@router.post("/passkey-login")
async def log_in_with_passkey(
    body: PasskeyLogin, request: Request, response: Response, db: DbDep, services: ServicesDep
) -> Me:
    """Finish logging in with a passkey, and start a session as its owner.

    Every refusal counts against the address's failed logins, as a wrong password does.
    """
    address = client_address(request)
    if services.throttle.blocked(address):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too_many_attempts")
    ceremony = services.ceremonies.finish(request.cookies.get(CEREMONY_COOKIE))
    if ceremony is None or ceremony.owner_id is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "passkey_expired")
    try:
        answer = parse_login(body.credential)
    except PasskeyRejected:
        services.throttle.failed(address)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "passkey_rejected") from None
    passkey = (
        await db.execute(select(Passkey).where(Passkey.credential_id == answer.credential_id))
    ).scalar_one_or_none()
    person: Person | None = passkey.person if passkey else None
    handle = answer.user_handle
    if passkey is None or not person.active or (handle and handle != person.webauthn_handle):
        services.throttle.failed(address)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "passkey_unknown")
    try:
        new_sign_count = verify_login(
            _party(request, services),
            answer,
            ceremony.challenge,
            public_key=passkey.public_key,
            sign_count=passkey.sign_count,
        )
    except PasskeyRejected:
        services.throttle.failed(address)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "passkey_rejected") from None
    services.throttle.succeeded(address)
    passkey.sign_count = new_sign_count
    passkey.last_used_at = utcnow()
    token = await open_session(db, person, request.headers.get("user-agent", ""))
    session_cookie.issue(response, request, services.settings, token)
    clear_ceremony(response, name=CEREMONY_COOKIE, path=CEREMONY_PATH)
    return await session_cookie.describe(
        db,
        person,
        services.claude is not None,
        services.notifier.channels,
        services.settings.phone_country_code,
    )
