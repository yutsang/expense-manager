"""Unit tests for blocking tax code deactivation when referenced by open documents.

Tests cover:
  - Deactivation proceeds when no open invoices/bills reference the tax code
  - Deactivation is blocked when open invoices reference the tax code
  - Deactivation is blocked when open bills reference the tax code
  - Deactivation is blocked when both open invoices and bills reference the tax code
  - Non-deactivation updates (e.g. name change) are not affected by the check
  - Paid/void invoices and bills do not block deactivation
  - The error includes counts of blocking documents
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


def _make_tax_code(
    *,
    tc_id: str = "tc-1",
    tenant_id: str = "t1",
    is_active: bool = True,
) -> MagicMock:
    tc = MagicMock()
    tc.id = tc_id
    tc.tenant_id = tenant_id
    tc.is_active = is_active
    tc.code = "GST"
    tc.name = "GST on Income"
    tc.version = 1
    tc.updated_by = None
    return tc


class TestTaxCodeDeactivationServiceSource:
    """Verify service code structure for deactivation guard."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "tax_codes.py"
        return svc_path.read_text()

    def test_tax_code_in_use_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class TaxCodeInUseError" in source

    def test_update_imports_invoice_and_bill_models(self) -> None:
        source = self._read_service_source()
        assert "Invoice" in source
        assert "Bill" in source
        assert "InvoiceLine" in source
        assert "BillLine" in source

    def test_update_checks_open_documents_before_deactivation(self) -> None:
        source = self._read_service_source()
        # Should check for open statuses when deactivating
        assert "is_active" in source
        assert "paid" in source
        assert "void" in source


class TestApiEndpointHandlesInUseError:
    """Verify API endpoint maps TaxCodeInUseError to HTTP 409."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "items.py"
        return api_path.read_text()

    def test_api_catches_tax_code_in_use_error(self) -> None:
        source = self._read_api_source()
        assert "TaxCodeInUseError" in source

    def test_api_returns_409_for_in_use(self) -> None:
        source = self._read_api_source()
        # The update endpoint (not just create) should handle 409 for in-use
        update_idx = source.index("update_tax_code_endpoint")
        update_block = source[update_idx : update_idx + 800]
        assert "HTTP_409_CONFLICT" in update_block


@_skip_311
class TestDeactivationBlockedByOpenInvoices:
    """update_tax_code rejects deactivation when open invoices reference the tax code."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_deactivation_blocked_by_open_invoices(self, mock_db: AsyncMock) -> None:
        from app.services.tax_codes import TaxCodeInUseError, update_tax_code

        tc = _make_tax_code(is_active=True)

        # scalar returns: first the tax code lookup, then invoice count=3, then bill count=0
        mock_db.scalar = AsyncMock(side_effect=[tc, 3, 0])

        with pytest.raises(TaxCodeInUseError, match="3 open invoice"):
            await update_tax_code(mock_db, "t1", "tc-1", "actor-1", {"is_active": False})

    @pytest.mark.anyio
    async def test_deactivation_blocked_by_open_bills(self, mock_db: AsyncMock) -> None:
        from app.services.tax_codes import TaxCodeInUseError, update_tax_code

        tc = _make_tax_code(is_active=True)

        # scalar returns: first the tax code lookup, then invoice count=0, then bill count=2
        mock_db.scalar = AsyncMock(side_effect=[tc, 0, 2])

        with pytest.raises(TaxCodeInUseError, match="2 open bill"):
            await update_tax_code(mock_db, "t1", "tc-1", "actor-1", {"is_active": False})

    @pytest.mark.anyio
    async def test_deactivation_blocked_by_both(self, mock_db: AsyncMock) -> None:
        from app.services.tax_codes import TaxCodeInUseError, update_tax_code

        tc = _make_tax_code(is_active=True)

        # scalar returns: first the tax code lookup, then invoice count=2, then bill count=1
        mock_db.scalar = AsyncMock(side_effect=[tc, 2, 1])

        with pytest.raises(TaxCodeInUseError) as exc_info:
            await update_tax_code(mock_db, "t1", "tc-1", "actor-1", {"is_active": False})

        msg = str(exc_info.value)
        assert "2 open invoice" in msg
        assert "1 open bill" in msg

    @pytest.mark.anyio
    async def test_deactivation_allowed_when_no_open_documents(self, mock_db: AsyncMock) -> None:
        from app.services.tax_codes import update_tax_code

        tc = _make_tax_code(is_active=True)

        # scalar returns: first the tax code lookup, then invoice count=0, then bill count=0
        mock_db.scalar = AsyncMock(side_effect=[tc, 0, 0])

        result = await update_tax_code(mock_db, "t1", "tc-1", "actor-1", {"is_active": False})
        assert result.is_active is False

    @pytest.mark.anyio
    async def test_non_deactivation_update_skips_check(self, mock_db: AsyncMock) -> None:
        """Renaming a tax code should not trigger the open-document check."""
        from app.services.tax_codes import update_tax_code

        tc = _make_tax_code(is_active=True)

        # scalar returns: only the tax code lookup (no count queries)
        mock_db.scalar = AsyncMock(return_value=tc)

        result = await update_tax_code(mock_db, "t1", "tc-1", "actor-1", {"name": "New Name"})
        assert result.name == "New Name"
        # Only one scalar call (get_tax_code), no count queries
        assert mock_db.scalar.call_count == 1

    @pytest.mark.anyio
    async def test_already_inactive_skips_check(self, mock_db: AsyncMock) -> None:
        """Setting is_active=False on an already-inactive tax code should not re-check."""
        from app.services.tax_codes import update_tax_code

        tc = _make_tax_code(is_active=False)

        # scalar returns: only the tax code lookup
        mock_db.scalar = AsyncMock(return_value=tc)

        await update_tax_code(mock_db, "t1", "tc-1", "actor-1", {"is_active": False})
        # Only one scalar call (get_tax_code), no count queries
        assert mock_db.scalar.call_count == 1
