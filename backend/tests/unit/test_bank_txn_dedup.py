"""Unit tests for bank transaction deduplication key (Bug #55).

Tests cover:
  - BankTransaction model has the dedup UniqueConstraint
  - Migration 0037 exists and adds the constraint
  - Bank import service catches IntegrityError on duplicate and counts as skipped
"""

from __future__ import annotations

import pathlib

_MODELS_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
_MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
_BANK_IMPORT_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "bank_import.py"
)


class TestBankTransactionDedupConstraint:
    """BankTransaction model must have a dedup unique constraint."""

    def _get_bank_txn_class(self) -> str:
        source = _MODELS_PATH.read_text()
        start = source.index("class BankTransaction(Base)")
        next_class = source.find("\nclass ", start + 1)
        if next_class == -1:
            next_class = len(source)
        return source[start:next_class]

    def test_has_dedup_constraint(self) -> None:
        cls_body = self._get_bank_txn_class()
        assert "uq_bank_txn_dedup" in cls_body

    def test_constraint_includes_bank_account_id(self) -> None:
        cls_body = self._get_bank_txn_class()
        constraint_start = cls_body.index("uq_bank_txn_dedup")
        constraint_section = cls_body[max(0, constraint_start - 200):constraint_start + 50]
        assert "bank_account_id" in constraint_section

    def test_constraint_includes_transaction_date(self) -> None:
        cls_body = self._get_bank_txn_class()
        constraint_start = cls_body.index("uq_bank_txn_dedup")
        constraint_section = cls_body[max(0, constraint_start - 200):constraint_start + 50]
        assert "transaction_date" in constraint_section

    def test_constraint_includes_amount(self) -> None:
        cls_body = self._get_bank_txn_class()
        constraint_start = cls_body.index("uq_bank_txn_dedup")
        constraint_section = cls_body[max(0, constraint_start - 200):constraint_start + 50]
        assert "amount" in constraint_section

    def test_constraint_includes_reference(self) -> None:
        cls_body = self._get_bank_txn_class()
        constraint_start = cls_body.index("uq_bank_txn_dedup")
        constraint_section = cls_body[max(0, constraint_start - 200):constraint_start + 50]
        assert "reference" in constraint_section


class TestBankTxnDedupMigration:
    """A migration must add the dedup constraint to bank_transactions."""

    def _get_migration_source(self) -> str:
        candidates = list(_MIGRATIONS_DIR.glob("*bank_txn_dedup*"))
        assert len(candidates) >= 1, "Bank txn dedup migration not found"
        return candidates[0].read_text()

    def test_migration_exists(self) -> None:
        self._get_migration_source()

    def test_creates_dedup_constraint(self) -> None:
        source = self._get_migration_source()
        assert "uq_bank_txn_dedup" in source

    def test_has_downgrade(self) -> None:
        source = self._get_migration_source()
        assert "def downgrade()" in source
        downgrade_start = source.index("def downgrade()")
        downgrade_body = source[downgrade_start:]
        assert "uq_bank_txn_dedup" in downgrade_body

    def test_migration_has_down_revision(self) -> None:
        source = self._get_migration_source()
        assert "down_revision" in source


class TestBankImportCatchesIntegrityError:
    """Bank import service must catch IntegrityError and count duplicates as skipped."""

    def _get_source(self) -> str:
        return _BANK_IMPORT_PATH.read_text()

    def test_imports_integrity_error(self) -> None:
        source = self._get_source()
        assert "IntegrityError" in source

    def test_catches_integrity_error_in_import_loop(self) -> None:
        source = self._get_source()
        func_start = source.index("async def import_csv")
        func_body = source[func_start:]
        assert "except IntegrityError" in func_body

    def test_increments_skipped_on_integrity_error(self) -> None:
        source = self._get_source()
        func_start = source.index("async def import_csv")
        func_body = source[func_start:]
        # Find the IntegrityError handler
        handler_start = func_body.index("except IntegrityError")
        handler_section = func_body[handler_start:handler_start + 200]
        assert "skipped_duplicates" in handler_section
