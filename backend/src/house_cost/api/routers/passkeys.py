"""Adding passkeys to an account, and logging in with one."""

import json
import secrets
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import parse_authentication_credential_json
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from ...audit import record
from ...auth import open_session
from ...models import Passkey, Person, utcnow
from ...passkeys import CEREMONY_COOKIE, CEREMONY_SECONDS, REJECTED, Party, party
from .. import session_cookie
from ..deps import DbDep, ServicesDep, SessionDep
from ..schemas import Me, Out
from .account import client_address

router = APIRouter(prefix="/auth", tags=["passkeys"])

#: The name the site goes by on a person's device when they add a passkey.
RP_NAME = "House costs"


class PasskeyOut(Out):
    id: int
    label: str
    created_at: datetime
    last_used_at: datetime | None


class PasskeyIn(BaseModel):
    """A passkey to add: the authenticator's answer, as the browser serialises it."""

    label: str = Field(min_length=1, max_length=100)
    credential: dict[str, Any]


class PasskeyLogin(BaseModel):
    credential: dict[str, Any]


def _party(request: Request, services) -> Party:
    return party(services.settings.public_url, request.url.scheme, request.headers.get("host", ""))


def _hold(response: Response, request: Request, services, key: str) -> None:
    response.set_cookie(
        CEREMONY_COOKIE,
        key,
        max_age=CEREMONY_SECONDS,
        httponly=True,
        samesite="strict",
        secure=session_cookie.is_secure(request, services.settings),
        path="/api/auth",
    )


def _options(options) -> dict[str, Any]:
    return json.loads(options_to_json(options))


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
        person.webauthn_handle = secrets.token_bytes(32)
    owned = (
        await db.execute(select(Passkey.credential_id).where(Passkey.person_id == person.id))
    ).scalars()
    rp = _party(request, services)
    options = generate_registration_options(
        rp_id=rp.rp_id,
        rp_name=RP_NAME,
        user_id=person.webauthn_handle,
        user_name=person.login,
        user_display_name=person.name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=c) for c in owned],
    )
    _hold(response, request, services, services.ceremonies.start(options.challenge, person.id))
    return _options(options)


@router.post("/passkeys", status_code=status.HTTP_201_CREATED)
async def add_passkey(
    body: PasskeyIn, request: Request, session: SessionDep, db: DbDep, services: ServicesDep
) -> PasskeyOut:
    """Finish adding a passkey, from the authenticator's answer to the challenge."""
    ceremony = services.ceremonies.finish(request.cookies.get(CEREMONY_COOKIE))
    if ceremony is None or ceremony.person_id != session.person_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "passkey_expired")
    rp = _party(request, services)
    try:
        verified = verify_registration_response(
            credential=body.credential,
            expected_challenge=ceremony.challenge,
            expected_rp_id=rp.rp_id,
            expected_origin=rp.origin,
        )
    except REJECTED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "passkey_rejected") from None
    existing = await db.execute(
        select(Passkey.id).where(Passkey.credential_id == verified.credential_id)
    )
    if existing.first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "passkey_exists")
    transports = body.credential.get("response", {}).get("transports") or []
    passkey = Passkey(
        person_id=session.person_id,
        credential_id=verified.credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        transports=[t for t in transports if isinstance(t, str)],
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
    options = generate_authentication_options(
        rp_id=_party(request, services).rp_id,
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    _hold(response, request, services, services.ceremonies.start(options.challenge, None))
    return _options(options)


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
    if ceremony is None or ceremony.person_id is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "passkey_expired")
    try:
        credential = parse_authentication_credential_json(body.credential)
    except REJECTED:
        services.throttle.failed(address)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "passkey_rejected") from None
    passkey = (
        await db.execute(select(Passkey).where(Passkey.credential_id == credential.raw_id))
    ).scalar_one_or_none()
    person: Person | None = passkey.person if passkey else None
    handle = credential.response.user_handle
    if passkey is None or not person.active or (handle and handle != person.webauthn_handle):
        services.throttle.failed(address)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "passkey_unknown")
    rp = _party(request, services)
    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=ceremony.challenge,
            expected_rp_id=rp.rp_id,
            expected_origin=rp.origin,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
        )
    except REJECTED:
        services.throttle.failed(address)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "passkey_rejected") from None
    services.throttle.succeeded(address)
    passkey.sign_count = verified.new_sign_count
    passkey.last_used_at = utcnow()
    token = await open_session(db, person, request.headers.get("user-agent", ""))
    session_cookie.issue(response, request, services.settings, token)
    response.delete_cookie(CEREMONY_COOKIE, path="/api/auth")
    return await session_cookie.describe(
        db,
        person,
        services.claude is not None,
        services.notifier.channels,
        services.settings.phone_country_code,
    )
