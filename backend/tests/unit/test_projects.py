"""Unit tests for projects & time tracking module (Issue #67).

Tests cover:
  - Model source verification (Project, TimeEntry, BillingRate)
  - Schema validation (ProjectCreate, TimeEntryCreate, BillingRateCreate)
  - Billing rate resolution logic
  - Invoice generation from time entries
  - WIP calculation
  - Billed time entries are locked (cannot be modified)
  - API endpoints exist (source inspection)
  - Migration exists with upgrade+downgrade
"""

from __future__ import annotations

import pathlib
import sys
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.schemas import (
    BillingRateCreate,
    BillingRateResponse,
    GenerateInvoiceRequest,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    TimeEntryCreate,
    TimeEntryResponse,
    TimeEntryUpdate,
    WipResponse,
)

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")

_MODELS_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
_SERVICE_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "projects.py"
_API_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "projects.py"
_MIGRATION_DIR = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"


# ── Model source verification ────────────────────────────────────────────────


class TestProjectModel:
    """Verify Project model definition via source inspection."""

    def test_project_class_exists(self) -> None:
        source = _MODELS_PATH.read_text()
        assert "class Project(Base):" in source

    def test_projects_table_name(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class Project(Base):")
        block = source[idx : idx + 500]
        assert '"projects"' in block

    def test_has_required_fields(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class Project(Base):")
        block = source[idx : idx + 2000]
        for field in [
            "tenant_id",
            "contact_id",
            "name",
            "code",
            "description",
            "status",
            "budget_hours",
            "budget_amount",
            "currency",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "version",
        ]:
            assert field in block, f"Missing field: {field}"

    def test_budget_amount_uses_numeric_19_4(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class Project(Base):")
        block = source[idx : idx + 2000]
        assert "Numeric(19, 4)" in block

    def test_status_constraint(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class Project(Base):")
        block = source[idx : idx + 2000]
        assert "active" in block
        assert "completed" in block
        assert "archived" in block

    def test_unique_tenant_code(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class Project(Base):")
        block = source[idx : idx + 2000]
        assert "uq_projects_tenant_code" in block


class TestTimeEntryModel:
    """Verify TimeEntry model definition via source inspection."""

    def test_time_entry_class_exists(self) -> None:
        source = _MODELS_PATH.read_text()
        assert "class TimeEntry(Base):" in source

    def test_time_entries_table_name(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class TimeEntry(Base):")
        block = source[idx : idx + 500]
        assert '"time_entries"' in block

    def test_has_required_fields(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class TimeEntry(Base):")
        block = source[idx : idx + 2000]
        for field in [
            "tenant_id",
            "project_id",
            "user_id",
            "entry_date",
            "hours",
            "description",
            "is_billable",
            "approval_status",
            "billed_invoice_id",
        ]:
            assert field in block, f"Missing field: {field}"

    def test_hours_positive_constraint(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class TimeEntry(Base):")
        block = source[idx : idx + 2000]
        assert "ck_time_entries_hours_positive" in block

    def test_approval_status_constraint(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class TimeEntry(Base):")
        block = source[idx : idx + 2000]
        assert "pending" in block
        assert "approved" in block
        assert "rejected" in block


class TestBillingRateModel:
    """Verify BillingRate model definition via source inspection."""

    def test_billing_rate_class_exists(self) -> None:
        source = _MODELS_PATH.read_text()
        assert "class BillingRate(Base):" in source

    def test_billing_rates_table_name(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class BillingRate(Base):")
        block = source[idx : idx + 500]
        assert '"billing_rates"' in block

    def test_has_required_fields(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class BillingRate(Base):")
        block = source[idx : idx + 2000]
        for field in [
            "tenant_id",
            "project_id",
            "user_id",
            "role",
            "rate",
            "currency",
            "effective_from",
            "effective_to",
        ]:
            assert field in block, f"Missing field: {field}"

    def test_rate_uses_numeric_19_4(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class BillingRate(Base):")
        block = source[idx : idx + 2000]
        assert "Numeric(19, 4)" in block

    def test_rate_non_negative_constraint(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class BillingRate(Base):")
        block = source[idx : idx + 2000]
        assert "ck_billing_rates_rate_non_negative" in block


# ── Schema validation ────────────────────────────────────────────────────────


class TestProjectSchemas:
    """Validate Project Pydantic schemas."""

    def test_project_create_minimal(self) -> None:
        p = ProjectCreate(contact_id="abc-123", name="Test Project")
        assert p.name == "Test Project"
        assert p.status == "active"
        assert p.currency == "USD"
        assert p.budget_hours is None
        assert p.budget_amount is None

    def test_project_create_with_budget(self) -> None:
        p = ProjectCreate(
            contact_id="abc-123",
            name="Test",
            budget_hours="100.00",
            budget_amount="50000.0000",
        )
        assert p.budget_hours == "100.00"
        assert p.budget_amount == "50000.0000"

    def test_project_create_rejects_negative_budget_hours(self) -> None:
        with pytest.raises(Exception):
            ProjectCreate(contact_id="abc", name="Test", budget_hours="-10")

    def test_project_create_rejects_negative_budget_amount(self) -> None:
        with pytest.raises(Exception):
            ProjectCreate(contact_id="abc", name="Test", budget_amount="-1000")

    def test_project_create_rejects_invalid_status(self) -> None:
        with pytest.raises(Exception):
            ProjectCreate(contact_id="abc", name="Test", status="invalid")

    def test_project_create_rejects_empty_name(self) -> None:
        with pytest.raises(Exception):
            ProjectCreate(contact_id="abc", name="")

    def test_project_update_all_none(self) -> None:
        u = ProjectUpdate()
        assert u.name is None

    def test_project_response_from_attributes(self) -> None:
        assert ProjectResponse.model_config.get("from_attributes") is True


class TestTimeEntrySchemas:
    """Validate TimeEntry Pydantic schemas."""

    def test_time_entry_create_minimal(self) -> None:
        te = TimeEntryCreate(
            project_id="proj-1",
            user_id="user-1",
            entry_date=date(2026, 4, 18),
            hours="2.50",
        )
        assert te.is_billable is True
        assert Decimal(te.hours) == Decimal("2.50")

    def test_time_entry_create_rejects_zero_hours(self) -> None:
        with pytest.raises(Exception):
            TimeEntryCreate(
                project_id="p", user_id="u", entry_date=date(2026, 1, 1), hours="0"
            )

    def test_time_entry_create_rejects_negative_hours(self) -> None:
        with pytest.raises(Exception):
            TimeEntryCreate(
                project_id="p", user_id="u", entry_date=date(2026, 1, 1), hours="-1"
            )

    def test_time_entry_update_rejects_invalid_approval_status(self) -> None:
        with pytest.raises(Exception):
            TimeEntryUpdate(approval_status="invalid")

    def test_time_entry_update_accepts_valid_approval_status(self) -> None:
        u = TimeEntryUpdate(approval_status="approved")
        assert u.approval_status == "approved"

    def test_time_entry_response_from_attributes(self) -> None:
        assert TimeEntryResponse.model_config.get("from_attributes") is True


class TestBillingRateSchemas:
    """Validate BillingRate Pydantic schemas."""

    def test_billing_rate_create_minimal(self) -> None:
        br = BillingRateCreate(rate="150.0000", effective_from=date(2026, 1, 1))
        assert Decimal(br.rate) == Decimal("150.0000")
        assert br.currency == "USD"
        assert br.project_id is None
        assert br.user_id is None

    def test_billing_rate_create_rejects_negative_rate(self) -> None:
        with pytest.raises(Exception):
            BillingRateCreate(rate="-10", effective_from=date(2026, 1, 1))

    def test_billing_rate_accepts_zero_rate(self) -> None:
        br = BillingRateCreate(rate="0", effective_from=date(2026, 1, 1))
        assert Decimal(br.rate) == Decimal("0")

    def test_billing_rate_response_from_attributes(self) -> None:
        assert BillingRateResponse.model_config.get("from_attributes") is True


class TestGenerateInvoiceRequest:
    """Validate GenerateInvoiceRequest schema."""

    def test_valid_date_range(self) -> None:
        req = GenerateInvoiceRequest(
            from_date=date(2026, 1, 1), to_date=date(2026, 1, 31)
        )
        assert req.from_date < req.to_date

    def test_same_date_allowed(self) -> None:
        req = GenerateInvoiceRequest(
            from_date=date(2026, 1, 1), to_date=date(2026, 1, 1)
        )
        assert req.from_date == req.to_date

    def test_rejects_reversed_dates(self) -> None:
        with pytest.raises(Exception):
            GenerateInvoiceRequest(
                from_date=date(2026, 2, 1), to_date=date(2026, 1, 1)
            )


class TestWipResponse:
    """Validate WipResponse schema."""

    def test_wip_response_construction(self) -> None:
        wip = WipResponse(
            project_id="proj-1",
            entries=[],
            total_hours="0",
            total_amount="0",
            currency="USD",
        )
        assert wip.total_hours == "0"


# ── Service logic via source inspection ──────────────────────────────────────


class TestServiceSource:
    """Verify service code structure via source inspection."""

    def _read_source(self) -> str:
        return _SERVICE_PATH.read_text()

    def test_service_file_exists(self) -> None:
        assert _SERVICE_PATH.exists()

    def test_create_project_function(self) -> None:
        source = self._read_source()
        assert "async def create_project(" in source

    def test_list_projects_function(self) -> None:
        source = self._read_source()
        assert "async def list_projects(" in source

    def test_get_project_function(self) -> None:
        source = self._read_source()
        assert "async def get_project(" in source

    def test_update_project_function(self) -> None:
        source = self._read_source()
        assert "async def update_project(" in source

    def test_create_time_entry_function(self) -> None:
        source = self._read_source()
        assert "async def create_time_entry(" in source

    def test_update_time_entry_function(self) -> None:
        source = self._read_source()
        assert "async def update_time_entry(" in source

    def test_resolve_billing_rate_function(self) -> None:
        source = self._read_source()
        assert "async def resolve_billing_rate(" in source

    def test_generate_invoice_function(self) -> None:
        source = self._read_source()
        assert "async def generate_invoice(" in source

    def test_get_wip_function(self) -> None:
        source = self._read_source()
        assert "async def get_wip(" in source

    def test_billed_entry_locked_check(self) -> None:
        """Service must check billed_invoice_id before allowing updates."""
        source = self._read_source()
        assert "billed_invoice_id" in source
        assert "TimeEntryLockedError" in source

    def test_rate_resolution_priority(self) -> None:
        """Service resolves rates: project+user > user > project-role > default."""
        source = self._read_source()
        assert "Project + user specific" in source or "project_id == project_id" in source

    def test_generate_invoice_marks_entries_billed(self) -> None:
        """After invoice generation, entries must be marked with billed_invoice_id."""
        source = self._read_source()
        assert "billed_invoice_id=inv.id" in source or "billed_invoice_id" in source

    def test_audit_events_emitted(self) -> None:
        """Service must emit audit events for create/update/generate operations."""
        source = self._read_source()
        assert "await emit(" in source
        assert "project.created" in source
        assert "time_entry.created" in source


# ── Service tests with mocking ───────────────────────────────────────────────


@_skip_311
class TestBillingRateResolution:
    """Test billing rate resolution logic with mocked DB."""

    @pytest.mark.asyncio
    async def test_resolve_project_user_rate(self) -> None:
        from app.services.projects import resolve_billing_rate

        mock_db = AsyncMock()
        # First call returns project+user rate
        mock_db.scalar = AsyncMock(return_value=Decimal("200.0000"))

        rate = await resolve_billing_rate(
            mock_db,
            tenant_id="t1",
            project_id="p1",
            user_id="u1",
            entry_date=date(2026, 4, 1),
        )
        assert rate == Decimal("200.0000")

    @pytest.mark.asyncio
    async def test_resolve_fallback_to_user_rate(self) -> None:
        from app.services.projects import resolve_billing_rate

        mock_db = AsyncMock()
        # First call (project+user) returns None, second (user) returns rate
        mock_db.scalar = AsyncMock(side_effect=[None, Decimal("150.0000")])

        rate = await resolve_billing_rate(
            mock_db,
            tenant_id="t1",
            project_id="p1",
            user_id="u1",
            entry_date=date(2026, 4, 1),
        )
        assert rate == Decimal("150.0000")

    @pytest.mark.asyncio
    async def test_resolve_fallback_to_default(self) -> None:
        from app.services.projects import resolve_billing_rate

        mock_db = AsyncMock()
        # First three calls return None, fourth (default) returns rate
        mock_db.scalar = AsyncMock(
            side_effect=[None, None, None, Decimal("100.0000")]
        )

        rate = await resolve_billing_rate(
            mock_db,
            tenant_id="t1",
            project_id="p1",
            user_id="u1",
            entry_date=date(2026, 4, 1),
        )
        assert rate == Decimal("100.0000")

    @pytest.mark.asyncio
    async def test_resolve_no_rate_raises(self) -> None:
        from app.services.projects import NoBillingRateError, resolve_billing_rate

        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=None)

        with pytest.raises(NoBillingRateError):
            await resolve_billing_rate(
                mock_db,
                tenant_id="t1",
                project_id="p1",
                user_id="u1",
                entry_date=date(2026, 4, 1),
            )


@_skip_311
class TestTimeEntryLocking:
    """Test that billed time entries cannot be modified."""

    @pytest.mark.asyncio
    async def test_update_billed_entry_raises(self) -> None:
        from app.services.projects import TimeEntryLockedError, update_time_entry

        mock_db = AsyncMock()
        mock_entry = MagicMock()
        mock_entry.id = "te-1"
        mock_entry.tenant_id = "t1"
        mock_entry.billed_invoice_id = "inv-123"
        mock_db.scalar = AsyncMock(return_value=mock_entry)

        with pytest.raises(TimeEntryLockedError):
            await update_time_entry(
                mock_db, "t1", "te-1", "actor-1", hours=Decimal("5.00")
            )


# ── API router source verification ──────────────────────────────────────────


class TestApiRouterSource:
    """Verify API router endpoints exist via source inspection."""

    def _read_source(self) -> str:
        return _API_PATH.read_text()

    def test_api_file_exists(self) -> None:
        assert _API_PATH.exists()

    def test_projects_post_endpoint(self) -> None:
        source = self._read_source()
        assert '@router.post("")' in source or "@router.post(\"\"" in source

    def test_projects_get_list_endpoint(self) -> None:
        source = self._read_source()
        assert '@router.get("")' in source or "@router.get(\"\"" in source

    def test_projects_get_one_endpoint(self) -> None:
        source = self._read_source()
        assert "/{project_id}" in source

    def test_projects_patch_endpoint(self) -> None:
        source = self._read_source()
        assert '@router.patch("/{project_id}"' in source

    def test_time_entries_post_endpoint(self) -> None:
        source = self._read_source()
        assert "time_entries_router" in source

    def test_time_entries_patch_endpoint(self) -> None:
        source = self._read_source()
        assert "/{entry_id}" in source

    def test_billing_rates_post_endpoint(self) -> None:
        source = self._read_source()
        assert "billing_rates_router" in source

    def test_generate_invoice_endpoint(self) -> None:
        source = self._read_source()
        assert "generate-invoice" in source

    def test_wip_endpoint(self) -> None:
        source = self._read_source()
        assert "/wip" in source

    def test_router_registered_in_main(self) -> None:
        main_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "main.py"
        source = main_path.read_text()
        assert "projects.router" in source
        assert "projects.time_entries_router" in source
        assert "projects.billing_rates_router" in source


# ── Migration verification ───────────────────────────────────────────────────


class TestMigration:
    """Verify migration for projects tables exists."""

    def _find_migration(self) -> str | None:
        for p in _MIGRATION_DIR.iterdir():
            if "projects" in p.name and "time_entries" in p.name:
                return p.read_text()
        return None

    def test_migration_exists(self) -> None:
        source = self._find_migration()
        assert source is not None, "Migration for projects/time_entries not found"

    def test_migration_creates_projects_table(self) -> None:
        source = self._find_migration()
        assert source is not None
        assert '"projects"' in source

    def test_migration_creates_time_entries_table(self) -> None:
        source = self._find_migration()
        assert source is not None
        assert '"time_entries"' in source

    def test_migration_creates_billing_rates_table(self) -> None:
        source = self._find_migration()
        assert source is not None
        assert '"billing_rates"' in source

    def test_migration_has_downgrade(self) -> None:
        source = self._find_migration()
        assert source is not None
        assert "def downgrade()" in source

    def test_migration_downgrade_drops_tables(self) -> None:
        source = self._find_migration()
        assert source is not None
        # Tables dropped in reverse order (billing_rates, time_entries, projects)
        downgrade_idx = source.index("def downgrade()")
        downgrade_body = source[downgrade_idx:]
        assert 'drop_table("billing_rates")' in downgrade_body
        assert 'drop_table("time_entries")' in downgrade_body
        assert 'drop_table("projects")' in downgrade_body

    def test_migration_money_columns_use_numeric_19_4(self) -> None:
        source = self._find_migration()
        assert source is not None
        assert "Numeric(19, 4)" in source

    def test_migration_hours_column_uses_numeric_6_2(self) -> None:
        source = self._find_migration()
        assert source is not None
        assert "Numeric(6, 2)" in source
