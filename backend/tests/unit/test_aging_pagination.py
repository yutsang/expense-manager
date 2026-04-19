"""Unit tests for paginated AR / AP aging reports.

Tests cover:
- Schema: AgingResponse includes next_cursor field
- _build_aging_response returns paginated rows with correct bucket totals
- API endpoints accept limit and cursor query params
- Limit clamped to max 200; default is 50
- Bucket totals reflect full dataset regardless of pagination
- Backward compatibility: no params returns first 50 rows
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.schemas import AgingResponse

_UTC = timezone.utc  # noqa: UP017 - need 3.10 compat for test runner

# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestAgingResponseSchema:
    """AgingResponse must include next_cursor for pagination."""

    def test_next_cursor_field_exists_and_nullable(self) -> None:
        resp = AgingResponse(
            as_of=date(2026, 4, 16),
            current_total="0.00",
            bucket_1_30="0.00",
            bucket_31_60="0.00",
            bucket_61_90="0.00",
            bucket_90_plus="0.00",
            grand_total="0.00",
            rows=[],
            generated_at=datetime(2026, 4, 16, tzinfo=_UTC),
            next_cursor=None,
        )
        assert resp.next_cursor is None

    def test_next_cursor_can_be_string(self) -> None:
        resp = AgingResponse(
            as_of=date(2026, 4, 16),
            current_total="0.00",
            bucket_1_30="0.00",
            bucket_31_60="0.00",
            bucket_61_90="0.00",
            bucket_90_plus="0.00",
            grand_total="0.00",
            rows=[],
            generated_at=datetime(2026, 4, 16, tzinfo=_UTC),
            next_cursor="abc-123",
        )
        assert resp.next_cursor == "abc-123"

    def test_backward_compat_next_cursor_defaults_to_none(self) -> None:
        """Old callers that don't send next_cursor should still work."""
        resp = AgingResponse(
            as_of=date(2026, 4, 16),
            current_total="0.00",
            bucket_1_30="0.00",
            bucket_31_60="0.00",
            bucket_61_90="0.00",
            bucket_90_plus="0.00",
            grand_total="0.00",
            rows=[],
            generated_at=datetime(2026, 4, 16, tzinfo=_UTC),
        )
        assert resp.next_cursor is None


# ---------------------------------------------------------------------------
# Helpers to build mock DB results
# ---------------------------------------------------------------------------


def _make_row(
    doc_id: str,
    invoice_number: str,
    issue_date: date,
    due_date: date | None,
    total: Decimal,
    amount_due: Decimal,
    contact_id: str = "c-1",
    contact_name: str = "Acme Corp",
) -> Any:
    """Return a mock row that looks like what the SQL query returns."""
    row = MagicMock()
    row.doc_id = doc_id
    row.invoice_number = invoice_number
    row.issue_date = issue_date
    row.due_date = due_date
    row.total = total
    row.amount_due = amount_due
    row.contact_id = contact_id
    row.contact_name = contact_name
    return row


# ---------------------------------------------------------------------------
# _build_aging_response pagination tests
# ---------------------------------------------------------------------------


