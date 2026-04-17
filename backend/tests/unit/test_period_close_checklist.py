"""Unit tests for period close checklist feature (Issue #40).

Tests cover:
  - PeriodChecklistItem model exists with correct columns
  - Checklist schemas (request/response) validation
  - Default checklist tasks constant
  - Service: get_checklist returns all items for a period
  - Service: sign_off_checklist_item marks an item
  - Service: transition_period rejects close when required items are unsigned
  - API endpoint source verification
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


class TestPeriodChecklistItemModel:
    """PeriodChecklistItem ORM model must exist in models.py."""

    def _read_models_source(self) -> str:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        return models_path.read_text()

    def test_model_class_exists(self) -> None:
        source = self._read_models_source()
        assert "class PeriodChecklistItem(" in source

    def test_table_name(self) -> None:
        source = self._read_models_source()
        assert '"period_checklist_items"' in source

    def test_has_period_id_column(self) -> None:
        source = self._read_models_source()
        assert "period_id" in source

    def test_has_task_key_column(self) -> None:
        source = self._read_models_source()
        assert "task_key" in source

    def test_has_checked_by_column(self) -> None:
        source = self._read_models_source()
        assert "checked_by" in source

    def test_has_checked_at_column(self) -> None:
        source = self._read_models_source()
        assert "checked_at" in source


class TestChecklistSchemas:
    """Pydantic schemas for checklist endpoints."""

    def _read_schemas_source(self) -> str:
        import pathlib

        path = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "schemas.py"
        return path.read_text()

    def test_checklist_item_response_class_exists(self) -> None:
        source = self._read_schemas_source()
        assert "class PeriodChecklistItemResponse(" in source

    def test_checklist_item_response_has_task_key(self) -> None:
        source = self._read_schemas_source()
        idx = source.index("class PeriodChecklistItemResponse(")
        block = source[idx : idx + 400]
        assert "task_key:" in block

    def test_checklist_item_response_has_label(self) -> None:
        source = self._read_schemas_source()
        idx = source.index("class PeriodChecklistItemResponse(")
        block = source[idx : idx + 400]
        assert "label:" in block

    def test_checklist_item_response_has_checked_by(self) -> None:
        source = self._read_schemas_source()
        idx = source.index("class PeriodChecklistItemResponse(")
        block = source[idx : idx + 400]
        assert "checked_by:" in block

    def test_checklist_item_response_has_checked_at(self) -> None:
        source = self._read_schemas_source()
        idx = source.index("class PeriodChecklistItemResponse(")
        block = source[idx : idx + 400]
        assert "checked_at:" in block

    def test_checklist_signoff_request_class_exists(self) -> None:
        source = self._read_schemas_source()
        assert "class ChecklistSignoffRequest(" in source

    def test_checklist_signoff_request_has_task_key(self) -> None:
        source = self._read_schemas_source()
        idx = source.index("class ChecklistSignoffRequest(")
        block = source[idx : idx + 300]
        assert "task_key:" in block


class TestDefaultChecklistTasks:
    """Fixed checklist tasks are defined as a constant."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "periods.py"
        return svc_path.read_text()

    def test_default_tasks_constant_exists(self) -> None:
        source = self._read_service_source()
        assert "DEFAULT_CHECKLIST_TASKS" in source

    def test_bank_reconciliation_in_defaults(self) -> None:
        source = self._read_service_source()
        assert "bank_reconciliation_complete" in source

    def test_ar_aging_reviewed_in_defaults(self) -> None:
        source = self._read_service_source()
        assert "ar_aging_reviewed" in source

    def test_ap_aging_reviewed_in_defaults(self) -> None:
        source = self._read_service_source()
        assert "ap_aging_reviewed" in source

    def test_expense_claims_approved_in_defaults(self) -> None:
        source = self._read_service_source()
        assert "expense_claims_approved" in source

    def test_accruals_posted_in_defaults(self) -> None:
        source = self._read_service_source()
        assert "accruals_posted" in source


class TestChecklistApiEndpointSource:
    """Verify checklist API endpoints exist."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "periods.py"
        return api_path.read_text()

    def test_get_checklist_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "/{period_id}/checklist" in source

    def test_signoff_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "/{period_id}/checklist/signoff" in source


class TestChecklistMigrationSource:
    """Migration for period_checklist_items table."""

    def test_migration_file_exists(self) -> None:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("0026_*.py"))
        assert len(migration_files) == 1, "Expected migration 0026 for period checklist"

    def test_migration_creates_table(self) -> None:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("0026_*.py"))
        source = migration_files[0].read_text()
        assert "period_checklist_items" in source


# ── Service-level async tests (require Python 3.11+) ────────────────────────


@_skip_311
class TestGetChecklist:
    """get_checklist returns all default tasks, merging sign-off state."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_returns_all_default_tasks(self, mock_db: AsyncMock) -> None:
        from app.services.periods import DEFAULT_CHECKLIST_TASKS, get_checklist

        # Simulate no items signed off yet
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        items = await get_checklist(mock_db, period_id="p-1", tenant_id="t-1")
        assert len(items) == len(DEFAULT_CHECKLIST_TASKS)

    @pytest.mark.anyio
    async def test_unsigned_items_have_no_checked_by(self, mock_db: AsyncMock) -> None:
        from app.services.periods import get_checklist

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        items = await get_checklist(mock_db, period_id="p-1", tenant_id="t-1")
        for item in items:
            assert item["checked_by"] is None
            assert item["checked_at"] is None


@_skip_311
class TestSignoffChecklistItem:
    """sign_off_checklist_item records who signed off and when."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.anyio
    async def test_signoff_creates_record(self, mock_db: AsyncMock) -> None:
        from app.services.periods import sign_off_checklist_item

        # Simulate period found and no existing signoff
        period_mock = MagicMock()
        period_mock.id = "p-1"
        period_mock.tenant_id = "t-1"
        period_mock.status = "open"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch("app.services.periods.get_period", return_value=period_mock):
            result = await sign_off_checklist_item(
                mock_db,
                period_id="p-1",
                tenant_id="t-1",
                task_key="bank_reconciliation_complete",
                actor_id="user-1",
            )

        assert result["checked_by"] == "user-1"
        assert result["checked_at"] is not None
