"""Tests that signup auto-runs onboarding so new tenants land on a populated dashboard."""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


def _read_auth_service_source() -> str:
    path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "auth.py"
    return path.read_text()


class TestSignupWiresOnboarding:
    """Source-level assertions: signup calls setup_tenant in-transaction."""

    def test_signup_imports_setup_tenant(self) -> None:
        assert "from app.services.onboarding import setup_tenant" in _read_auth_service_source()

    def test_signup_imports_set_rls_tenant(self) -> None:
        assert "from app.core.tenant import set_rls_tenant" in _read_auth_service_source()

    def test_signup_calls_setup_tenant(self) -> None:
        source = _read_auth_service_source()
        # Must invoke setup_tenant from inside signup, after tenant is created.
        signup_def_idx = source.index("async def signup(")
        login_def_idx = source.index("async def login(")
        signup_body = source[signup_def_idx:login_def_idx]
        assert "await setup_tenant(" in signup_body
        assert "await set_rls_tenant(" in signup_body


@_skip_311
class TestSignupServiceCallsSetupTenant:
    """Mocked end-to-end: signup() invokes setup_tenant() with derived defaults."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock(return_value=None)  # no existing user with this email
        db.add = MagicMock()
        return db

    @pytest.mark.anyio
    async def test_signup_invokes_setup_tenant(self, mock_db: AsyncMock) -> None:
        from app.services import auth as auth_svc

        with (
            patch.object(auth_svc, "setup_tenant", new_callable=AsyncMock) as mock_setup,
            patch.object(auth_svc, "set_rls_tenant", new_callable=AsyncMock) as mock_rls,
            patch.object(auth_svc, "hash_password", return_value="hashed"),
            patch.object(auth_svc, "create_access_token", return_value="access"),
            patch.object(auth_svc, "create_refresh_token", return_value=("raw", "hash")),
        ):
            await auth_svc.signup(
                mock_db,
                email="jane@example.com",
                password="supersecret1",
                display_name="Jane",
                tenant_name="Acme Corp",
                country="AU",
                currency="AUD",
            )

        mock_setup.assert_awaited_once()
        mock_rls.assert_awaited_once()

        kwargs = mock_setup.await_args.kwargs
        assert kwargs["company_name"] == "Acme Corp"
        assert kwargs["legal_name"] == "Acme Corp"
        assert kwargs["country"] == "AU"
        assert kwargs["functional_currency"] == "AUD"
        assert kwargs["bank_currency"] == "AUD"
        assert kwargs["coa_template"] == "general"
        assert kwargs["fiscal_year_start_month"] == 1
        assert kwargs["bank_account_name"] == "Primary Operating Account"
