"""Passkeys: the WebAuthn ceremonies that add one and log in with one.

A ceremony is two requests: the server hands out options carrying a fresh challenge, and the
browser comes back with the authenticator's answer to it. Between the two, the challenge waits
here, in memory, under a random key the browser holds in a short-lived cookie.
"""

import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from webauthn.helpers.exceptions import WebAuthnException

#: How long a ceremony may take between its two requests.
CEREMONY_SECONDS = 300
#: The cookie a ceremony's key travels in.
CEREMONY_COOKIE = "hc_webauthn"

#: What parsing and verifying raise for an answer that does not hold up: the library's own
#: failures, and a malformed base64 or number, which surface as ValueError.
REJECTED = (WebAuthnException, ValueError)


@dataclass(frozen=True)
class Party:
    """Who the passkeys belong to: the site's host name, and the origin answers must come from."""

    rp_id: str
    origin: str


def party(public_url: str | None, scheme: str, host: str) -> Party:
    """The relying party for a request: the configured public URL's, else the request's own.

    A passkey is bound to the host name it was made for, so a deployment behind a proxy needs its
    public URL set for passkeys made there to keep working.
    """
    if public_url:
        parts = urlsplit(public_url)
        return Party(rp_id=parts.hostname or "", origin=f"{parts.scheme}://{parts.netloc}")
    return Party(rp_id=host.split(":")[0], origin=f"{scheme}://{host}")


@dataclass(frozen=True)
class Ceremony:
    """A challenge handed out, and whose ceremony it is (None for a login, which names nobody)."""

    challenge: bytes
    person_id: int | None
    expires: float


class Ceremonies:
    """Challenges waiting for their answer. Each is used once; an expired one is forgotten."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._waiting: dict[str, Ceremony] = {}

    def start(self, challenge: bytes, person_id: int | None) -> str:
        """Keep a challenge for its answer, and return the key the browser holds."""
        self._forget_expired()
        key = secrets.token_urlsafe(24)
        self._waiting[key] = Ceremony(challenge, person_id, self._clock() + CEREMONY_SECONDS)
        return key

    def finish(self, key: str | None) -> Ceremony | None:
        """The ceremony a key belongs to, if it is still waiting; it can be finished only once."""
        self._forget_expired()
        return self._waiting.pop(key, None) if key else None

    def _forget_expired(self) -> None:
        now = self._clock()
        for key in [k for k, ceremony in self._waiting.items() if ceremony.expires <= now]:
            del self._waiting[key]