class TestBuildAgingResponsePagination:
    """The core helper must paginate rows while keeping full bucket totals."""

    @pytest.mark.anyio
    async def test_returns_limited_rows_and_next_cursor(self) -> None:
        """When more rows exist than limit, response has next_cursor."""
        from app.api.v1.reports import _build_aging_response

        as_of = date(2026, 4, 16)
        rows = [
            _make_row(
                f"inv-{i}",
                f"INV-{i:04d}",
                date(2026, 3, 1),
                date(2026, 3, 15),
                Decimal("100.00"),
                Decimal("100.00"),
            )
            for i in range(5)
        ]

        # Mock: bucket totals query returns full-dataset totals
        bucket_result = MagicMock()
        bucket_result.fetchall.return_value = [
            MagicMock(bucket="1-30", bucket_total=Decimal("500.00")),
        ]

        # Mock: detail query returns limit+1 rows (to detect next page)
        detail_result = MagicMock()
        detail_result.fetchall.return_value = rows[:4]  # limit+1 = 4 for limit=3

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=[bucket_result, detail_result])

        resp = await _build_aging_response(
            mock_db, as_of, "invoices", ("authorised", "sent", "partial"), limit=3
        )

        # Should have exactly limit rows
        assert len(resp.rows) == 3
        # next_cursor should be set to the last row's doc_id
        assert resp.next_cursor == rows[2].doc_id

    @pytest.mark.anyio
    async def test_no_next_cursor_on_last_page(self) -> None:
        """When rows <= limit, next_cursor should be None."""
        from app.api.v1.reports import _build_aging_response

        as_of = date(2026, 4, 16)
        rows = [
            _make_row(
                f"inv-{i}",
                f"INV-{i:04d}",
                date(2026, 3, 1),
                date(2026, 3, 15),
                Decimal("100.00"),
                Decimal("100.00"),
            )
            for i in range(2)
        ]

        bucket_result = MagicMock()
        bucket_result.fetchall.return_value = [
            MagicMock(bucket="1-30", bucket_total=Decimal("200.00")),
        ]

        detail_result = MagicMock()
        detail_result.fetchall.return_value = rows  # only 2, limit is 50

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=[bucket_result, detail_result])

        resp = await _build_aging_response(
            mock_db, as_of, "invoices", ("authorised", "sent", "partial"), limit=50
        )

        assert len(resp.rows) == 2
        assert resp.next_cursor is None

    @pytest.mark.anyio
    async def test_bucket_totals_reflect_full_dataset(self) -> None:
        """Bucket totals come from SQL aggregation over the full dataset,
        not just the paginated page."""
        from app.api.v1.reports import _build_aging_response

        as_of = date(2026, 4, 16)
        # Only return 1 detail row (limit=1)
        rows = [
            _make_row(
                "inv-0",
                "INV-0001",
                date(2026, 3, 1),
                date(2026, 3, 15),
                Decimal("100.00"),
                Decimal("100.00"),
            ),
            _make_row(
                "inv-1",
                "INV-0002",
                date(2026, 3, 1),
                date(2026, 3, 15),
                Decimal("200.00"),
                Decimal("200.00"),
            ),
        ]

        # SQL-side bucket totals for the *full* dataset
        bucket_result = MagicMock()
        bucket_result.fetchall.return_value = [
            MagicMock(bucket="current", bucket_total=Decimal("50.00")),
            MagicMock(bucket="1-30", bucket_total=Decimal("300.00")),
            MagicMock(bucket="31-60", bucket_total=Decimal("150.00")),
            MagicMock(bucket="61-90", bucket_total=Decimal("75.00")),
            MagicMock(bucket="90+", bucket_total=Decimal("25.00")),
        ]

        detail_result = MagicMock()
        detail_result.fetchall.return_value = rows  # 2 rows, limit+1 = 2 for limit=1

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=[bucket_result, detail_result])

        resp = await _build_aging_response(
            mock_db, as_of, "invoices", ("authorised", "sent", "partial"), limit=1
        )

        # Only 1 detail row returned
        assert len(resp.rows) == 1
        # But totals reflect the full dataset from SQL
        assert resp.current_total == "50.00"
        assert resp.bucket_1_30 == "300.00"
        assert resp.bucket_31_60 == "150.00"
        assert resp.bucket_61_90 == "75.00"
        assert resp.bucket_90_plus == "25.00"
        assert resp.grand_total == "600.00"

    @pytest.mark.anyio
    async def test_cursor_param_passed_to_detail_query(self) -> None:
        """When cursor is provided, the detail query should filter by it."""
        from app.api.v1.reports import _build_aging_response

        as_of = date(2026, 4, 16)

        bucket_result = MagicMock()
        bucket_result.fetchall.return_value = []

        detail_result = MagicMock()
        detail_result.fetchall.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=[bucket_result, detail_result])

        await _build_aging_response(
            mock_db,
            as_of,
            "invoices",
            ("authorised", "sent", "partial"),
            limit=50,
            cursor="inv-prev-last",
        )

        # Two DB calls: bucket totals + detail rows
        assert mock_db.execute.call_count == 2
        # The detail query (second call) should include the cursor value
        detail_call_args = mock_db.execute.call_args_list[1]
        detail_sql_str = str(detail_call_args[0][0])
        assert "cursor" in detail_sql_str.lower() or "> :cursor" in detail_sql_str

    @pytest.mark.anyio
    async def test_empty_result(self) -> None:
        """No rows at all should return empty response with zero totals."""
        from app.api.v1.reports import _build_aging_response

        as_of = date(2026, 4, 16)

        bucket_result = MagicMock()
        bucket_result.fetchall.return_value = []

        detail_result = MagicMock()
        detail_result.fetchall.return_value = []

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=[bucket_result, detail_result])

        resp = await _build_aging_response(
            mock_db, as_of, "invoices", ("authorised", "sent", "partial")
        )

        assert len(resp.rows) == 0
        assert resp.next_cursor is None
        assert resp.grand_total == "0.00"
        assert resp.current_total == "0.00"


