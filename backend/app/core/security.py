"""Authentication and cryptography utilities.

- Passwords: Argon2id (OWASP recommended).
- JWT: HMAC-SHA256 access (15m) + rotating refresh (30d).
- Tokens: URL-safe random bytes for invites / email verification.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

# Argon2id with OWASP-recommended parameters (2026 baseline)
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


def create_access_token(user_id: str, tenant_id: str | None = None) -> str:
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, object] = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "type": "access",
        "jti": str(uuid.uuid4()),
    }
    if tenant_id:
        payload["tid"] = tenant_id
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """Return (raw_token, hashed_token). Store only the hash; send raw to client."""
    raw = secrets.token_urlsafe(48)
    hashed = _hash_token(raw)
    return raw, hashed


def decode_access_token(token: str) -> dict[str, object]:
    """Decode and validate an access JWT. Raises JWTError on failure."""
    try:
        payload: dict[str, object] = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "access":
            raise JWTError("Not an access token")
        return payload
    except JWTError:
        raise


def generate_secure_token(nbytes: int = 32) -> str:
    """URL-safe token for email verification / invite links."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return _hash_token(token)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
