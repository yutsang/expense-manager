"""Unit tests for payment over-allocation prevention (Bug #49).

Tests cover:
  - Allocating more than payment.amount raises OverAllocationError.
  - First allocation up to payment.amount succeeds.
  - Second allocation that would push total past payment.amount raises.
  - Aggregate check uses existing non-voided allocations (pre-flush).
"""

from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


@_skip_311
class TestPaymentOverAllocation:
    """allocate_payment must prevent total allocations from exceeding payment.amount."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_payment(
        self,
        *,
        amount: str = "1000.0000",
        status: str = "pending",
    ) -> MagicMock:
        payment = MagicMock()
        payment.id = "pay-1"
        payment.tenant_id = "t1"
        payment.amount = Decimal(amount)
        payment.currency = "USD"
        payment.status = status
        payment.version = 1
        payment.updated_by = None
        return payment

    def _make_invoice(self, *, amount_due: str = "1000.0000") -> MagicMock:
        inv = MagicMock()
        inv.id = "inv-1"
        inv.tenant_id = "t1"
        inv.amount_due = Decimal(amount_due)
        return inv

    @pytest.mark.anyio
    async def test_first_allocation_within_limit_succeeds(self, mock_db: AsyncMock) -> None:
        """A single allocation equal to payment amount should succeed."""
        from app.services.payments import allocate_payment

        payment = self._make_payment(amount="1000.0000")
        invoice = self._make_invoice(amount_due="1000.0000")

        # existing allocations total = 0 (no previous allocations)
        existing_sum_result = MagicMock()
        existing_sum_result.scalar.return_value = Decimal("0")

        mock_db.execute = AsyncMock(return_value=existing_sum_result)

        with (
            patch("app.services.payments.get_payment", return_value=payment),
            patch.object(mock_db, "scalar", return_value=invoice),
            patch("app.services.payments.emit", new_callable=AsyncMock),
        ):
            result = await allocate_payment(
                mock_db,
                "t1",
                "actor-1",
                payment_id="pay-1",
                invoice_id="inv-1",
                amount_applied=Decimal("1000.0000"),
            )

        assert result is not None

    @pytest.mark.anyio
    async def test_over_allocation_raises(self, mock_db: AsyncMock) -> None:
        """Allocating more than the payment amount should raise OverAllocationError."""
        from app.services.payments import OverAllocationError, allocate_payment

        payment = self._make_payment(amount="1000.0000")
        invoice = self._make_invoice(amount_due="2000.0000")

        # existing allocations total = 0
        existing_sum_result = MagicMock()
        existing_sum_result.scalar.return_value = Decimal("0")

        mock_db.execute = AsyncMock(return_value=existing_sum_result)

        with (
            patch("app.services.payments.get_payment", return_value=payment),
            patch.object(mock_db, "scalar", return_value=invoice),
            pytest.raises(OverAllocationError),
        ):
            await allocate_payment(
                mock_db,
                "t1",
                "actor-1",
                payment_id="pay-1",
                invoice_id="inv-1",
                amount_applied=Decimal("1500.0000"),
            )

    @pytest.mark.anyio
    async def test_second_allocation_exceeding_total_raises(self, mock_db: AsyncMock) -> None:
        """A second allocation that pushes the total past payment.amount should raise."""
        from app.services.payments import OverAllocationError, allocate_payment

        payment = self._make_payment(amount="1000.0000")
        invoice = self._make_invoice(amount_due="800.0000")

        # existing allocations total = 600 (from a prior allocation)
        existing_sum_result = MagicMock()
        existing_sum_result.scalar.return_value = Decimal("600.0000")

        mock_db.execute = AsyncMock(return_value=existing_sum_result)

        with (
            patch("app.services.payments.get_payment", return_value=payment),
            patch.object(mock_db, "scalar", return_value=invoice),
            pytest.raises(OverAllocationError),
        ):
            # 600 existing + 500 new = 1100 > 1000 payment amount
            await allocate_payment(
                mock_db,
                "t1",
                "actor-1",
                payment_id="pay-1",
                invoice_id="inv-1",
                amount_applied=Decimal("500.0000"),
            )

    @pytest.mark.anyio
    async def test_exact_remaining_amount_succeeds(self, mock_db: AsyncMock) -> None:
        """Allocating exactly the remaining amount should succeed."""
        from app.services.payments import allocate_payment

        payment = self._make_payment(amount="1000.0000")
        invoice = self._make_invoice(amount_due="400.0000")

        # existing allocations total = 600
        existing_sum_result = MagicMock()
        existing_sum_result.scalar.return_value = Decimal("600.0000")

        mock_db.execute = AsyncMock(return_value=existing_sum_result)

        with (
            patch("app.services.payments.get_payment", return_value=payment),
            patch.object(mock_db, "scalar", return_value=invoice),
            patch("app.services.payments.emit", new_callable=AsyncMock),
        ):
            # 600 existing + 400 new = 1000 == payment amount — OK
            result = await allocate_payment(
                mock_db,
                "t1",
                "actor-1",
                payment_id="pay-1",
                invoice_id="inv-1",
                amount_applied=Decimal("400.0000"),
            )

        assert result is not None

    @pytest.mark.anyio
    async def test_voided_payment_still_blocked(self, mock_db: AsyncMock) -> None:
        """Allocating to a voided payment should still raise PaymentTransitionError."""
        from app.services.payments import PaymentTransitionError, allocate_payment

        payment = self._make_payment(amount="1000.0000", status="voided")

        with (
            patch("app.services.payments.get_payment", return_value=payment),
            pytest.raises(PaymentTransitionError, match="voided"),
        ):
            await allocate_payment(
                mock_db,
                "t1",
                "actor-1",
                payment_id="pay-1",
                invoice_id="inv-1",
                amount_applied=Decimal("100.0000"),
            )