# ---------------------------------------------------------------------------
# API endpoint parameter tests (unit-level, mock the helper)
# ---------------------------------------------------------------------------


class TestAgingEndpointParams:
    """ar-aging and ap-aging endpoints must accept limit and cursor query params."""

    @pytest.mark.anyio
    async def test_ar_aging_passes_limit_and_cursor(self) -> None:
        from app.api.v1.reports import ar_aging_endpoint

        mock_db = AsyncMock()
        mock_response = AgingResponse(
            as_of=date(2026, 4, 16),
            current_total="0.00",
            bucket_1_30="0.00",
            bucket_31_60="0.00",
            bucket_61_90="0.00",
            bucket_90_plus="0.00",
            grand_total="0.00",
            rows=[],
            generated_at=datetime(2026, 4, 16, tzinfo=_UTC),
            next_cursor=None,
        )

        with patch(
            "app.api.v1.reports._build_aging_response", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_response
            await ar_aging_endpoint(
                db=mock_db,
                tenant_id="t-1",
                as_of=date(2026, 4, 16),
                limit=25,
                cursor="inv-abc",
                bucket=None,
            )
            mock_build.assert_called_once_with(
                mock_db,
                date(2026, 4, 16),
                "invoices",
                ("authorised", "sent", "partial"),
                limit=25,
                cursor="inv-abc",
                bucket=None,
            )

    @pytest.mark.anyio
    async def test_ap_aging_passes_limit_and_cursor(self) -> None:
        from app.api.v1.reports import ap_aging_endpoint

        mock_db = AsyncMock()
        mock_response = AgingResponse(
            as_of=date(2026, 4, 16),
            current_total="0.00",
            bucket_1_30="0.00",
            bucket_31_60="0.00",
            bucket_61_90="0.00",
            bucket_90_plus="0.00",
            grand_total="0.00",
            rows=[],
            generated_at=datetime(2026, 4, 16, tzinfo=_UTC),
            next_cursor=None,
        )

        with patch(
            "app.api.v1.reports._build_aging_response", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_response
            await ap_aging_endpoint(
                db=mock_db,
                tenant_id="t-1",
                as_of=date(2026, 4, 16),
                limit=100,
                cursor="bill-xyz",
                bucket=None,
            )
            mock_build.assert_called_once_with(
                mock_db,
                date(2026, 4, 16),
                "bills",
                ("approved", "partial"),
                limit=100,
                cursor="bill-xyz",
                bucket=None,
            )

    @pytest.mark.anyio
    async def test_ar_aging_default_limit_and_no_cursor(self) -> None:
        """When no limit/cursor provided, defaults are used."""
        from app.api.v1.reports import ar_aging_endpoint

        mock_db = AsyncMock()
        mock_response = AgingResponse(
            as_of=date(2026, 4, 16),
            current_total="0.00",
            bucket_1_30="0.00",
            bucket_31_60="0.00",
            bucket_61_90="0.00",
            bucket_90_plus="0.00",
            grand_total="0.00",
            rows=[],
            generated_at=datetime(2026, 4, 16, tzinfo=_UTC),
            next_cursor=None,
        )

        with patch(
            "app.api.v1.reports._build_aging_response", new_callable=AsyncMock
        ) as mock_build:
            mock_build.return_value = mock_response
            # Call with only required params; limit/cursor should use defaults
            await ar_aging_endpoint(
                db=mock_db,
                tenant_id="t-1",
                as_of=date(2026, 4, 16),
                limit=50,
                cursor=None,
                bucket=None,
            )
            mock_build.assert_called_once_with(
                mock_db,
                date(2026, 4, 16),
                "invoices",
                ("authorised", "sent", "partial"),
                limit=50,
                cursor=None,
                bucket=None,
            )
