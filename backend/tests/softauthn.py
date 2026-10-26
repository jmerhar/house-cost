"""A software authenticator, answering WebAuthn ceremonies as a phone or a security key would.

It makes real ES256 key pairs and real CBOR, so the server's verification runs exactly as it
does for a device; only the person's touch is skipped.
"""

import base64
import hashlib
import json
import secrets
import struct
from dataclasses import dataclass, field

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

FLAG_USER_PRESENT = 0x01
FLAG_USER_VERIFIED = 0x04
FLAG_ATTESTED = 0x40


def b64(data: bytes) -> str:
    """Base64url without padding, as WebAuthn's JSON carries bytes."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass
class Credential:
    """One passkey the authenticator holds."""

    id: bytes
    key: ec.EllipticCurvePrivateKey
    rp_id: str
    user_handle: bytes
    sign_count: int = 0


@dataclass
class SoftAuthenticator:
    """Holds passkeys and answers the server's options with them."""

    origin: str
    credentials: list[Credential] = field(default_factory=list)

    def _client_data(self, kind: str, challenge: str, origin: str | None) -> bytes:
        return json.dumps(
            {
                "type": kind,
                "challenge": challenge,
                "origin": origin or self.origin,
                "crossOrigin": False,
            }
        ).encode()

    def register(
        self, options: dict, *, origin: str | None = None, credential: Credential | None = None
    ) -> dict:
        """Make a passkey for the options' site and user, and the browser's JSON for it; with
        ``credential``, offer that existing passkey again instead."""
        rp_id = options["rp"]["id"]
        if credential is None:
            key = ec.generate_private_key(ec.SECP256R1())
            credential = Credential(
                secrets.token_bytes(32), key, rp_id, unb64(options["user"]["id"])
            )
            self.credentials.append(credential)
        numbers = credential.key.public_key().public_numbers()
        cose_key = cbor2.dumps(
            {
                1: 2,
                3: -7,
                -1: 1,
                -2: numbers.x.to_bytes(32, "big"),
                -3: numbers.y.to_bytes(32, "big"),
            }
        )
        auth_data = (
            hashlib.sha256(rp_id.encode()).digest()
            + bytes([FLAG_USER_PRESENT | FLAG_USER_VERIFIED | FLAG_ATTESTED])
            + struct.pack(">I", 0)
            + bytes(16)
            + struct.pack(">H", len(credential.id))
            + credential.id
            + cose_key
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        return {
            "id": b64(credential.id),
            "rawId": b64(credential.id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(
                    self._client_data("webauthn.create", options["challenge"], origin)
                ),
                "attestationObject": b64(attestation),
                "transports": ["internal", "hybrid"],
            },
            "clientExtensionResults": {},
        }

    def authenticate(
        self, options: dict, *, credential: Credential | None = None, origin: str | None = None
    ) -> dict:
        """Sign the options' challenge with a passkey for its site, and the browser's JSON."""
        credential = credential or next(c for c in self.credentials if c.rp_id == options["rpId"])
        credential.sign_count += 1
        auth_data = (
            hashlib.sha256(credential.rp_id.encode()).digest()
            + bytes([FLAG_USER_PRESENT | FLAG_USER_VERIFIED])
            + struct.pack(">I", credential.sign_count)
        )
        client_data = self._client_data("webauthn.get", options["challenge"], origin)
        signature = credential.key.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "id": b64(credential.id),
            "rawId": b64(credential.id),
            "type": "public-key",
            "response": {
                "clientDataJSON": b64(client_data),
                "authenticatorData": b64(auth_data),
                "signature": b64(signature),
                "userHandle": b64(credential.user_handle),
            },
            "clientExtensionResults": {},
        }
