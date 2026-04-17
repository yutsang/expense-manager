"""Unit tests for UBO (Ultimate Beneficial Owner) tracking (Issue #33).

HK Companies Ordinance Cap 622 compliance: contacts that are corporate entities
need a Significant Controllers Register recording each controller's name, ID,
nationality, address, ownership percentage, and nature of control.

Tests cover:
  - ContactUBO model exists with all required columns
  - ContactUBO model has correct constraints (control_type enum, ownership_pct range)
  - Pydantic schemas for create/update/response
  - UBO service: create, list, get, update
  - UBO service: ownership_pct validation (0-100 range, NUMERIC(5,2))
  - KYC dashboard alert: corporate contacts with no UBO records
  - Migration 0024: creates contact_ubos table with upgrade + downgrade
  - API endpoints exist under /v1/contacts/{id}/ubos
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ---------------------------------------------------------------------------
# Model source inspection tests
# ---------------------------------------------------------------------------


class TestContactUBOModel:
    """ContactUBO model must have all columns required by Cap 622."""

    def _read_models_source(self) -> str:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def test_contact_ubos_table_exists(self) -> None:
        source = self._read_models_source()
        assert '"contact_ubos"' in source

    def test_class_name_exists(self) -> None:
        source = self._read_models_source()
        assert "class ContactUBO" in source

    def test_controller_name_column(self) -> None:
        source = self._read_models_source()
        assert "controller_name" in source

    def test_id_type_column(self) -> None:
        source = self._read_models_source()
        # Must appear in the ContactUBO section
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "id_type" in block

    def test_id_number_column(self) -> None:
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "id_number" in block

    def test_nationality_column(self) -> None:
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "nationality" in block

    def test_address_column(self) -> None:
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "address" in block

    def test_ownership_pct_column(self) -> None:
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "ownership_pct" in block

    def test_ownership_pct_precision(self) -> None:
        """ownership_pct should be Numeric(5, 2) per the issue spec."""
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "Numeric(5, 2)" in block

    def test_control_type_column(self) -> None:
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "control_type" in block

    def test_is_significant_controller_column(self) -> None:
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "is_significant_controller" in block

    def test_effective_date_column(self) -> None:
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "effective_date" in block

    def test_ceased_date_column(self) -> None:
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "ceased_date" in block

    def test_tenant_id_column(self) -> None:
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "tenant_id" in block

    def test_contact_id_fk(self) -> None:
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "contact_id" in block
        assert "contacts.id" in block

    def test_standard_columns(self) -> None:
        """id, created_at, updated_at, version must be present."""
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        for col in ("created_at", "updated_at", "version"):
            assert col in block, f"Missing standard column: {col}"

    def test_control_type_check_constraint(self) -> None:
        """DB check constraint for valid control_type values."""
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        for val in ("shareholding", "voting_rights", "board_appointment", "other"):
            assert val in block, f"Missing control_type enum value: {val}"

    def test_ownership_pct_check_constraint(self) -> None:
        """ownership_pct must be between 0 and 100."""
        source = self._read_models_source()
        idx = source.index("class ContactUBO")
        block = source[idx : idx + 2000]
        assert "ownership_pct" in block
        # Should have a check constraint limiting range
        assert "100" in block


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestUBOSchemas:
    """Pydantic schemas for UBO create/update/response."""

    def test_ubo_create_schema_exists(self) -> None:
        from app.api.v1.schemas import ContactUBOCreate

        assert ContactUBOCreate is not None

    def test_ubo_create_required_fields(self) -> None:
        from app.api.v1.schemas import ContactUBOCreate

        fields = ContactUBOCreate.model_fields
        assert "controller_name" in fields
        assert "control_type" in fields
        assert "ownership_pct" in fields
        assert "effective_date" in fields

    def test_ubo_create_valid(self) -> None:
        from app.api.v1.schemas import ContactUBOCreate

        ubo = ContactUBOCreate(
            controller_name="John Doe",
            id_type="passport",
            id_number="A12345678",
            nationality="HK",
            address="123 Main St, Hong Kong",
            ownership_pct="25.50",
            control_type="shareholding",
            is_significant_controller=True,
            effective_date=date(2024, 1, 1),
        )
        assert ubo.controller_name == "John Doe"
        assert ubo.ownership_pct == "25.50"

    def test_ubo_create_invalid_control_type(self) -> None:
        from app.api.v1.schemas import ContactUBOCreate

        with pytest.raises(Exception):
            ContactUBOCreate(
                controller_name="John Doe",
                ownership_pct="25.00",
                control_type="invalid_type",
                effective_date=date(2024, 1, 1),
            )

    def test_ubo_create_negative_ownership_rejected(self) -> None:
        from app.api.v1.schemas import ContactUBOCreate

        with pytest.raises(Exception):
            ContactUBOCreate(
                controller_name="John Doe",
                ownership_pct="-1.00",
                control_type="shareholding",
                effective_date=date(2024, 1, 1),
            )

    def test_ubo_create_over_100_ownership_rejected(self) -> None:
        from app.api.v1.schemas import ContactUBOCreate

        with pytest.raises(Exception):
            ContactUBOCreate(
                controller_name="John Doe",
                ownership_pct="101.00",
                control_type="shareholding",
                effective_date=date(2024, 1, 1),
            )

    def test_ubo_update_schema_exists(self) -> None:
        from app.api.v1.schemas import ContactUBOUpdate

        assert ContactUBOUpdate is not None

    def test_ubo_update_all_fields_optional(self) -> None:
        from app.api.v1.schemas import ContactUBOUpdate

        # Should not raise — all fields optional
        ubo = ContactUBOUpdate()
        assert ubo is not None

    def test_ubo_response_schema_exists(self) -> None:
        from app.api.v1.schemas import ContactUBOResponse

        assert ContactUBOResponse is not None

    def test_ubo_response_has_id(self) -> None:
        from app.api.v1.schemas import ContactUBOResponse

        assert "id" in ContactUBOResponse.model_fields

    def test_ubo_response_has_contact_id(self) -> None:
        from app.api.v1.schemas import ContactUBOResponse

        assert "contact_id" in ContactUBOResponse.model_fields

    def test_ubo_response_from_attributes(self) -> None:
        from app.api.v1.schemas import ContactUBOResponse

        assert ContactUBOResponse.model_config.get("from_attributes") is True


# ---------------------------------------------------------------------------
# Service source inspection
# ---------------------------------------------------------------------------


class TestUBOServiceExists:
    """UBO service functions exist in kyc.py."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "kyc.py"
        return svc_path.read_text()

    def test_create_ubo_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def create_ubo(" in source

    def test_list_ubos_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def list_ubos(" in source

    def test_get_ubo_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def get_ubo(" in source

    def test_update_ubo_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def update_ubo(" in source

    def test_ubo_not_found_error_exists(self) -> None:
        source = self._read_service_source()
        assert "class UBONotFoundError" in source


# ---------------------------------------------------------------------------
# Service-level async tests
# ---------------------------------------------------------------------------


@_skip_311
class TestCreateUBO:
    """create_ubo service function tests."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.anyio
    async def test_create_ubo_basic(self, mock_db: AsyncMock) -> None:
        from app.services.kyc import create_ubo

        await create_ubo(
            mock_db,
            tenant_id="t1",
            contact_id="c1",
            controller_name="John Doe",
            ownership_pct=Decimal("25.00"),
            control_type="shareholding",
            is_significant_controller=True,
            effective_date=date(2024, 1, 1),
        )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

    @pytest.mark.anyio
    async def test_create_ubo_with_all_fields(self, mock_db: AsyncMock) -> None:
        from app.services.kyc import create_ubo

        await create_ubo(
            mock_db,
            tenant_id="t1",
            contact_id="c1",
            controller_name="Jane Smith",
            id_type="passport",
            id_number="P999888",
            nationality="GB",
            address="10 Downing St, London",
            ownership_pct=Decimal("51.00"),
            control_type="voting_rights",
            is_significant_controller=True,
            effective_date=date(2023, 6, 15),
            ceased_date=None,
        )
        mock_db.add.assert_called_once()


@_skip_311
class TestListUBOs:
    """list_ubos service function tests."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_list_ubos_returns_list(self, mock_db: AsyncMock) -> None:
        from app.services.kyc import list_ubos

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await list_ubos(mock_db, contact_id="c1", tenant_id="t1")
        assert isinstance(result, list)


@_skip_311
class TestGetUBO:
    """get_ubo service function tests."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_get_ubo_not_found_raises(self, mock_db: AsyncMock) -> None:
        from app.services.kyc import UBONotFoundError, get_ubo

        mock_db.scalar = AsyncMock(return_value=None)

        with pytest.raises(UBONotFoundError):
            await get_ubo(mock_db, ubo_id="nonexistent", tenant_id="t1")


@_skip_311
class TestUpdateUBO:
    """update_ubo service function tests."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        return db

    def _make_ubo(self) -> MagicMock:
        ubo = MagicMock()
        ubo.id = "ubo-1"
        ubo.tenant_id = "t1"
        ubo.contact_id = "c1"
        ubo.controller_name = "John Doe"
        ubo.ownership_pct = Decimal("25.00")
        ubo.control_type = "shareholding"
        ubo.is_significant_controller = True
        ubo.effective_date = date(2024, 1, 1)
        ubo.ceased_date = None
        ubo.version = 1
        return ubo

    @pytest.mark.anyio
    async def test_update_ubo_changes_fields(self, mock_db: AsyncMock) -> None:
        from app.services.kyc import update_ubo

        ubo = self._make_ubo()
        mock_db.scalar = AsyncMock(return_value=ubo)

        result = await update_ubo(
            mock_db,
            ubo_id="ubo-1",
            tenant_id="t1",
            ownership_pct=Decimal("30.00"),
        )
        assert result.ownership_pct == Decimal("30.00")

    @pytest.mark.anyio
    async def test_update_ubo_bumps_version(self, mock_db: AsyncMock) -> None:
        from app.services.kyc import update_ubo

        ubo = self._make_ubo()
        mock_db.scalar = AsyncMock(return_value=ubo)

        result = await update_ubo(
            mock_db,
            ubo_id="ubo-1",
            tenant_id="t1",
            controller_name="Jane Doe",
        )
        assert result.version == 2

    @pytest.mark.anyio
    async def test_update_ubo_not_found_raises(self, mock_db: AsyncMock) -> None:
        from app.services.kyc import UBONotFoundError, update_ubo

        mock_db.scalar = AsyncMock(return_value=None)

        with pytest.raises(UBONotFoundError):
            await update_ubo(
                mock_db,
                ubo_id="nonexistent",
                tenant_id="t1",
                controller_name="X",
            )


# ---------------------------------------------------------------------------
# Dashboard alert for missing UBOs on corporate contacts
# ---------------------------------------------------------------------------


@_skip_311
class TestDashboardAlertMissingUBOs:
    """KYC dashboard shows warning for corporate contacts with no UBO records."""

    def test_dashboard_alerts_has_missing_ubos_field(self) -> None:
        from app.api.v1.schemas import KycDashboardAlerts

        assert "missing_ubos" in KycDashboardAlerts.model_fields

    def test_dashboard_alerts_source_counts_missing_ubos(self) -> None:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "kyc.py"
        source = svc_path.read_text()
        assert "missing_ubos" in source


# ---------------------------------------------------------------------------
# Migration source inspection
# ---------------------------------------------------------------------------


class TestMigration0024Exists:
    """Migration 0024 creates contact_ubos table."""

    def _read_migration_source(self) -> str:
        import pathlib

        mig_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "migrations"
            / "versions"
            / "0024_contact_ubos.py"
        )
        return mig_path.read_text()

    def test_migration_file_exists(self) -> None:
        self._read_migration_source()

    def test_migration_creates_table(self) -> None:
        source = self._read_migration_source()
        assert "contact_ubos" in source
        assert "create_table" in source

    def test_migration_has_controller_name(self) -> None:
        source = self._read_migration_source()
        assert "controller_name" in source

    def test_migration_has_ownership_pct(self) -> None:
        source = self._read_migration_source()
        assert "ownership_pct" in source

    def test_migration_has_control_type(self) -> None:
        source = self._read_migration_source()
        assert "control_type" in source

    def test_migration_has_rls(self) -> None:
        source = self._read_migration_source()
        assert "ROW LEVEL SECURITY" in source

    def test_migration_has_downgrade(self) -> None:
        source = self._read_migration_source()
        assert "def downgrade()" in source

    def test_migration_downgrade_drops_table(self) -> None:
        source = self._read_migration_source()
        assert "drop_table" in source

    def test_migration_revises_0023(self) -> None:
        source = self._read_migration_source()
        assert '"0023"' in source


# ---------------------------------------------------------------------------
# API endpoint source inspection
# ---------------------------------------------------------------------------


class TestUBOEndpoints:
    """GET/POST/PATCH /v1/contacts/{id}/ubos endpoints exist."""

    def _read_kyc_api_source(self) -> str:
        import pathlib

        api_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "kyc.py"
        return api_path.read_text()

    def test_list_ubos_endpoint_exists(self) -> None:
        source = self._read_kyc_api_source()
        assert "ubos" in source
        assert "GET" in source or "get" in source.lower()

    def test_create_ubo_endpoint_exists(self) -> None:
        source = self._read_kyc_api_source()
        assert "ContactUBOCreate" in source or "create_ubo" in source

    def test_update_ubo_endpoint_exists(self) -> None:
        source = self._read_kyc_api_source()
        assert "ContactUBOUpdate" in source or "update_ubo" in source

    def test_endpoints_are_nested_under_contacts(self) -> None:
        """UBO endpoints should be at /contacts/{contact_id}/ubos."""
        source = self._read_kyc_api_source()
        assert "contact_id" in source
        assert "ubos" in source
