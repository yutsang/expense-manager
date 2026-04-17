"""Unit tests for due_date / issue_date cross-field validation (Issue #7).

Tests cover:
  - InvoiceCreate schema rejects due_date < issue_date
  - InvoiceCreate schema accepts due_date == issue_date (same-day terms)
  - InvoiceCreate schema accepts due_date > issue_date
  - InvoiceCreate schema accepts due_date omitted (None)
  - BillCreate schema rejects due_date < issue_date
  - BillCreate schema accepts due_date == issue_date
  - BillCreate schema accepts due_date > issue_date
  - BillCreate schema accepts due_date omitted (None)
  - Service-level guard in create_invoice raises ValueError
  - Service-level guard in create_bill raises ValueError
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock

import pytest

from app.api.v1.schemas import BillCreate, InvoiceCreate

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")

_VALID_LINE = {"account_id": "a1", "quantity": "1", "unit_price": "100"}


# ---------------------------------------------------------------------------
# Schema-level tests: InvoiceCreate
# ---------------------------------------------------------------------------


class TestInvoiceCreateDateOrder:
    """InvoiceCreate rejects due_date before issue_date at the schema level."""

    def test_due_date_before_issue_date_rejected(self) -> None:
        with pytest.raises(ValueError, match="[Dd]ue date must be on or after issue date"):
            InvoiceCreate(
                contact_id="c1",
                issue_date="2026-04-16",
                due_date="2026-04-15",
                currency="USD",
                lines=[_VALID_LINE],
            )

    def test_due_date_equal_to_issue_date_accepted(self) -> None:
        inv = InvoiceCreate(
            contact_id="c1",
            issue_date="2026-04-16",
            due_date="2026-04-16",
            currency="USD",
            lines=[_VALID_LINE],
        )
        assert inv.due_date == inv.issue_date

    def test_due_date_after_issue_date_accepted(self) -> None:
        inv = InvoiceCreate(
            contact_id="c1",
            issue_date="2026-04-01",
            due_date="2026-04-30",
            currency="USD",
            lines=[_VALID_LINE],
        )
        assert inv.due_date is not None
        assert inv.due_date > inv.issue_date

    def test_due_date_omitted_accepted(self) -> None:
        inv = InvoiceCreate(
            contact_id="c1",
            issue_date="2026-04-16",
            currency="USD",
            lines=[_VALID_LINE],
        )
        assert inv.due_date is None


# ---------------------------------------------------------------------------
# Schema-level tests: BillCreate
# ---------------------------------------------------------------------------


class TestBillCreateDateOrder:
    """BillCreate rejects due_date before issue_date at the schema level."""

    def test_due_date_before_issue_date_rejected(self) -> None:
        with pytest.raises(ValueError, match="[Dd]ue date must be on or after issue date"):
            BillCreate(
                contact_id="c1",
                issue_date="2026-04-16",
                due_date="2026-04-15",
                currency="USD",
                lines=[_VALID_LINE],
            )

    def test_due_date_equal_to_issue_date_accepted(self) -> None:
        bill = BillCreate(
            contact_id="c1",
            issue_date="2026-04-16",
            due_date="2026-04-16",
            currency="USD",
            lines=[_VALID_LINE],
        )
        assert bill.due_date == bill.issue_date

    def test_due_date_after_issue_date_accepted(self) -> None:
        bill = BillCreate(
            contact_id="c1",
            issue_date="2026-04-01",
            due_date="2026-04-30",
            currency="USD",
            lines=[_VALID_LINE],
        )
        assert bill.due_date is not None
        assert bill.due_date > bill.issue_date

    def test_due_date_omitted_accepted(self) -> None:
        bill = BillCreate(
            contact_id="c1",
            issue_date="2026-04-16",
            currency="USD",
            lines=[_VALID_LINE],
        )
        assert bill.due_date is None


# ---------------------------------------------------------------------------
# Service-level tests: create_invoice date guard
# ---------------------------------------------------------------------------


@_skip_311
class TestCreateInvoiceDateGuard:
    """create_invoice raises ValueError when due_date < issue_date."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_due_date_before_issue_date_raises(self, mock_db: AsyncMock) -> None:
        from app.services.invoices import create_invoice

        with pytest.raises(ValueError, match="[Dd]ue date"):
            await create_invoice(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-04-16",
                due_date="2026-04-15",
                currency="USD",
                lines=[
                    {"account_id": "a1", "quantity": "1", "unit_price": "100", "_tax_rate": "0"}
                ],
            )

    @pytest.mark.anyio
    async def test_due_date_equal_to_issue_date_allowed(self, mock_db: AsyncMock) -> None:
        from app.services.invoices import create_invoice

        result = await create_invoice(
            mock_db,
            "t1",
            "actor-1",
            contact_id="c1",
            issue_date="2026-04-16",
            due_date="2026-04-16",
            currency="USD",
            lines=[{"account_id": "a1", "quantity": "1", "unit_price": "100", "_tax_rate": "0"}],
        )
        assert result is not None


# ---------------------------------------------------------------------------
# Service-level tests: create_bill date guard
# ---------------------------------------------------------------------------


@_skip_311
class TestCreateBillDateGuard:
    """create_bill raises ValueError when due_date < issue_date."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_due_date_before_issue_date_raises(self, mock_db: AsyncMock) -> None:
        from app.services.bills import create_bill

        with pytest.raises(ValueError, match="[Dd]ue date"):
            await create_bill(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-04-16",
                due_date="2026-04-15",
                currency="USD",
                lines=[
                    {"account_id": "a1", "quantity": "1", "unit_price": "100", "_tax_rate": "0"}
                ],
            )

    @pytest.mark.anyio
    async def test_due_date_equal_to_issue_date_allowed(self, mock_db: AsyncMock) -> None:
        from app.services.bills import create_bill

        result = await create_bill(
            mock_db,
            "t1",
            "actor-1",
            contact_id="c1",
            issue_date="2026-04-16",
            due_date="2026-04-16",
            currency="USD",
            lines=[{"account_id": "a1", "quantity": "1", "unit_price": "100", "_tax_rate": "0"}],
        )
        assert result is not None
