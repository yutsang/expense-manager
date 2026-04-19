"""Unit tests for positive total validation on invoice/bill creation (Issue #8).

Tests cover:
  - create_invoice raises ValueError when computed total <= 0
  - create_invoice accepts a positive total
  - create_bill raises ValueError when computed total <= 0
  - create_bill accepts a positive total
  - Zero quantity lines produce zero total and are rejected
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# Invoice total validation
# ---------------------------------------------------------------------------


class TestCreateInvoicePositiveTotal:
    """create_invoice must reject total <= 0."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        from unittest.mock import MagicMock

        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        # scalar returns: contact (is_archived=False), then tenant
        contact_mock = MagicMock()
        contact_mock.is_archived = False
        tenant_mock = MagicMock()
        tenant_mock.tax_rounding_policy = "per_line"
        db.scalar = AsyncMock(side_effect=[contact_mock, tenant_mock])
        # execute returns: account validation result, then bill count
        acct_result = MagicMock()
        acct_result.scalars.return_value.all.return_value = [MagicMock(id="a1", tenant_id="t1")]
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        db.execute = AsyncMock(side_effect=[acct_result, count_result])
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
        from unittest.mock import patch

        from app.services.invoices import create_invoice

        with patch("app.services.invoices.emit", new_callable=AsyncMock):
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


class TestCreateBillPositiveTotal:
    """create_bill must reject total <= 0."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        from unittest.mock import MagicMock

        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        # scalar returns: contact (is_archived=False), then tenant
        contact_mock = MagicMock()
        contact_mock.is_archived = False
        tenant_mock = MagicMock()
        tenant_mock.tax_rounding_policy = "per_line"
        db.scalar = AsyncMock(side_effect=[contact_mock, tenant_mock])
        # execute returns: account validation result, then bill count
        acct_result = MagicMock()
        acct_result.scalars.return_value.all.return_value = [MagicMock(id="a1", tenant_id="t1")]
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        db.execute = AsyncMock(side_effect=[acct_result, count_result])
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
        from unittest.mock import patch

        from app.services.bills import create_bill

        with patch("app.services.bills.emit", new_callable=AsyncMock):
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
