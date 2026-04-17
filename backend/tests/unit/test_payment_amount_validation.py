"""Unit tests for payment amount positivity validation (Issue #11).

Tests cover:
  - PaymentCreate schema rejects zero amount
  - PaymentCreate schema rejects negative amount
  - PaymentCreate schema rejects non-numeric amount
  - PaymentCreate schema accepts valid positive amount
  - Service-level guard in create_payment raises ValueError for zero amount
  - Service-level guard in create_payment raises ValueError for negative amount
"""

from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.schemas import PaymentCreate

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ---------------------------------------------------------------------------
# Schema-level tests: PaymentCreate
# ---------------------------------------------------------------------------


class TestPaymentCreateAmountValidation:
    """PaymentCreate schema must reject zero, negative, and non-numeric amounts."""

    def test_zero_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="[Aa]mount must be.*positive|[Aa]mount.*greater"):
            PaymentCreate(
                payment_type="received",
                contact_id="c1",
                amount="0",
                currency="USD",
                payment_date="2026-04-16",
            )

    def test_zero_with_decimals_rejected(self) -> None:
        with pytest.raises(ValueError, match="[Aa]mount must be.*positive|[Aa]mount.*greater"):
            PaymentCreate(
                payment_type="received",
                contact_id="c1",
                amount="0.00",
                currency="USD",
                payment_date="2026-04-16",
            )

    def test_negative_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="[Aa]mount must be.*positive|[Aa]mount.*greater"):
            PaymentCreate(
                payment_type="received",
                contact_id="c1",
                amount="-500.00",
                currency="USD",
                payment_date="2026-04-16",
            )

    def test_non_numeric_amount_rejected(self) -> None:
        with pytest.raises(Exception):
            PaymentCreate(
                payment_type="received",
                contact_id="c1",
                amount="not-a-number",
                currency="USD",
                payment_date="2026-04-16",
            )

    def test_positive_amount_accepted(self) -> None:
        p = PaymentCreate(
            payment_type="received",
            contact_id="c1",
            amount="100.50",
            currency="USD",
            payment_date="2026-04-16",
        )
        assert p.amount == "100.50"

    def test_small_positive_amount_accepted(self) -> None:
        p = PaymentCreate(
            payment_type="received",
            contact_id="c1",
            amount="0.01",
            currency="USD",
            payment_date="2026-04-16",
        )
        assert p.amount == "0.01"


# ---------------------------------------------------------------------------
# Service-level tests: create_payment amount guard
# ---------------------------------------------------------------------------


@_skip_311
class TestCreatePaymentAmountGuard:
    """create_payment raises ValueError when amount <= 0."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = AsyncMock()
        db.execute = AsyncMock()
        return db

    def _make_contact(self) -> MagicMock:
        contact = MagicMock()
        contact.id = "c1"
        contact.tenant_id = "t1"
        return contact

    @pytest.mark.anyio
    async def test_zero_amount_raises(self, mock_db: AsyncMock) -> None:
        from app.services.payments import create_payment

        mock_db.scalar = AsyncMock(return_value=self._make_contact())

        with pytest.raises(ValueError, match="[Aa]mount must be.*positive|[Aa]mount.*greater"):
            await create_payment(
                mock_db,
                "t1",
                "actor-1",
                payment_type="received",
                contact_id="c1",
                amount=Decimal("0"),
                currency="USD",
                payment_date="2026-04-16",
            )

    @pytest.mark.anyio
    async def test_negative_amount_raises(self, mock_db: AsyncMock) -> None:
        from app.services.payments import create_payment

        mock_db.scalar = AsyncMock(return_value=self._make_contact())

        with pytest.raises(ValueError, match="[Aa]mount must be.*positive|[Aa]mount.*greater"):
            await create_payment(
                mock_db,
                "t1",
                "actor-1",
                payment_type="received",
                contact_id="c1",
                amount=Decimal("-100"),
                currency="USD",
                payment_date="2026-04-16",
            )
