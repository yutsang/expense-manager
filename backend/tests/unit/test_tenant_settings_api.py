"""Unit tests for tenant settings synced to backend (Issue #72).

Tests cover:
  - TenantSettings schema for org settings fields
  - Settings service: get_settings, update_settings
  - Settings API router: GET /v1/settings, PATCH /v1/settings
  - Audit event emitted on settings update
  - Source-level verification of service and router existence
"""

from __future__ import annotations

import pathlib
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


class TestTenantSettingsSchema:
    """Pydantic schema for tenant settings PATCH."""

    def test_org_name_accepted(self) -> None:
        from app.api.v1.schemas import TenantSettingsUpdate

        s = TenantSettingsUpdate(org_name="My Corp")
        assert s.org_name == "My Corp"

    def test_country_accepted(self) -> None:
        from app.api.v1.schemas import TenantSettingsUpdate

        s = TenantSettingsUpdate(country="AU")
        assert s.country == "AU"

    def test_functional_currency_accepted(self) -> None:
        from app.api.v1.schemas import TenantSettingsUpdate

        s = TenantSettingsUpdate(functional_currency="AUD")
        assert s.functional_currency == "AUD"

    def test_fiscal_year_start_month_accepted(self) -> None:
        from app.api.v1.schemas import TenantSettingsUpdate

        s = TenantSettingsUpdate(fiscal_year_start_month=7)
        assert s.fiscal_year_start_month == 7

    def test_notification_prefs_accepted(self) -> None:
        from app.api.v1.schemas import TenantSettingsUpdate

        prefs = {
            "email_overdue_invoices": True,
            "daily_sanctions_scan": False,
            "period_close_reminders": True,
            "kyc_expiry_alerts": True,
        }
        s = TenantSettingsUpdate(notification_prefs=prefs)
        assert s.notification_prefs == prefs

    def test_all_fields_default_to_none(self) -> None:
        from app.api.v1.schemas import TenantSettingsUpdate

        s = TenantSettingsUpdate()
        assert s.org_name is None
        assert s.country is None
        assert s.functional_currency is None
        assert s.fiscal_year_start_month is None
        assert s.notification_prefs is None

    def test_fiscal_year_start_month_rejects_invalid(self) -> None:
        from app.api.v1.schemas import TenantSettingsUpdate

        with pytest.raises(Exception):
            TenantSettingsUpdate(fiscal_year_start_month=13)

    def test_fiscal_year_start_month_rejects_zero(self) -> None:
        from app.api.v1.schemas import TenantSettingsUpdate

        with pytest.raises(Exception):
            TenantSettingsUpdate(fiscal_year_start_month=0)


class TestTenantSettingsResponse:
    """Pydantic schema for GET response."""

    def test_settings_response_schema_exists(self) -> None:
        from app.api.v1.schemas import TenantSettingsResponse

        s = TenantSettingsResponse(
            org_name="Test",
            country="AU",
            functional_currency="AUD",
            fiscal_year_start_month=7,
            tax_rounding_policy="per_line",
            notification_prefs={},
        )
        assert s.org_name == "Test"
        assert s.tax_rounding_policy == "per_line"


class TestTenantModelSettings:
    """Tenant model has a settings JSONB column."""

    def test_tenant_model_has_settings_column(self) -> None:
        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        source = models_path.read_text()
        assert "settings" in source
        # Should be JSONB
        assert "JSONB" in source


class TestTenantSettingsServiceSource:
    """Verify service module exists and has expected functions."""

    def _read_source(self) -> str:
        svc_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "tenant_settings.py"
        )
        return svc_path.read_text()

    def test_get_settings_function_exists(self) -> None:
        source = self._read_source()
        assert "async def get_settings(" in source

    def test_update_settings_function_exists(self) -> None:
        source = self._read_source()
        assert "async def update_settings(" in source

    def test_update_emits_audit_event(self) -> None:
        source = self._read_source()
        assert "emit(" in source
        assert "tenant_settings.updated" in source


class TestTenantSettingsRouterSource:
    """Verify router module exists and has expected endpoints."""

    def _read_source(self) -> str:
        api_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "app"
            / "api"
            / "v1"
            / "tenant_settings.py"
        )
        return api_path.read_text()

    def test_get_endpoint_exists(self) -> None:
        source = self._read_source()
        assert "@router.get(" in source

    def test_patch_endpoint_exists(self) -> None:
        source = self._read_source()
        assert "@router.patch(" in source

    def test_router_registered_in_main(self) -> None:
        main_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "main.py"
        source = main_path.read_text()
        assert "tenant_settings" in source


@_skip_311
class TestTenantSettingsService:
    """Async tests for the tenant settings service."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        return db

    def _make_tenant(self, settings: dict | None = None) -> MagicMock:
        tenant = MagicMock()
        tenant.id = "t1"
        tenant.name = "Test Corp"
        tenant.country = "AU"
        tenant.functional_currency = "AUD"
        tenant.fiscal_year_start_month = 7
        tenant.settings = settings or {}
        tenant.version = 1
        return tenant

    @pytest.mark.anyio
    async def test_get_settings_returns_dict(self, mock_db: AsyncMock) -> None:
        from app.services.tenant_settings import get_settings

        tenant = self._make_tenant({"notification_prefs": {"email_overdue_invoices": True}})
        mock_db.scalar = AsyncMock(return_value=tenant)

        result = await get_settings(mock_db, "t1")
        assert result["org_name"] == "Test Corp"
        assert result["country"] == "AU"
        assert result["functional_currency"] == "AUD"
        assert result["fiscal_year_start_month"] == 7

    @pytest.mark.anyio
    async def test_update_settings_merges(self, mock_db: AsyncMock) -> None:
        from unittest.mock import patch

        from app.services.tenant_settings import update_settings

        tenant = self._make_tenant()
        mock_db.scalar = AsyncMock(return_value=tenant)

        with patch("app.services.tenant_settings.emit", new_callable=AsyncMock):
            await update_settings(mock_db, "t1", "actor-1", {"org_name": "New Name"})
        assert tenant.name == "New Name"
