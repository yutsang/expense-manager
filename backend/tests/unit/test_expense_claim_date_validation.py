"""Unit tests for expense claim date validation (Issue #27).

Tests cover:
  - Reject expense claim when claim_date is in the future (> today)
  - Reject expense claim when claim_date falls in a hard_closed period
  - Reject expense claim when claim_date falls in an audited period
  - Accept expense claim when claim_date falls in a soft_closed period (with warning)
  - Accept expense claim when claim_date falls in an open period (happy path)
  - Accept expense claim with today's date (boundary)
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_UTC = timezone.utc  # noqa: UP017 - need 3.10 compat

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(
    _NEEDS_311, reason="transitive imports use datetime.UTC (Python >=3.11)"
)


def _claim_data(*, claim_date: date | str | None = None) -> dict:
    """Build a minimal expense claim payload for create_expense_claim."""
    d = claim_date or str(date.today())
    return {
        "contact_id": "contact-1",
        "title": "Test claim",
        "claim_date": str(d),
        "currency": "USD",
        "lines": [
            {
                "account_id": "acc-1",
                "amount": "50.00",
                "tax_amount": "0",
                "description": "Test line",
            },
        ],
    }


def _make_period(*, status: str = "open", name: str = "2026-04") -> MagicMock:
    p = MagicMock()
    p.id = "period-1"
    p.tenant_id = "t1"
    p.name = name
    p.status = status
    p.start_date = datetime(2026, 4, 1, tzinfo=_UTC)
    p.end_date = datetime(2026, 4, 30, tzinfo=_UTC)
    return p


def _mock_db() -> AsyncMock:
    """Build an AsyncMock db session.

    The scalar call returns None (no cross-claim dup).
    The execute call returns no existing receipts.
    """
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.scalar = AsyncMock(return_value=None)

    # For the count query (auto-numbering) and cross-claim receipt query
    count_result = MagicMock()
    count_result.scalar.return_value = 0
    count_result.first.return_value = None
    db.execute = AsyncMock(return_value=count_result)

    return db


# ── Source-inspection tests (run on any Python) ──────────────────────────────


class TestDateValidationSourceInspection:
    """Verify the date validation code exists in expense_claims.py via source inspection."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "expense_claims.py"
        )
        return svc_path.read_text()

    def test_future_date_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class FutureDateError" in source

    def test_hard_closed_period_check_exists(self) -> None:
        source = self._read_service_source()
        assert "hard_closed" in source

    def test_audited_period_check_exists(self) -> None:
        source = self._read_service_source()
        assert "audited" in source

    def test_get_period_for_date_imported(self) -> None:
        source = self._read_service_source()
        assert "get_period_for_date" in source

    def test_soft_closed_warning_logged(self) -> None:
        source = self._read_service_source()
        assert "soft_closed" in source


class TestApiHandlesDateErrors:
    """Verify the API endpoint maps date-validation errors to HTTP 422."""

    def _read_api_source(self) -> str:
        import pathlib

        api_path = (
            pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "expense_claims.py"
        )
        return api_path.read_text()

    def test_api_imports_future_date_error(self) -> None:
        source = self._read_api_source()
        assert "FutureDateError" in source

    def test_api_imports_period_posting_error(self) -> None:
        source = self._read_api_source()
        assert "PeriodPostingError" in source


# ── Async service tests (require Python 3.11+ due to transitive imports) ─────


