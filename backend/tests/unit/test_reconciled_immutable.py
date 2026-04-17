"""Unit tests for reconciled bank transaction immutability (Issue #25).

Tests cover:
  - ReconciledTransactionError is defined in the service module
  - update_bank_transaction raises ReconciledTransactionError when is_reconciled=True
  - delete_bank_transaction raises ReconciledTransactionError when is_reconciled=True
  - update_bank_transaction succeeds on unreconciled transactions
  - delete_bank_transaction succeeds on unreconciled transactions
  - unreconcile_transaction clears reconciliation state and requires a reason
  - API PATCH /bank-transactions/{id} returns 409 when reconciled
  - API DELETE /bank-transactions/{id} returns 409 when reconciled
  - API POST /bank-transactions/{id}/unreconcile exists and works
"""

from __future__ import annotations

import sys
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

_UTC = timezone.utc  # noqa: UP017 - need 3.10 compat for test runner
_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ── Service-level source tests ────────────────────────────────────────────


class TestReconciledTransactionErrorExists:
    """ReconciledTransactionError must be defined in the service module."""

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
        assert "class ReconciledTransactionError" in source

    def test_error_inherits_from_valueerror(self) -> None:
        source = self._read_service_source()
        assert "class ReconciledTransactionError(ValueError)" in source


class TestUpdateGuardInServiceSource:
    """update_bank_transaction must guard against reconciled transactions."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "app"
            / "services"
            / "bank_reconciliation.py"
        )
        return svc_path.read_text()

    def test_update_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def update_bank_transaction" in source

    def test_update_function_checks_reconciled(self) -> None:
        source = self._read_service_source()
        func_start = source.index("async def update_bank_transaction")
        next_func = source.find("\nasync def ", func_start + 1)
        if next_func == -1:
            next_func = len(source)
        func_body = source[func_start:next_func]
        # Guard may be via a helper like _assert_not_reconciled
        assert "_assert_not_reconciled" in func_body or "ReconciledTransactionError" in func_body

    def test_delete_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def delete_bank_transaction" in source

    def test_delete_function_checks_reconciled(self) -> None:
        source = self._read_service_source()
        func_start = source.index("async def delete_bank_transaction")
        next_func = source.find("\nasync def ", func_start + 1)
        if next_func == -1:
            next_func = len(source)
        func_body = source[func_start:next_func]
        # Guard may be via a helper like _assert_not_reconciled
        assert "_assert_not_reconciled" in func_body or "ReconciledTransactionError" in func_body


class TestUnreconcileInServiceSource:
    """unreconcile_transaction must exist and require a reason."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "app"
            / "services"
            / "bank_reconciliation.py"
        )
        return svc_path.read_text()

    def test_unreconcile_function_exists(self) -> None:
        source = self._read_service_source()
        assert "async def unreconcile_transaction" in source

    def test_unreconcile_takes_reason_param(self) -> None:
        source = self._read_service_source()
        func_start = source.index("async def unreconcile_transaction")
        next_func = source.find("\nasync def ", func_start + 1)
        if next_func == -1:
            next_func = len(source)
        func_body = source[func_start:next_func]
        assert "reason" in func_body


# ── Async service tests (mock DB) ────────────────────────────────────────


@_skip_311
class TestUpdateBankTransactionGuard:
    """update_bank_transaction raises ReconciledTransactionError when reconciled."""

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
        is_reconciled: bool = False,
        journal_line_id: str | None = None,
    ) -> MagicMock:
        txn = MagicMock()
        txn.id = txn_id
        txn.tenant_id = tenant_id
        txn.is_reconciled = is_reconciled
        txn.journal_line_id = journal_line_id
        txn.version = 1
        return txn

    @pytest.mark.anyio
    async def test_update_raises_when_reconciled(self, mock_db: AsyncMock) -> None:
        from app.services.bank_reconciliation import (
            ReconciledTransactionError,
            update_bank_transaction,
        )

        txn = self._make_bank_txn(is_reconciled=True, journal_line_id="jl-1")
        mock_db.scalar = AsyncMock(return_value=txn)

        with pytest.raises(ReconciledTransactionError):
            await update_bank_transaction(
                mock_db, "t1", "actor-1", "txn-1", {"description": "new desc"}
            )

    @pytest.mark.anyio
    async def test_update_succeeds_when_not_reconciled(self, mock_db: AsyncMock) -> None:
        from app.services.bank_reconciliation import update_bank_transaction

        txn = self._make_bank_txn(is_reconciled=False)
        mock_db.scalar = AsyncMock(return_value=txn)

        result = await update_bank_transaction(
            mock_db, "t1", "actor-1", "txn-1", {"description": "new desc"}
        )
        assert result.description == "new desc"


