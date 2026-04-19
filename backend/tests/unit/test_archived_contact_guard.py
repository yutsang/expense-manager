"""Unit tests for archived contact guard on invoices and bills (Issue #12).

Tests cover:
  - create_invoice rejects when contact is archived (HTTP 422)
  - create_bill rejects when contact is archived (HTTP 422)
  - Active contacts pass and documents are created normally
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Service source inspection tests
# ---------------------------------------------------------------------------


class TestInvoiceArchivedContactGuardSource:
    """Verify invoice service checks is_archived."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "invoices.py"
        return svc_path.read_text()

    def test_archived_contact_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class ArchivedContactError" in source

    def test_create_invoice_checks_archived(self) -> None:
        source = self._read_service_source()
        assert "ArchivedContactError" in source
        assert "is_archived" in source


class TestBillArchivedContactGuardSource:
    """Verify bill service checks is_archived."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "bills.py"
        return svc_path.read_text()

    def test_archived_contact_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class ArchivedContactError" in source

    def test_create_bill_checks_archived(self) -> None:
        source = self._read_service_source()
        assert "ArchivedContactError" in source
        assert "is_archived" in source


# ---------------------------------------------------------------------------
# Invoice service async tests
# ---------------------------------------------------------------------------


class TestInvoiceArchivedContactGuard:
    """create_invoice should reject archived contacts."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_lines(self) -> list[dict]:
        return [
            {
                "account_id": "acc-1",
                "quantity": "1",
                "unit_price": "100.00",
                "discount_pct": "0",
                "_tax_rate": "0",
            }
        ]

    def _make_account(self, account_id: str = "acc-1") -> MagicMock:
        acc = MagicMock()
        acc.id = account_id
        acc.tenant_id = "t1"
        acc.is_active = True
        return acc

    def _make_contact(self, *, is_archived: bool = False) -> MagicMock:
        contact = MagicMock()
        contact.id = "c1"
        contact.tenant_id = "t1"
        contact.is_archived = is_archived
        return contact

    @pytest.mark.anyio
    async def test_archived_contact_rejects_invoice(self, mock_db: AsyncMock) -> None:
        """Invoice against archived contact should raise ArchivedContactError."""
        from app.services.invoices import ArchivedContactError, create_invoice

        archived = self._make_contact(is_archived=True)
        acc = self._make_account()
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = [acc]

        mock_db.scalar = AsyncMock(return_value=archived)
        mock_db.execute = AsyncMock(return_value=accounts_result)

        with pytest.raises(ArchivedContactError, match="archived"):
            await create_invoice(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-01-15",
                currency="USD",
                lines=self._make_lines(),
            )

    @pytest.mark.anyio
    async def test_active_contact_allows_invoice(self, mock_db: AsyncMock) -> None:
        """Active contact should allow invoice creation."""
        from app.services.invoices import create_invoice

        active = self._make_contact(is_archived=False)
        acc = self._make_account()
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = [acc]

        mock_db.scalar = AsyncMock(return_value=active)
        mock_db.execute = AsyncMock(return_value=accounts_result)

        inv = await create_invoice(
            mock_db,
            "t1",
            "actor-1",
            contact_id="c1",
            issue_date="2026-01-15",
            currency="USD",
            lines=self._make_lines(),
        )

        assert inv is not None


# ---------------------------------------------------------------------------
# Bill service async tests
# ---------------------------------------------------------------------------


class TestBillArchivedContactGuard:
    """create_bill should reject archived contacts."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_lines(self) -> list[dict]:
        return [
            {
                "account_id": "acc-1",
                "quantity": "1",
                "unit_price": "100.00",
                "discount_pct": "0",
                "_tax_rate": "0",
            }
        ]

    def _make_account(self, account_id: str = "acc-1") -> MagicMock:
        acc = MagicMock()
        acc.id = account_id
        acc.tenant_id = "t1"
        acc.is_active = True
        return acc

    def _make_contact(self, *, is_archived: bool = False) -> MagicMock:
        contact = MagicMock()
        contact.id = "c1"
        contact.tenant_id = "t1"
        contact.is_archived = is_archived
        return contact

    @pytest.mark.anyio
    async def test_archived_contact_rejects_bill(self, mock_db: AsyncMock) -> None:
        """Bill against archived contact should raise ArchivedContactError."""
        from app.services.bills import ArchivedContactError, create_bill

        archived = self._make_contact(is_archived=True)
        acc = self._make_account()
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = [acc]

        mock_db.scalar = AsyncMock(return_value=archived)
        mock_db.execute = AsyncMock(return_value=accounts_result)

        with pytest.raises(ArchivedContactError, match="archived"):
            await create_bill(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-01-15",
                currency="USD",
                lines=self._make_lines(),
            )

    @pytest.mark.anyio
    async def test_active_contact_allows_bill(self, mock_db: AsyncMock) -> None:
        """Active contact should allow bill creation."""
        from app.services.bills import create_bill

        active = self._make_contact(is_archived=False)
        acc = self._make_account()
        accounts_result = MagicMock()
        accounts_result.scalars.return_value.all.return_value = [acc]

        tenant_mock = MagicMock()
        tenant_mock.tax_rounding_policy = "per_line"
        mock_db.scalar = AsyncMock(side_effect=[active, tenant_mock])
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_db.execute = AsyncMock(side_effect=[accounts_result, count_result])

        with patch("app.services.bills.emit", new_callable=AsyncMock):
            bill = await create_bill(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-01-15",
                currency="USD",
                lines=self._make_lines(),
            )

        assert bill is not None
