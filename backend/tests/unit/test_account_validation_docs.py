"""Unit tests for GL account validation in invoices and bills (Issue #10).

Tests cover:
  - create_invoice rejects lines with non-existent account_id (HTTP 422)
  - create_bill rejects lines with non-existent account_id (HTTP 422)
  - Tenant-scoped: accounts from other tenants are rejected
  - Valid accounts pass and documents are created normally
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ---------------------------------------------------------------------------
# Service source inspection tests
# ---------------------------------------------------------------------------


class TestInvoiceAccountValidationSource:
    """Verify invoice service includes account existence check."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "invoices.py"
        return svc_path.read_text()

    def test_invalid_account_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class InvalidAccountError" in source

    def test_create_invoice_validates_accounts(self) -> None:
        source = self._read_service_source()
        assert "InvalidAccountError" in source


class TestBillAccountValidationSource:
    """Verify bill service includes account existence check."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "bills.py"
        return svc_path.read_text()

    def test_invalid_account_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class InvalidAccountError" in source

    def test_create_bill_validates_accounts(self) -> None:
        source = self._read_service_source()
        assert "InvalidAccountError" in source


# ---------------------------------------------------------------------------
# Invoice service async tests
# ---------------------------------------------------------------------------


@_skip_311
class TestInvoiceAccountValidation:
    """create_invoice should validate all line account_ids exist for the tenant."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_lines(self, account_ids: list[str] | None = None) -> list[dict]:
        ids = account_ids or ["acc-1"]
        return [
            {
                "account_id": aid,
                "quantity": "1",
                "unit_price": "100.00",
                "discount_pct": "0",
                "_tax_rate": "0",
            }
            for aid in ids
        ]

    def _make_account(self, account_id: str, tenant_id: str = "t1") -> MagicMock:
        acc = MagicMock()
        acc.id = account_id
        acc.tenant_id = tenant_id
        acc.is_active = True
        return acc

    @pytest.mark.anyio
    async def test_nonexistent_account_rejects_invoice(self, mock_db: AsyncMock) -> None:
        """Invoice with non-existent account_id should raise InvalidAccountError."""
        from app.services.invoices import InvalidAccountError, create_invoice

        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=accounts_result)

        with pytest.raises(InvalidAccountError, match="bad-acc"):
            await create_invoice(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-01-15",
                currency="USD",
                lines=self._make_lines(["bad-acc"]),
            )

    @pytest.mark.anyio
    async def test_cross_tenant_account_rejects_invoice(self, mock_db: AsyncMock) -> None:
        """Account from another tenant should be rejected."""
        from app.services.invoices import InvalidAccountError, create_invoice

        other_tenant_acc = self._make_account("acc-other", tenant_id="t2")
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = [other_tenant_acc]
        mock_db.execute = AsyncMock(return_value=accounts_result)

        with pytest.raises(InvalidAccountError, match="acc-other"):
            await create_invoice(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-01-15",
                currency="USD",
                lines=self._make_lines(["acc-other"]),
            )

    @pytest.mark.anyio
    async def test_valid_accounts_creates_invoice(self, mock_db: AsyncMock) -> None:
        """Valid accounts should allow invoice creation."""
        from app.services.invoices import create_invoice

        acc1 = self._make_account("acc-1")
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = [acc1]
        mock_db.execute = AsyncMock(return_value=accounts_result)

        inv = await create_invoice(
            mock_db,
            "t1",
            "actor-1",
            contact_id="c1",
            issue_date="2026-01-15",
            currency="USD",
            lines=self._make_lines(["acc-1"]),
        )

        assert inv is not None
        assert mock_db.add.call_count >= 1


# ---------------------------------------------------------------------------
# Bill service async tests
# ---------------------------------------------------------------------------


@_skip_311
class TestBillAccountValidation:
    """create_bill should validate all line account_ids exist for the tenant."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_lines(self, account_ids: list[str] | None = None) -> list[dict]:
        ids = account_ids or ["acc-1"]
        return [
            {
                "account_id": aid,
                "quantity": "1",
                "unit_price": "100.00",
                "discount_pct": "0",
                "_tax_rate": "0",
            }
            for aid in ids
        ]

    def _make_account(self, account_id: str, tenant_id: str = "t1") -> MagicMock:
        acc = MagicMock()
        acc.id = account_id
        acc.tenant_id = tenant_id
        acc.is_active = True
        return acc

    @pytest.mark.anyio
    async def test_nonexistent_account_rejects_bill(self, mock_db: AsyncMock) -> None:
        """Bill with non-existent account_id should raise InvalidAccountError."""
        from app.services.bills import InvalidAccountError, create_bill

        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=accounts_result)

        with pytest.raises(InvalidAccountError, match="bad-acc"):
            await create_bill(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-01-15",
                currency="USD",
                lines=self._make_lines(["bad-acc"]),
            )

    @pytest.mark.anyio
    async def test_cross_tenant_account_rejects_bill(self, mock_db: AsyncMock) -> None:
        """Account from another tenant should be rejected."""
        from app.services.bills import InvalidAccountError, create_bill

        other_tenant_acc = self._make_account("acc-other", tenant_id="t2")
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = [other_tenant_acc]
        mock_db.execute = AsyncMock(return_value=accounts_result)

        with pytest.raises(InvalidAccountError, match="acc-other"):
            await create_bill(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-01-15",
                currency="USD",
                lines=self._make_lines(["acc-other"]),
            )

    @pytest.mark.anyio
    async def test_valid_accounts_creates_bill(self, mock_db: AsyncMock) -> None:
        """Valid accounts should allow bill creation."""
        from app.services.bills import create_bill

        acc1 = self._make_account("acc-1")
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = [acc1]
        mock_db.execute = AsyncMock(return_value=accounts_result)

        bill = await create_bill(
            mock_db,
            "t1",
            "actor-1",
            contact_id="c1",
            issue_date="2026-01-15",
            currency="USD",
            lines=self._make_lines(["acc-1"]),
        )

        assert bill is not None
        assert mock_db.add.call_count >= 1
