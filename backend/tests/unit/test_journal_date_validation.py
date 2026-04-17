"""Unit tests for journal entry date validation (Issue #26).

Tests cover:
  - Reject JE when transaction_date falls in a hard_closed period
  - Reject JE when transaction_date falls in an audited period
  - Reject JE when transaction_date is more than 7 days in the future
  - Allow future-dated JE when force=True (and audit-log the override)
  - Accept JE when transaction_date falls in a soft_closed period (with warning)
  - System-generated JEs bypass all date checks
  - Accept JE when transaction_date falls in an open period (no change)
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_UTC = timezone.utc  # noqa: UP017 - need 3.10 compat

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(
    _NEEDS_311, reason="transitive imports use datetime.UTC (Python >=3.11)"
)


def _make_lines() -> list:
    from app.domain.ledger.journal import JournalLineInput

    return [
        JournalLineInput(
            account_id="acc-1",
            debit=Decimal("100.0000"),
            credit=Decimal("0"),
            currency="USD",
            functional_debit=Decimal("100.0000"),
            functional_credit=Decimal("0"),
        ),
        JournalLineInput(
            account_id="acc-2",
            debit=Decimal("0"),
            credit=Decimal("100.0000"),
            currency="USD",
            functional_debit=Decimal("0"),
            functional_credit=Decimal("100.0000"),
        ),
    ]


def _make_period(*, status: str = "open") -> MagicMock:
    p = MagicMock()
    p.id = "period-1"
    p.tenant_id = "t1"
    p.name = "2026-04"
    p.status = status
    p.start_date = datetime(2026, 4, 1, tzinfo=_UTC)
    p.end_date = datetime(2026, 4, 30, tzinfo=_UTC)
    return p


def _mock_db() -> AsyncMock:
    """Build an AsyncMock db session.

    The scalar call returns None (no idempotency dup).
    The execute call returns no control accounts.
    """
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.scalar = AsyncMock(return_value=None)

    accounts_result = MagicMock()
    accounts_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=accounts_result)

    return db


# ── Source-inspection tests (run on any Python) ──────────────────────────────


class TestDateValidationSourceInspection:
    """Verify the date validation code exists in journals.py via source inspection."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "journals.py"
        return svc_path.read_text()

    def test_create_draft_accepts_force_param(self) -> None:
        source = self._read_service_source()
        assert "force: bool" in source or "force:" in source

    def test_future_date_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class FutureDateError" in source

    def test_period_status_check_in_create_draft(self) -> None:
        source = self._read_service_source()
        assert "hard_closed" in source
        assert "audited" in source

    def test_max_future_days_constant_exists(self) -> None:
        source = self._read_service_source()
        assert "_MAX_FUTURE_DAYS" in source

    def test_system_generated_bypasses_date_check(self) -> None:
        source = self._read_service_source()
        # The date validation block should be guarded by `if not system_generated`
        assert "not system_generated" in source

    def test_get_period_for_date_imported(self) -> None:
        source = self._read_service_source()
        assert "get_period_for_date" in source

    def test_future_date_override_audit_event(self) -> None:
        source = self._read_service_source()
        assert "journal.future_date_override" in source

    def test_soft_closed_warning_logged(self) -> None:
        source = self._read_service_source()
        assert "soft_closed_period" in source or "soft_closed" in source


# ── Async service tests (require Python 3.11+ due to transitive imports) ─────


@_skip_311
class TestRejectHardClosedPeriod:
    """JE with a date in a hard_closed period must be rejected."""

    @pytest.mark.anyio
    async def test_hard_closed_period_raises(self) -> None:
        from app.services.journals import create_draft
        from app.services.periods import PeriodPostingError

        period = _make_period(status="hard_closed")
        db = _mock_db()

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            patch(
                "app.services.journals.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
            pytest.raises(PeriodPostingError, match="hard_closed"),
        ):
            await create_draft(
                db,
                tenant_id="t1",
                date_=date(2026, 4, 15),
                period_id="period-1",
                description="Test in closed period",
                lines=_make_lines(),
                actor_id="user-1",
            )

    @pytest.mark.anyio
    async def test_audited_period_raises(self) -> None:
        from app.services.journals import create_draft
        from app.services.periods import PeriodPostingError

        period = _make_period(status="audited")
        db = _mock_db()

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            patch(
                "app.services.journals.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
            pytest.raises(PeriodPostingError, match="audited"),
        ):
            await create_draft(
                db,
                tenant_id="t1",
                date_=date(2026, 4, 15),
                period_id="period-1",
                description="Test in audited period",
                lines=_make_lines(),
                actor_id="user-1",
            )


