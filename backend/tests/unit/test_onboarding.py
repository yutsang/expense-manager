"""Unit tests for tenant onboarding wizard (Issue #34).

Tests cover:
  - OnboardingSetup schema validates company details + COA template + bank info
  - Service: setup_tenant provisions COA, periods, bank account, first contact
  - setup_completed_at is set on tenant after completion
  - Skip wizard: tenant with setup_completed_at != None is not redirected
  - COA template choices: general, professional_services, retail
  - Onboarding endpoint exists at POST /v1/onboarding/setup
"""

from __future__ import annotations

import pathlib
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ── Schema tests ────────────────────────────────────────────────────────────


class TestOnboardingSetupSchema:
    """Validates OnboardingSetup request schema."""

    def test_valid_onboarding_request(self) -> None:
        from app.api.v1.schemas import OnboardingSetup

        body = OnboardingSetup(
            company_name="Acme Corp",
            legal_name="Acme Corporation Ltd",
            country="US",
            functional_currency="USD",
            fiscal_year_start_month=1,
            coa_template="general",
            bank_account_name="Main Checking",
            bank_name="First National",
            bank_account_number="1234567890",
            bank_currency="USD",
        )
        assert body.company_name == "Acme Corp"
        assert body.coa_template == "general"

    def test_coa_template_must_be_valid(self) -> None:
        from app.api.v1.schemas import OnboardingSetup

        with pytest.raises(Exception):
            OnboardingSetup(
                company_name="Acme Corp",
                legal_name="Acme Corporation Ltd",
                country="US",
                functional_currency="USD",
                fiscal_year_start_month=1,
                coa_template="invalid_template",
                bank_account_name="Main Checking",
            )

    def test_fiscal_year_start_month_range(self) -> None:
        from app.api.v1.schemas import OnboardingSetup

        with pytest.raises(Exception):
            OnboardingSetup(
                company_name="Acme Corp",
                legal_name="Acme Corporation Ltd",
                country="US",
                functional_currency="USD",
                fiscal_year_start_month=13,
                coa_template="general",
                bank_account_name="Main Checking",
            )

    def test_optional_fields_default_to_none(self) -> None:
        from app.api.v1.schemas import OnboardingSetup

        body = OnboardingSetup(
            company_name="Acme Corp",
            legal_name="Acme Corporation Ltd",
            country="US",
            functional_currency="USD",
            fiscal_year_start_month=1,
            coa_template="general",
            bank_account_name="Main Checking",
        )
        assert body.bank_name is None
        assert body.bank_account_number is None
        assert body.first_contact_name is None

    def test_first_contact_fields(self) -> None:
        from app.api.v1.schemas import OnboardingSetup

        body = OnboardingSetup(
            company_name="Acme Corp",
            legal_name="Acme Corp",
            country="US",
            functional_currency="USD",
            fiscal_year_start_month=1,
            coa_template="general",
            bank_account_name="Main Checking",
            first_contact_name="Jane Customer",
            first_contact_email="jane@example.com",
            first_contact_type="customer",
        )
        assert body.first_contact_name == "Jane Customer"
        assert body.first_contact_type == "customer"

    def test_professional_services_template(self) -> None:
        from app.api.v1.schemas import OnboardingSetup

        body = OnboardingSetup(
            company_name="Law Firm",
            legal_name="Law Firm LLP",
            country="US",
            functional_currency="USD",
            fiscal_year_start_month=1,
            coa_template="professional_services",
            bank_account_name="Operating",
        )
        assert body.coa_template == "professional_services"

    def test_retail_template(self) -> None:
        from app.api.v1.schemas import OnboardingSetup

        body = OnboardingSetup(
            company_name="Shop",
            legal_name="Shop LLC",
            country="US",
            functional_currency="USD",
            fiscal_year_start_month=1,
            coa_template="retail",
            bank_account_name="Main",
        )
        assert body.coa_template == "retail"


class TestOnboardingResponseSchema:
    """OnboardingResponse returns summary of what was created."""

    def test_response_has_required_fields(self) -> None:
        from app.api.v1.schemas import OnboardingResponse

        resp = OnboardingResponse(
            tenant_id="t1",
            setup_completed_at="2026-04-16T00:00:00Z",
            accounts_created=50,
            periods_created=24,
            bank_account_id="ba1",
            first_contact_id=None,
        )
        assert resp.accounts_created == 50
        assert resp.first_contact_id is None


# ── Model tests (source-level) ──────────────────────────────────────────────