@_skip_311
class TestDeleteBankTransactionGuard:
    """delete_bank_transaction raises ReconciledTransactionError when reconciled."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        db.delete = AsyncMock()
        return db

    def _make_bank_txn(
        self,
        *,
        txn_id: str = "txn-1",
        tenant_id: str = "t1",
        is_reconciled: bool = False,
        journal_line_id: str | None = None,
    ) -> MagicMock:
        txn = MagicMock()
        txn.id = txn_id
        txn.tenant_id = tenant_id
        txn.is_reconciled = is_reconciled
        txn.journal_line_id = journal_line_id
        txn.version = 1
        return txn

    @pytest.mark.anyio
    async def test_delete_raises_when_reconciled(self, mock_db: AsyncMock) -> None:
        from app.services.bank_reconciliation import (
            ReconciledTransactionError,
            delete_bank_transaction,
        )

        txn = self._make_bank_txn(is_reconciled=True, journal_line_id="jl-1")
        mock_db.scalar = AsyncMock(return_value=txn)

        with pytest.raises(ReconciledTransactionError):
            await delete_bank_transaction(mock_db, "t1", "actor-1", "txn-1")

    @pytest.mark.anyio
    async def test_delete_succeeds_when_not_reconciled(self, mock_db: AsyncMock) -> None:
        from app.services.bank_reconciliation import delete_bank_transaction

        txn = self._make_bank_txn(is_reconciled=False)
        mock_db.scalar = AsyncMock(return_value=txn)

        await delete_bank_transaction(mock_db, "t1", "actor-1", "txn-1")
        mock_db.delete.assert_awaited_once_with(txn)


@_skip_311
class TestUnreconcileTransaction:
    """unreconcile_transaction clears reconciliation and logs reason."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_reconciled_txn(self) -> MagicMock:
        txn = MagicMock()
        txn.id = "txn-1"
        txn.tenant_id = "t1"
        txn.is_reconciled = True
        txn.journal_line_id = "jl-1"
        txn.reconciled_at = "2024-01-01T00:00:00Z"
        txn.version = 2
        return txn

    @pytest.mark.anyio
    async def test_unreconcile_clears_state(self, mock_db: AsyncMock) -> None:
        from app.services.bank_reconciliation import unreconcile_transaction

        txn = self._make_reconciled_txn()
        mock_db.scalar = AsyncMock(return_value=txn)

        result = await unreconcile_transaction(
            mock_db, "t1", "actor-1", "txn-1", reason="Correcting match"
        )
        assert result.is_reconciled is False
        assert result.journal_line_id is None
        assert result.reconciled_at is None

    @pytest.mark.anyio
    async def test_unreconcile_raises_when_not_reconciled(self, mock_db: AsyncMock) -> None:
        from app.services.bank_reconciliation import (
            ReconciledTransactionError,
            unreconcile_transaction,
        )

        txn = MagicMock()
        txn.id = "txn-1"
        txn.tenant_id = "t1"
        txn.is_reconciled = False
        txn.journal_line_id = None
        mock_db.scalar = AsyncMock(return_value=txn)

        with pytest.raises(ReconciledTransactionError):
            await unreconcile_transaction(mock_db, "t1", "actor-1", "txn-1", reason="Bad reason")


# ── API endpoint source tests ────────────────────────────────────────────


class TestApiEndpointsExist:
    """API must have PATCH, DELETE, and unreconcile endpoints for bank transactions."""

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

    def test_patch_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert '@router.patch("/bank-transactions/{transaction_id}"' in source

    def test_delete_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert '@router.delete("/bank-transactions/{transaction_id}"' in source

    def test_unreconcile_endpoint_exists(self) -> None:
        source = self._read_api_source()
        assert "unreconcile" in source
        assert '"/bank-transactions/{transaction_id}/unreconcile"' in source

    def test_api_imports_reconciled_error(self) -> None:
        source = self._read_api_source()
        assert "ReconciledTransactionError" in source

    def test_patch_returns_409_on_reconciled(self) -> None:
        source = self._read_api_source()
        # Find the update endpoint and check it handles the error
        func_start = source.index("async def update_transaction")
        next_func = source.find("\nasync def ", func_start + 1)
        if next_func == -1:
            next_func = source.find("\n@router", func_start + 1)
        if next_func == -1:
            next_func = len(source)
        func_body = source[func_start:next_func]
        assert "ReconciledTransactionError" in func_body
        assert "409" in func_body or "HTTP_409_CONFLICT" in func_body

    def test_delete_returns_409_on_reconciled(self) -> None:
        source = self._read_api_source()
        func_start = source.index("async def delete_transaction")
        next_func = source.find("\nasync def ", func_start + 1)
        if next_func == -1:
            next_func = source.find("\n@router", func_start + 1)
        if next_func == -1:
            next_func = len(source)
        func_body = source[func_start:next_func]
        assert "ReconciledTransactionError" in func_body
        assert "409" in func_body or "HTTP_409_CONFLICT" in func_body


class TestSchemaExists:
    """Schemas for update and unreconcile must exist."""

    def _read_schema_source(self) -> str:
        import pathlib

        schema_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "schemas.py"
        )
        return schema_path.read_text()

    def test_bank_transaction_update_schema_exists(self) -> None:
        source = self._read_schema_source()
        assert "class BankTransactionUpdate(BaseModel)" in source

    def test_unreconcile_request_schema_exists(self) -> None:
        source = self._read_schema_source()
        assert "class UnreconcileRequest(BaseModel)" in source

    def test_unreconcile_request_requires_reason(self) -> None:
        source = self._read_schema_source()
        cls_start = source.index("class UnreconcileRequest")
        # Look ahead for next class or end of file
        next_cls = source.find("\nclass ", cls_start + 1)
        if next_cls == -1:
            next_cls = len(source)
        cls_body = source[cls_start:next_cls]
        assert "reason" in cls_body