@_skip_311
class TestRejectFarFutureDate:
    """JE dated more than 7 days in the future must be rejected unless force=True."""

    @pytest.mark.anyio
    async def test_far_future_date_raises(self) -> None:
        from app.services.journals import FutureDateError, create_draft

        future_date = date.today() + timedelta(days=8)
        period = _make_period(status="open")
        db = _mock_db()

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            patch(
                "app.services.journals.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
            pytest.raises(FutureDateError, match="future"),
        ):
            await create_draft(
                db,
                tenant_id="t1",
                date_=future_date,
                period_id="period-1",
                description="Far future entry",
                lines=_make_lines(),
                actor_id="user-1",
            )

    @pytest.mark.anyio
    async def test_exactly_7_days_future_is_accepted(self) -> None:
        from app.services.journals import create_draft

        future_date = date.today() + timedelta(days=7)
        period = _make_period(status="open")
        db = _mock_db()

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            patch(
                "app.services.journals.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
        ):
            je = await create_draft(
                db,
                tenant_id="t1",
                date_=future_date,
                period_id="period-1",
                description="Boundary future entry",
                lines=_make_lines(),
                actor_id="user-1",
            )
            assert je is not None

    @pytest.mark.anyio
    async def test_force_allows_far_future_date(self) -> None:
        from app.services.journals import create_draft

        future_date = date.today() + timedelta(days=30)
        period = _make_period(status="open")
        db = _mock_db()

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            patch(
                "app.services.journals.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
        ):
            je = await create_draft(
                db,
                tenant_id="t1",
                date_=future_date,
                period_id="period-1",
                description="Forced future entry",
                lines=_make_lines(),
                actor_id="user-1",
                force=True,
            )
            assert je is not None

    @pytest.mark.anyio
    async def test_force_future_date_emits_audit_event(self) -> None:
        from app.services.journals import create_draft

        future_date = date.today() + timedelta(days=30)
        period = _make_period(status="open")
        db = _mock_db()

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock) as mock_emit,
            patch(
                "app.services.journals.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
        ):
            await create_draft(
                db,
                tenant_id="t1",
                date_=future_date,
                period_id="period-1",
                description="Forced future entry",
                lines=_make_lines(),
                actor_id="user-1",
                force=True,
            )

            # Check that an audit event was emitted for the force override
            emit_calls = mock_emit.call_args_list
            override_calls = [
                c for c in emit_calls if c.kwargs.get("action") == "journal.future_date_override"
            ]
            assert len(override_calls) == 1


@_skip_311
class TestSoftClosedPeriodWarning:
    """JE in a soft_closed period is accepted but create_draft logs a warning."""

    @pytest.mark.anyio
    async def test_soft_closed_period_is_accepted(self) -> None:
        from app.services.journals import create_draft

        period = _make_period(status="soft_closed")
        db = _mock_db()

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            patch(
                "app.services.journals.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
        ):
            je = await create_draft(
                db,
                tenant_id="t1",
                date_=date(2026, 4, 15),
                period_id="period-1",
                description="Soft-closed period entry",
                lines=_make_lines(),
                actor_id="user-1",
            )
            assert je is not None


@_skip_311
class TestSystemGeneratedBypass:
    """System-generated JEs (e.g., from invoice/bill auth) skip date checks."""

    @pytest.mark.anyio
    async def test_system_generated_skips_hard_closed_check(self) -> None:
        from app.services.journals import create_draft

        period = _make_period(status="hard_closed")
        db = _mock_db()

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            patch(
                "app.services.journals.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
        ):
            je = await create_draft(
                db,
                tenant_id="t1",
                date_=date(2026, 4, 15),
                period_id="period-1",
                description="System-generated in closed period",
                lines=_make_lines(),
                system_generated=True,
            )
            assert je is not None

    @pytest.mark.anyio
    async def test_system_generated_skips_future_date_check(self) -> None:
        from app.services.journals import create_draft

        future_date = date.today() + timedelta(days=60)
        period = _make_period(status="open")
        db = _mock_db()

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            patch(
                "app.services.journals.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
        ):
            je = await create_draft(
                db,
                tenant_id="t1",
                date_=future_date,
                period_id="period-1",
                description="System-generated far future",
                lines=_make_lines(),
                system_generated=True,
            )
            assert je is not None


@_skip_311
class TestOpenPeriodAccepted:
    """JE in an open period with a current date should work as before."""

    @pytest.mark.anyio
    async def test_open_period_current_date_accepted(self) -> None:
        from app.services.journals import create_draft

        period = _make_period(status="open")
        db = _mock_db()

        with (
            patch("app.services.journals.emit", new_callable=AsyncMock),
            patch(
                "app.services.journals.get_period_for_date",
                new_callable=AsyncMock,
                return_value=period,
            ),
        ):
            je = await create_draft(
                db,
                tenant_id="t1",
                date_=date.today(),
                period_id="period-1",
                description="Normal entry",
                lines=_make_lines(),
                actor_id="user-1",
            )
            assert je is not None
            assert db.add.call_count >= 1