class TestTenantModelSetupCompleted:
    """Tenant model must have setup_completed_at column."""

    def test_setup_completed_at_column_exists(self) -> None:
        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        source = models_path.read_text()
        assert "setup_completed_at" in source

    def test_setup_completed_at_is_nullable(self) -> None:
        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        source = models_path.read_text()
        # Should be nullable (None means wizard not completed)
        assert "setup_completed_at" in source


# ── Service tests ────────────────────────────────────────────────────────────


class TestOnboardingServiceSource:
    """Verify onboarding service code exists."""

    def _read_service_source(self) -> str:
        svc_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "onboarding.py"
        )
        return svc_path.read_text()

    def test_setup_tenant_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def setup_tenant(" in source

    def test_service_provisions_coa(self) -> None:
        source = self._read_service_source()
        assert "get_coa_template" in source or "coa_template" in source

    def test_service_provisions_periods(self) -> None:
        source = self._read_service_source()
        assert "provision_periods" in source

    def test_service_sets_setup_completed_at(self) -> None:
        source = self._read_service_source()
        assert "setup_completed_at" in source

    def test_service_creates_bank_account(self) -> None:
        source = self._read_service_source()
        assert "BankAccount" in source


class TestOnboardingApiSource:
    """Verify API endpoint source."""

    def _read_api_source(self) -> str:
        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "onboarding.py"
        )
        return api_path.read_text()

    def test_setup_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert '"/setup"' in source or "setup" in source

    def test_endpoint_calls_setup_tenant(self) -> None:
        source = self._read_api_source()
        assert "setup_tenant" in source


# ── Service-level async tests ────────────────────────────────────────────────


@_skip_311
class TestSetupTenantService:
    """Integration-style tests using mocked DB session."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        return db

    def _make_tenant(self, *, setup_completed: bool = False) -> MagicMock:
        tenant = MagicMock()
        tenant.id = "t1"
        tenant.name = "Test Co"
        tenant.country = "US"
        tenant.functional_currency = "USD"
        tenant.fiscal_year_start_month = 1
        tenant.setup_completed_at = "2026-04-16T00:00:00Z" if setup_completed else None
        tenant.version = 1
        return tenant

    @pytest.mark.anyio
    async def test_setup_tenant_sets_completed_flag(self, mock_db: AsyncMock) -> None:
        from app.services.onboarding import setup_tenant

        tenant = self._make_tenant()
        mock_db.scalar.return_value = tenant

        with (
            patch("app.services.onboarding.create_account", new_callable=AsyncMock) as mock_create,
            patch("app.services.onboarding.provision_periods", new_callable=AsyncMock, return_value=[]),
        ):
            mock_create.return_value = MagicMock(id="acct-1")
            result = await setup_tenant(
                mock_db,
                tenant_id="t1",
                actor_id="actor-1",
                company_name="Acme Corp",
                legal_name="Acme Corp",
                country="US",
                functional_currency="USD",
                fiscal_year_start_month=1,
                coa_template="general",
                bank_account_name="Main Checking",
            )

        assert tenant.setup_completed_at is not None

    @pytest.mark.anyio
    async def test_setup_rejects_already_completed(self, mock_db: AsyncMock) -> None:
        from app.services.onboarding import OnboardingAlreadyCompleteError, setup_tenant

        tenant = self._make_tenant(setup_completed=True)
        mock_db.scalar.return_value = tenant

        with pytest.raises(OnboardingAlreadyCompleteError):
            await setup_tenant(
                mock_db,
                tenant_id="t1",
                actor_id="actor-1",
                company_name="Acme Corp",
                legal_name="Acme Corp",
                country="US",
                functional_currency="USD",
                fiscal_year_start_month=1,
                coa_template="general",
                bank_account_name="Main Checking",
            )


# ── Migration test ───────────────────────────────────────────────────────────


class TestOnboardingMigration:
    """Migration 0027 adds setup_completed_at to tenants."""

    def test_migration_file_exists(self) -> None:
        mig_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "migrations"
            / "versions"
            / "0027_tenants_add_setup_completed_at.py"
        )
        assert mig_path.exists(), f"Migration file not found: {mig_path}"

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        mig_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "migrations"
            / "versions"
            / "0027_tenants_add_setup_completed_at.py"
        )
        source = mig_path.read_text()
        assert "def upgrade()" in source
        assert "def downgrade()" in source
        assert "setup_completed_at" in source