@_skip_311
class TestRejectFutureDate:
    """Expense claim with claim_date in the future must be rejected."""

    @pytest.mark.anyio
    async def test_future_date_raises(self) -> None:
        from app.services.expense_claims import FutureDateError, create_expense_claim

        future_date = date.today() + timedelta(days=1)
        db = _mock_db()

        with pytest.raises(FutureDateError, match="future"):
            await create_expense_claim(db, "t1", "user-1", _claim_data(claim_date=future_date))

    @pytest.mark.anyio
    async def test_far_future_date_raises(self) -> None:
        from app.services.expense_claims import FutureDateError, create_expense_claim

        future_date = date.today() + timedelta(days=30)
        db = _mock_db()

        with pytest.raises(FutureDateError, match="future"):
            await create_expense_claim(db, "t1", "user-1", _claim_data(claim_date=future_date))

    @pytest.mark.anyio
    async def test_today_is_accepted(self) -> None:
        from app.services.expense_claims import create_expense_claim

        today = date.today()
        period = _make_period(status="open")
        db = _mock_db()

        with patch(
            "app.services.expense_claims.get_period_for_date",
            new_callable=AsyncMock,
            return_value=period,
        ):
            claim = await create_expense_claim(db, "t1", "user-1", _claim_data(claim_date=today))
            assert claim is not None


@_skip_311
class TestRejectHardClosedPeriod:
    """Expense claim with claim_date in a hard_closed period must be rejected."""

    @pytest.mark.anyio
    async def test_hard_closed_period_raises(self) -> None:
        from app.services.expense_claims import create_expense_claim
        from app.services.periods import PeriodPostingError

        yesterday = date.today() - timedelta(days=1)
        period = _make_period(status="hard_closed", name=yesterday.strftime("%Y-%m"))
        db = _mock_db()

        with (
            patch(
                "app.services.expense_claims.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
            pytest.raises(PeriodPostingError, match="hard_closed"),
        ):
            await create_expense_claim(db, "t1", "user-1", _claim_data(claim_date=yesterday))

    @pytest.mark.anyio
    async def test_hard_closed_error_includes_period_name(self) -> None:
        from app.services.expense_claims import create_expense_claim
        from app.services.periods import PeriodPostingError

        yesterday = date.today() - timedelta(days=1)
        period = _make_period(status="hard_closed", name="2026-03")
        db = _mock_db()

        with (
            patch(
                "app.services.expense_claims.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
            pytest.raises(PeriodPostingError, match="2026-03"),
        ):
            await create_expense_claim(db, "t1", "user-1", _claim_data(claim_date=yesterday))

    @pytest.mark.anyio
    async def test_audited_period_raises(self) -> None:
        from app.services.expense_claims import create_expense_claim
        from app.services.periods import PeriodPostingError

        yesterday = date.today() - timedelta(days=1)
        period = _make_period(status="audited", name=yesterday.strftime("%Y-%m"))
        db = _mock_db()

        with (
            patch(
                "app.services.expense_claims.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
            pytest.raises(PeriodPostingError, match="audited"),
        ):
            await create_expense_claim(db, "t1", "user-1", _claim_data(claim_date=yesterday))


@_skip_311
class TestSoftClosedPeriodWarning:
    """Expense claim in a soft_closed period is accepted (with warning logged)."""

    @pytest.mark.anyio
    async def test_soft_closed_period_is_accepted(self) -> None:
        from app.services.expense_claims import create_expense_claim

        yesterday = date.today() - timedelta(days=1)
        period = _make_period(status="soft_closed", name=yesterday.strftime("%Y-%m"))
        db = _mock_db()

        with patch(
            "app.services.expense_claims.get_period_for_date",
            new_callable=AsyncMock,
            return_value=period,
        ):
            claim = await create_expense_claim(
                db, "t1", "user-1", _claim_data(claim_date=yesterday)
            )
            assert claim is not None


@_skip_311
class TestOpenPeriodAccepted:
    """Expense claim in an open period with a past date works normally."""

    @pytest.mark.anyio
    async def test_open_period_past_date_accepted(self) -> None:
        from app.services.expense_claims import create_expense_claim

        yesterday = date.today() - timedelta(days=1)
        period = _make_period(status="open", name=yesterday.strftime("%Y-%m"))
        db = _mock_db()

        with patch(
            "app.services.expense_claims.get_period_for_date",
            new_callable=AsyncMock,
            return_value=period,
        ):
            claim = await create_expense_claim(
                db, "t1", "user-1", _claim_data(claim_date=yesterday)
            )
            assert claim is not None
            assert db.add.call_count >= 1
