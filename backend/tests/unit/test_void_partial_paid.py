"""Unit tests for voiding partially-paid invoices (Bug #48).

Tests cover:
  - void_invoice raises InvoiceTransitionError when allocations exist
    with amount > 0 (partially-paid invoice).
  - void_invoice succeeds when no allocations exist (unpaid invoice).
  - void_invoice still blocks fully-paid invoices (existing behaviour).
  - void_invoice still blocks already-void invoices (existing behaviour).
"""

from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ---------------------------------------------------------------------------
# Service-level async tests
# ---------------------------------------------------------------------------


@_skip_311
class TestVoidPartiallyPaidInvoice:
    """void_invoice must reject partially-paid invoices with live allocations."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_invoice(
        self,
        *,
        status: str = "partial",
        journal_entry_id: str | None = "je-1",
        amount_due: str = "500.0000",
        total: str = "1000.0000",
    ) -> MagicMock:
        inv = MagicMock()
        inv.id = "inv-1"
        inv.tenant_id = "t1"
        inv.status = status
        inv.number = "INV-00001"
        inv.total = Decimal(total)
        inv.subtotal = Decimal("900.0000")
        inv.tax_total = Decimal("100.0000")
        inv.amount_due = Decimal(amount_due)
        inv.functional_total = Decimal(total)
        inv.currency = "USD"
        inv.fx_rate = Decimal("1")
        inv.contact_id = "contact-1"
        inv.issue_date = "2026-01-15"
        inv.due_date = "2026-02-15"
        inv.period_name = "2026-01"
        inv.reference = None
        inv.notes = None
        inv.version = 2
        inv.updated_by = None
        inv.journal_entry_id = journal_entry_id
        inv.authorised_by = "actor-1"
        inv.voided_at = None
        inv.credit_note_for_id = None
        return inv

    def _make_allocation(self, amount: str = "500.0000") -> MagicMock:
        alloc = MagicMock()
        alloc.id = "alloc-1"
        alloc.payment_id = "pay-1"
        alloc.invoice_id = "inv-1"
        alloc.bill_id = None
        alloc.amount = Decimal(amount)
        return alloc

    @pytest.mark.anyio
    async def test_void_partial_with_allocations_raises(self, mock_db: AsyncMock) -> None:
        """Voiding a partially-paid invoice with live allocations must raise."""
        from app.services.invoices import InvoiceTransitionError, void_invoice

        inv = self._make_invoice(status="partial", amount_due="500.0000")
        allocs = [self._make_allocation("500.0000")]

        # mock get_invoice to return our invoice
        # mock the allocation query to return existing allocations
        alloc_result = MagicMock()
        alloc_result.scalars.return_value.all.return_value = allocs

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch.object(mock_db, "execute", return_value=alloc_result),
        ):
            with pytest.raises(InvoiceTransitionError, match="reverse payments first"):
                await void_invoice(mock_db, "t1", "inv-1", "actor-2")

    @pytest.mark.anyio
    async def test_void_authorised_no_allocations_succeeds(self, mock_db: AsyncMock) -> None:
        """Voiding an authorised invoice with no allocations should succeed."""
        from app.services.invoices import void_invoice

        inv = self._make_invoice(status="authorised", amount_due="1000.0000")
        cn_mock = MagicMock()
        cn_mock.id = "cn-1"
        je_mock = MagicMock()

        # allocation query returns empty list
        alloc_result = MagicMock()
        alloc_result.scalars.return_value.all.return_value = []

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch.object(mock_db, "execute", return_value=alloc_result),
            patch("app.services.invoices.get_invoice_lines", return_value=[]),
            patch(
                "app.services.invoices.create_credit_note",
                return_value=(cn_mock, je_mock),
            ),
        ):
            result = await void_invoice(mock_db, "t1", "inv-1", "actor-2")

        assert result.status == "void"

    @pytest.mark.anyio
    async def test_void_draft_no_je_no_alloc_check(self, mock_db: AsyncMock) -> None:
        """Voiding a draft invoice (no JE, no allocations possible) should work."""
        from app.services.invoices import void_invoice

        inv = self._make_invoice(status="draft", journal_entry_id=None)

        # allocation query returns empty
        alloc_result = MagicMock()
        alloc_result.scalars.return_value.all.return_value = []

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            patch.object(mock_db, "execute", return_value=alloc_result),
        ):
            result = await void_invoice(mock_db, "t1", "inv-1", "actor-2")

        assert result.status == "void"

    @pytest.mark.anyio
    async def test_void_paid_still_blocked(self, mock_db: AsyncMock) -> None:
        """Fully-paid invoices remain blocked (existing behaviour)."""
        from app.services.invoices import InvoiceTransitionError, void_invoice

        inv = self._make_invoice(status="paid")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            pytest.raises(InvoiceTransitionError, match="credit note"),
        ):
            await void_invoice(mock_db, "t1", "inv-1", "actor-2")

    @pytest.mark.anyio
    async def test_void_already_void_still_blocked(self, mock_db: AsyncMock) -> None:
        """Already-void invoices remain blocked (existing behaviour)."""
        from app.services.invoices import InvoiceTransitionError, void_invoice

        inv = self._make_invoice(status="void")

        with (
            patch("app.services.invoices.get_invoice", return_value=inv),
            pytest.raises(InvoiceTransitionError, match="already void"),
        ):
            await void_invoice(mock_db, "t1", "inv-1", "actor-2")
