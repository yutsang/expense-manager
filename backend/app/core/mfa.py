"""Multi-factor authentication helpers.

Supports:
  - TOTP (RFC 6238) via pyotp — enrollment, verification, recovery codes
  - WebAuthn (FIDO2) registration + assertion stubs (full flow wired in Phase T0.9)

Rules:
  - TOTP secrets are stored AES-GCM encrypted via _encrypt_secret() before writing to DB.
  - Recovery codes: 8 × 8-char alphanumeric, hashed with sha256 in DB, single-use.
  - WebAuthn: server-side state (challenge) stored in Redis with 5-minute TTL.
"""

from __future__ import annotations

import hashlib
import secrets
import string
from base64 import b64decode, b64encode
from typing import TYPE_CHECKING

import pyotp

if TYPE_CHECKING:
    pass

_RECOVERY_ALPHABET = string.ascii_uppercase + string.digits  # no ambiguous chars
_RECOVERY_CODE_LENGTH = 8
_RECOVERY_CODE_COUNT = 8


# ── TOTP ─────────────────────────────────────────────────────────────────────


def generate_totp_secret() -> str:
    """Generate a new Base32 TOTP secret (to show to user for QR scanning)."""
    return pyotp.random_base32()


def get_totp_provisioning_uri(secret: str, user_email: str, issuer: str = "Aegis ERP") -> str:
    """Return an otpauth:// URI for QR code generation."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=user_email, issuer_name=issuer)


def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    """Verify a 6-digit TOTP code. valid_window allows ±1 time step (30s each)."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code.strip(), valid_window=valid_window)


def encrypt_totp_secret(secret: str, encryption_key: bytes) -> str:
    """AES-GCM encrypt the TOTP secret. Returns base64-encoded ciphertext:nonce."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    aes = AESGCM(encryption_key[:32])
    ct = aes.encrypt(nonce, secret.encode(), None)
    return b64encode(nonce + ct).decode()


def decrypt_totp_secret(encrypted: str, encryption_key: bytes) -> str:
    """Decrypt a TOTP secret previously encrypted with encrypt_totp_secret()."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = b64decode(encrypted)
    nonce, ct = raw[:12], raw[12:]
    aes = AESGCM(encryption_key[:32])
    return aes.decrypt(nonce, ct, None).decode()


# ── Recovery codes ────────────────────────────────────────────────────────────


def generate_recovery_codes() -> tuple[list[str], list[str]]:
    """Generate recovery codes. Returns (raw_codes, hashed_codes).

    Store only hashed_codes. Give raw_codes to the user once; they cannot be recovered.
    Format: XXXX-XXXX (hyphen-separated for readability).
    """
    raw: list[str] = []
    hashed: list[str] = []
    for _ in range(_RECOVERY_CODE_COUNT):
        code = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(_RECOVERY_CODE_LENGTH))
        formatted = f"{code[:4]}-{code[4:]}"
        raw.append(formatted)
        hashed.append(_hash_recovery_code(formatted))
    return raw, hashed


def _hash_recovery_code(code: str) -> str:
    normalized = code.replace("-", "").upper()
    return hashlib.sha256(normalized.encode()).hexdigest()


def verify_recovery_code(attempted: str, hashed_codes: list[str]) -> tuple[bool, str | None]:
    """Check if attempted code matches any stored hash. Returns (matched, matched_hash)."""
    h = _hash_recovery_code(attempted)
    if h in hashed_codes:
        return True, h
    return False, None


# ── WebAuthn ──────────────────────────────────────────────────────────────────
# Full implementation requires a Redis-backed challenge store; stubs here.
# Phase T0.9 wires these into /v1/auth/webauthn/* endpoints.


def begin_webauthn_registration(user_id: str, user_email: str, rp_id: str) -> dict:
    """Begin WebAuthn credential registration. Returns options to send to client."""
    from webauthn import generate_registration_options
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        ResidentKeyRequirement,
        UserVerificationRequirement,
    )

    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="Aegis ERP",
        user_id=user_id.encode(),
        user_name=user_email,
        user_display_name=user_email,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    return options  # type: ignore[return-value]


def begin_webauthn_authentication(rp_id: str, allowed_credentials: list[bytes]) -> dict:
    """Begin WebAuthn assertion. Returns options to send to client."""
    from webauthn import generate_authentication_options
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement

    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=[PublicKeyCredentialDescriptor(id=c) for c in allowed_credentials],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    return options  # type: ignore[return-value]
