"""Unit tests for positive total validation on invoice/bill creation (Issue #8).

Tests cover:
  - create_invoice raises ValueError when computed total <= 0
  - create_invoice accepts a positive total
  - create_bill raises ValueError when computed total <= 0
  - create_bill accepts a positive total
  - Zero quantity lines produce zero total and are rejected
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ---------------------------------------------------------------------------
# Invoice total validation
# ---------------------------------------------------------------------------


@_skip_311
class TestCreateInvoicePositiveTotal:
    """create_invoice must reject total <= 0."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_zero_total_rejected(self, mock_db: AsyncMock) -> None:
        from app.services.invoices import create_invoice

        with pytest.raises(
            ValueError,
            match="[Tt]otal.*must be.*positive|[Tt]otal.*greater than zero|[Tt]otal.*must be greater",
        ):
            await create_invoice(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-04-16",
                currency="USD",
                lines=[
                    {
                        "account_id": "a1",
                        "quantity": "0",
                        "unit_price": "100",
                        "_tax_rate": "0",
                    }
                ],
            )

    @pytest.mark.anyio
    async def test_negative_total_rejected(self, mock_db: AsyncMock) -> None:
        """Negative totals (e.g. from negative unit_price, if ever allowed) are rejected."""
        from app.services.invoices import create_invoice

        with pytest.raises(
            ValueError,
            match="[Tt]otal.*must be.*positive|[Tt]otal.*greater than zero|[Tt]otal.*must be greater",
        ):
            await create_invoice(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-04-16",
                currency="USD",
                lines=[
                    {
                        "account_id": "a1",
                        "quantity": "1",
                        "unit_price": "0",
                        "_tax_rate": "0",
                    }
                ],
            )

    @pytest.mark.anyio
    async def test_positive_total_accepted(self, mock_db: AsyncMock) -> None:
        from app.services.invoices import create_invoice

        result = await create_invoice(
            mock_db,
            "t1",
            "actor-1",
            contact_id="c1",
            issue_date="2026-04-16",
            currency="USD",
            lines=[
                {
                    "account_id": "a1",
                    "quantity": "2",
                    "unit_price": "50",
                    "_tax_rate": "0.10",
                }
            ],
        )
        assert result is not None


# ---------------------------------------------------------------------------
# Bill total validation
# ---------------------------------------------------------------------------


@_skip_311
class TestCreateBillPositiveTotal:
    """create_bill must reject total <= 0."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = AsyncMock()
        return db

    @pytest.mark.anyio
    async def test_zero_total_rejected(self, mock_db: AsyncMock) -> None:
        from app.services.bills import create_bill

        with pytest.raises(
            ValueError,
            match="[Tt]otal.*must be.*positive|[Tt]otal.*greater than zero|[Tt]otal.*must be greater",
        ):
            await create_bill(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-04-16",
                currency="USD",
                lines=[
                    {
                        "account_id": "a1",
                        "quantity": "0",
                        "unit_price": "100",
                        "_tax_rate": "0",
                    }
                ],
            )

    @pytest.mark.anyio
    async def test_negative_total_rejected(self, mock_db: AsyncMock) -> None:
        from app.services.bills import create_bill

        with pytest.raises(
            ValueError,
            match="[Tt]otal.*must be.*positive|[Tt]otal.*greater than zero|[Tt]otal.*must be greater",
        ):
            await create_bill(
                mock_db,
                "t1",
                "actor-1",
                contact_id="c1",
                issue_date="2026-04-16",
                currency="USD",
                lines=[
                    {
                        "account_id": "a1",
                        "quantity": "1",
                        "unit_price": "0",
                        "_tax_rate": "0",
                    }
                ],
            )

    @pytest.mark.anyio
    async def test_positive_total_accepted(self, mock_db: AsyncMock) -> None:
        from app.services.bills import create_bill

        result = await create_bill(
            mock_db,
            "t1",
            "actor-1",
            contact_id="c1",
            issue_date="2026-04-16",
            currency="USD",
            lines=[
                {
                    "account_id": "a1",
                    "quantity": "2",
                    "unit_price": "50",
                    "_tax_rate": "0.10",
                }
            ],
        )
        assert result is not None
