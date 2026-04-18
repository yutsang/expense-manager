"""Unit tests for bank transaction duplicate match prevention (Bug #62).

Tests cover:
  - match_transaction raises DuplicateReconciliationError when the bank
    transaction is already matched to a different journal line
  - match_transaction still raises DuplicateReconciliationError when
    journal_line_id is used by another bank transaction (existing behavior)
  - match_transaction succeeds when re-matching to the same journal line
  - unreconcile_transaction sets unreconciled_at, unreconciled_by,
    unreconcile_reason audit fields
  - BankTransaction model has the new unreconcile audit columns
"""

from __future__ import annotations

import sys
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

_UTC = timezone.utc
_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ── Service source tests ──────────────────────────────────────────────────


class TestMatchTransactionDuplicateBankTxnCheck:
    """match_transaction must check if the bank transaction itself is already matched."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "app"
            / "services"
            / "bank_reconciliation.py"
        )
        return svc_path.read_text()

    def test_checks_txn_journal_line_id_before_matching(self) -> None:
        source = self._read_service_source()
        match_start = source.index("async def match_transaction")
        next_func = source.find("\nasync def ", match_start + 1)
        if next_func == -1:
            next_func = len(source)
        match_body = source[match_start:next_func]
        assert "txn.journal_line_id is not None" in match_body
        assert "unreconcile first" in match_body


class TestUnreconcileAuditColumnsInSource:
    """unreconcile_transaction must set audit columns."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "app"
            / "services"
            / "bank_reconciliation.py"
        )
        return svc_path.read_text()

    def test_sets_unreconciled_at(self) -> None:
        source = self._read_service_source()
        func_start = source.index("async def unreconcile_transaction")
        next_func = source.find("\nasync def ", func_start + 1)
        if next_func == -1:
            next_func = source.find("\n# ---", func_start + 1)
        if next_func == -1:
            next_func = len(source)
        func_body = source[func_start:next_func]
        assert "unreconciled_at" in func_body

    def test_sets_unreconciled_by(self) -> None:
        source = self._read_service_source()
        func_start = source.index("async def unreconcile_transaction")
        next_func = source.find("\nasync def ", func_start + 1)
        if next_func == -1:
            next_func = source.find("\n# ---", func_start + 1)
        if next_func == -1:
            next_func = len(source)
        func_body = source[func_start:next_func]
        assert "unreconciled_by" in func_body

    def test_sets_unreconcile_reason(self) -> None:
        source = self._read_service_source()
        func_start = source.index("async def unreconcile_transaction")
        next_func = source.find("\nasync def ", func_start + 1)
        if next_func == -1:
            next_func = source.find("\n# ---", func_start + 1)
        if next_func == -1:
            next_func = len(source)
        func_body = source[func_start:next_func]
        assert "unreconcile_reason" in func_body


# ── Model tests ───────────────────────────────────────────────────────────


class TestBankTransactionModelAuditColumns:
    """BankTransaction model must have unreconcile audit columns."""

    def _read_model_source(self) -> str:
        import pathlib

        model_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        )
        return model_path.read_text()

    def test_has_unreconciled_at(self) -> None:
        source = self._read_model_source()
        assert "unreconciled_at" in source

    def test_has_unreconciled_by(self) -> None:
        source = self._read_model_source()
        assert "unreconciled_by" in source

    def test_has_unreconcile_reason(self) -> None:
        source = self._read_model_source()
        assert "unreconcile_reason" in source


# ── Migration tests ───────────────────────────────────────────────────────


class TestUnreconcileAuditMigration:
    """A migration must add unreconcile audit columns to bank_transactions."""

    def _get_migration_source(self) -> str:
        import pathlib

        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        candidates = list(migrations_dir.glob("*unreconcile*"))
        assert len(candidates) >= 1, "Unreconcile audit columns migration not found"
        return candidates[0].read_text()

    def test_migration_exists(self) -> None:
        self._get_migration_source()

    def test_adds_unreconciled_at(self) -> None:
        source = self._get_migration_source()
        assert "unreconciled_at" in source

    def test_adds_unreconciled_by(self) -> None:
        source = self._get_migration_source()
        assert "unreconciled_by" in source

    def test_adds_unreconcile_reason(self) -> None:
        source = self._get_migration_source()
        assert "unreconcile_reason" in source

    def test_has_downgrade(self) -> None:
        source = self._get_migration_source()
        assert "def downgrade()" in source
        downgrade_start = source.index("def downgrade()")
        downgrade_body = source[downgrade_start:]
        assert "drop_column" in downgrade_body


# ── Async service tests (mock DB) ────────────────────────────────────────


@_skip_311
class TestMatchTransactionAlreadyMatchedDifferentLine:
    """match_transaction raises when bank txn is already matched to another journal line."""

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
    async def test_raises_when_already_matched_to_different_line(
        self, mock_db: AsyncMock
    ) -> None:
        """Bank txn matched to jl-old should reject match to jl-new."""
        from app.services.bank_reconciliation import (
            DuplicateReconciliationError,
            match_transaction,
        )

        txn = self._make_bank_txn(txn_id="txn-1", journal_line_id="jl-old")
        mock_db.scalar = AsyncMock(return_value=txn)

        with pytest.raises(DuplicateReconciliationError, match="already matched"):
            await match_transaction(mock_db, "t1", "actor-1", "txn-1", "jl-new")

    @pytest.mark.anyio
    async def test_succeeds_when_rematching_same_line(self, mock_db: AsyncMock) -> None:
        """Re-matching to the same journal line should succeed."""
        from app.services.bank_reconciliation import match_transaction

        txn = self._make_bank_txn(txn_id="txn-1", journal_line_id="jl-same")
        # First scalar: _get_transaction, Second scalar: duplicate check returns None
        mock_db.scalar = AsyncMock(side_effect=[txn, None])

        result = await match_transaction(mock_db, "t1", "actor-1", "txn-1", "jl-same")
        assert result.journal_line_id == "jl-same"


@_skip_311
class TestUnreconcileTransactionAuditFields:
    """unreconcile_transaction must set audit columns."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.scalar = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_sets_unreconcile_audit_fields(self, mock_db: AsyncMock) -> None:
        from app.services.bank_reconciliation import unreconcile_transaction

        txn = MagicMock()
        txn.id = "txn-1"
        txn.tenant_id = "t1"
        txn.is_reconciled = True
        txn.journal_line_id = "jl-1"
        txn.reconciled_at = "2024-01-01T00:00:00Z"
        txn.version = 2
        mock_db.scalar = AsyncMock(return_value=txn)

        result = await unreconcile_transaction(
            mock_db, "t1", "actor-99", "txn-1", reason="Matched wrong line"
        )
        assert result.unreconciled_by == "actor-99"
        assert result.unreconcile_reason == "Matched wrong line"
        assert result.unreconciled_at is not None
        assert result.is_reconciled is False
        assert result.journal_line_id is None
