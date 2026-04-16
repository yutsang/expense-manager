"""Unit tests for security primitives (T0.8 DoD)."""

from __future__ import annotations

import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    hash_token,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self) -> None:
        hashed = hash_password("correct-horse-battery-staple")
        assert verify_password("correct-horse-battery-staple", hashed)

    def test_wrong_password_rejected(self) -> None:
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_different_hashes_per_call(self) -> None:
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # different salts


class TestJWT:
    def test_access_token_roundtrip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECRET_KEY", "s" * 32)
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://a:b@localhost/c")

        token = create_access_token("user-123", "tenant-456")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-123"
        assert payload["tid"] == "tenant-456"
        assert payload["type"] == "access"

    def test_tampered_token_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SECRET_KEY", "s" * 32)
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://a:b@localhost/c")
        token = create_access_token("user-123")
        with pytest.raises(JWTError):
            decode_access_token(token + "tampered")

    def test_refresh_token_is_hashed(self) -> None:
        raw, hashed = create_refresh_token("user-123")
        assert raw != hashed
        assert len(raw) > 32
        assert len(hashed) == 64  # sha256 hex digest


class TestTokenHashing:
    def test_hash_deterministic(self) -> None:
        assert hash_token("abc") == hash_token("abc")

    def test_different_tokens_different_hashes(self) -> None:
        assert hash_token("abc") != hash_token("xyz")
