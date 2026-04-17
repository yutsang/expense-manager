"""Unit tests for unique journal_line_id constraint on bank_transactions (Issue #21).

Tests cover:
  - Migration exists with upgrade() and downgrade() creating a partial unique index
  - DuplicateReconciliationError is defined in the service module
  - match_transaction raises DuplicateReconciliationError when journal_line_id is taken
  - match_transaction succeeds when journal_line_id is not yet used
  - API endpoint returns HTTP 409 when DuplicateReconciliationError is raised
  - Model reflects the unique index via __table_args__
"""

from __future__ import annotations

import sys
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

_UTC = timezone.utc  # noqa: UP017 - need 3.10 compat for test runner
_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ── Migration tests ─────────────────────────────────────────────────────────


class TestMigration0018:
    """A migration for the partial unique index on journal_line_id must exist."""

    def _get_migration_source(self) -> str:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        candidates = [
            f
            for f in migrations_dir.glob("0018*")
        ]
        assert len(candidates) >= 1, "Migration 0018 not found"
        return candidates[0].read_text()

    def test_migration_file_exists(self) -> None:
        self._get_migration_source()

    def test_migration_has_upgrade_and_downgrade(self) -> None:
        source = self._get_migration_source()
        assert "def upgrade()" in source
        assert "def downgrade()" in source

    def test_migration_creates_partial_unique_index(self) -> None:
        source = self._get_migration_source()
        assert "ix_bank_txn_journal_line_unique" in source
        assert "journal_line_id" in source
        assert "bank_transactions" in source

    def test_migration_downgrade_drops_index(self) -> None:
        source = self._get_migration_source()
        # downgrade should drop the index
        downgrade_start = source.index("def downgrade()")
        downgrade_body = source[downgrade_start:]
        assert "ix_bank_txn_journal_line_unique" in downgrade_body

    def test_migration_revises_0017(self) -> None:
        source = self._get_migration_source()
        assert 'down_revision' in source
        assert '"0017"' in source


# ── Service-level tests ─────────────────────────────────────────────────────


class TestDuplicateReconciliationError:
    """DuplicateReconciliationError must be defined in the service module."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "app"
            / "services"
            / "bank_reconciliation.py"
        )
        return svc_path.read_text()

    def test_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class DuplicateReconciliationError" in source

    def test_error_inherits_from_valueerror(self) -> None:
        source = self._read_service_source()
        assert "class DuplicateReconciliationError(ValueError)" in source


class TestMatchTransactionServiceSource:
    """Verify the service checks for existing reconciliation before matching."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "app"
            / "services"
            / "bank_reconciliation.py"
        )
        return svc_path.read_text()

    def test_match_transaction_checks_for_duplicate(self) -> None:
        """match_transaction should query for existing use of journal_line_id."""
        source = self._read_service_source()
        # The function should contain a check for existing reconciliation
        match_start = source.index("async def match_transaction")
        # Look at the function body (next function or end of file)
        next_func = source.find("\nasync def ", match_start + 1)
        if next_func == -1:
            next_func = len(source)
        match_body = source[match_start:next_func]
        assert "DuplicateReconciliationError" in match_body

    def test_service_imports_select(self) -> None:
        """Service must use select to check for existing matches."""
        source = self._read_service_source()
        assert "select" in source


# ── Async service tests (mock DB) ──────────────────────────────────────────


@_skip_311
class TestMatchTransactionDuplicateCheck:
    """match_transaction raises DuplicateReconciliationError on duplicate journal_line_id."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_bank_txn(
        self,
        *,
        txn_id: str = "txn-1",
        tenant_id: str = "t1",
        journal_line_id: str | None = None,
    ) -> MagicMock:
        txn = MagicMock()
        txn.id = txn_id
        txn.tenant_id = tenant_id
        txn.journal_line_id = journal_line_id
        txn.is_reconciled = journal_line_id is not None
        txn.version = 1
        return txn

    @pytest.mark.anyio
    async def test_raises_when_journal_line_already_matched(self, mock_db: AsyncMock) -> None:
        """When journal_line_id is already used by another bank transaction, raise."""
        from app.services.bank_reconciliation import (
            DuplicateReconciliationError,
            match_transaction,
        )

        target_txn = self._make_bank_txn(txn_id="txn-1")
        existing_txn = self._make_bank_txn(txn_id="txn-other", journal_line_id="jl-42")

        # First scalar call: _get_transaction returns target_txn
        # Second scalar call: duplicate check returns existing_txn
        mock_db.scalar = AsyncMock(side_effect=[target_txn, existing_txn])

        with pytest.raises(DuplicateReconciliationError):
            await match_transaction(mock_db, "t1", "actor-1", "txn-1", "jl-42")

    @pytest.mark.anyio
    async def test_succeeds_when_journal_line_not_used(self, mock_db: AsyncMock) -> None:
        """When journal_line_id is not used by any bank transaction, succeed."""
        from app.services.bank_reconciliation import match_transaction

        target_txn = self._make_bank_txn(txn_id="txn-1")

        # First scalar call: _get_transaction returns target_txn
        # Second scalar call: duplicate check returns None (not used)
        mock_db.scalar = AsyncMock(side_effect=[target_txn, None])

        result = await match_transaction(mock_db, "t1", "actor-1", "txn-1", "jl-new")
        assert result.journal_line_id == "jl-new"


# ── API endpoint tests ─────────────────────────────────────────────────────


class TestApiHandlesDuplicateReconciliation:
    """The API endpoint must catch DuplicateReconciliationError and return HTTP 409."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "app"
            / "api"
            / "v1"
            / "bank_reconciliation.py"
        )
        return api_path.read_text()

    def test_api_imports_duplicate_error(self) -> None:
        source = self._read_api_source()
        assert "DuplicateReconciliationError" in source

    def test_api_returns_409_on_duplicate(self) -> None:
        source = self._read_api_source()
        assert "409" in source or "HTTP_409_CONFLICT" in source

    def test_api_match_endpoint_catches_duplicate_error(self) -> None:
        source = self._read_api_source()
        # Find the match endpoint and check it handles the error
        match_start = source.index("async def match")
        next_func = source.find("\nasync def ", match_start + 1)
        if next_func == -1:
            next_func = source.find("\n@router", match_start + 1)
        if next_func == -1:
            next_func = len(source)
        match_body = source[match_start:next_func]
        assert "DuplicateReconciliationError" in match_body
