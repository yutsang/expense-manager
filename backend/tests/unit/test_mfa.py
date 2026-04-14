"""Unit tests for MFA — TOTP enrollment, verification, recovery codes (T0.9 DoD)."""
from __future__ import annotations

import time

import pyotp
import pytest

from app.core.mfa import (
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_recovery_codes,
    generate_totp_secret,
    get_totp_provisioning_uri,
    verify_recovery_code,
    verify_totp,
)

_TEST_KEY = b"testkey_32bytes_long_enough_here"  # 32 bytes


class TestTOTP:
    def test_generate_secret_is_valid_base32(self) -> None:
        secret = generate_totp_secret()
        # pyotp.TOTP should accept it without raising
        totp = pyotp.TOTP(secret)
        assert totp.now()  # generates a 6-digit code

    def test_provisioning_uri_contains_issuer(self) -> None:
        secret = generate_totp_secret()
        uri = get_totp_provisioning_uri(secret, "user@example.com")
        assert "Aegis%20ERP" in uri or "Aegis+ERP" in uri or "Aegis ERP" in uri
        assert "user%40example.com" in uri or "user@example.com" in uri
        assert uri.startswith("otpauth://")

    def test_valid_code_verifies(self) -> None:
        secret = generate_totp_secret()
        code = pyotp.TOTP(secret).now()
        assert verify_totp(secret, code)

    def test_wrong_code_rejected(self) -> None:
        secret = generate_totp_secret()
        assert not verify_totp(secret, "000000")

    def test_code_with_spaces_stripped(self) -> None:
        secret = generate_totp_secret()
        code = pyotp.TOTP(secret).now()
        assert verify_totp(secret, f" {code} ")


class TestTOTPEncryption:
    def test_encrypt_decrypt_roundtrip(self) -> None:
        secret = generate_totp_secret()
        encrypted = encrypt_totp_secret(secret, _TEST_KEY)
        assert encrypted != secret
        assert decrypt_totp_secret(encrypted, _TEST_KEY) == secret

    def test_different_nonces_each_call(self) -> None:
        secret = generate_totp_secret()
        e1 = encrypt_totp_secret(secret, _TEST_KEY)
        e2 = encrypt_totp_secret(secret, _TEST_KEY)
        assert e1 != e2  # different nonces

    def test_wrong_key_raises(self) -> None:
        secret = generate_totp_secret()
        encrypted = encrypt_totp_secret(secret, _TEST_KEY)
        wrong_key = b"wrongkey_32bytes_long_enough_xxx"
        from cryptography.exceptions import InvalidTag
        with pytest.raises(InvalidTag):
            decrypt_totp_secret(encrypted, wrong_key)


class TestRecoveryCodes:
    def test_generates_correct_count(self) -> None:
        raw, hashed = generate_recovery_codes()
        assert len(raw) == 8
        assert len(hashed) == 8

    def test_raw_and_hashed_differ(self) -> None:
        raw, hashed = generate_recovery_codes()
        for r, h in zip(raw, hashed):
            assert r != h
            assert len(h) == 64  # sha256 hex

    def test_valid_code_matches(self) -> None:
        raw, hashed = generate_recovery_codes()
        matched, matched_hash = verify_recovery_code(raw[0], hashed)
        assert matched is True
        assert matched_hash == hashed[0]

    def test_invalid_code_no_match(self) -> None:
        _, hashed = generate_recovery_codes()
        matched, matched_hash = verify_recovery_code("XXXX-XXXX", hashed)
        assert matched is False
        assert matched_hash is None

    def test_case_insensitive_match(self) -> None:
        raw, hashed = generate_recovery_codes()
        lowercased = raw[0].lower()
        matched, _ = verify_recovery_code(lowercased, hashed)
        assert matched is True

    def test_codes_are_unique(self) -> None:
        raw, _ = generate_recovery_codes()
        assert len(set(raw)) == 8

    def test_code_format_xxxx_xxxx(self) -> None:
        raw, _ = generate_recovery_codes()
        for code in raw:
            parts = code.split("-")
            assert len(parts) == 2
            assert all(len(p) == 4 for p in parts)
