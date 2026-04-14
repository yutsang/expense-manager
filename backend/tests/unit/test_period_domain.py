"""Unit tests for the period domain — state machine and period generation."""
from __future__ import annotations

from datetime import date

import pytest

from app.domain.ledger.period import (
    PeriodStatus,
    PeriodTransitionError,
    assert_transition_allowed,
    can_post,
    generate_period_name,
    generate_periods,
)


class TestPeriodStatus:
    def test_values(self) -> None:
        assert PeriodStatus.OPEN.value == "open"
        assert PeriodStatus.SOFT_CLOSED.value == "soft_closed"
        assert PeriodStatus.HARD_CLOSED.value == "hard_closed"
        assert PeriodStatus.AUDITED.value == "audited"


class TestCanPost:
    def test_open_period_can_post(self) -> None:
        assert can_post(PeriodStatus.OPEN) is True

    def test_soft_closed_cannot_post_without_override(self) -> None:
        assert can_post(PeriodStatus.SOFT_CLOSED) is False

    def test_soft_closed_can_post_with_admin_override(self) -> None:
        assert can_post(PeriodStatus.SOFT_CLOSED, admin_override=True) is True

    def test_hard_closed_cannot_post(self) -> None:
        assert can_post(PeriodStatus.HARD_CLOSED) is False
        assert can_post(PeriodStatus.HARD_CLOSED, admin_override=True) is False

    def test_audited_cannot_post(self) -> None:
        assert can_post(PeriodStatus.AUDITED) is False


class TestAssertTransitionAllowed:
    def test_open_to_soft_closed(self) -> None:
        assert_transition_allowed(PeriodStatus.OPEN, PeriodStatus.SOFT_CLOSED)  # no raise

    def test_open_to_hard_closed(self) -> None:
        assert_transition_allowed(PeriodStatus.OPEN, PeriodStatus.HARD_CLOSED)

    def test_soft_closed_to_hard_closed(self) -> None:
        assert_transition_allowed(PeriodStatus.SOFT_CLOSED, PeriodStatus.HARD_CLOSED)

    def test_soft_closed_to_open(self) -> None:
        assert_transition_allowed(PeriodStatus.SOFT_CLOSED, PeriodStatus.OPEN)

    def test_hard_closed_to_audited(self) -> None:
        assert_transition_allowed(PeriodStatus.HARD_CLOSED, PeriodStatus.AUDITED)

    def test_open_to_audited_invalid(self) -> None:
        with pytest.raises(PeriodTransitionError):
            assert_transition_allowed(PeriodStatus.OPEN, PeriodStatus.AUDITED)

    def test_audited_to_open_invalid(self) -> None:
        with pytest.raises(PeriodTransitionError):
            assert_transition_allowed(PeriodStatus.AUDITED, PeriodStatus.OPEN)

    def test_hard_closed_to_open_invalid(self) -> None:
        with pytest.raises(PeriodTransitionError):
            assert_transition_allowed(PeriodStatus.HARD_CLOSED, PeriodStatus.OPEN)

    def test_same_status_invalid(self) -> None:
        with pytest.raises(PeriodTransitionError):
            assert_transition_allowed(PeriodStatus.OPEN, PeriodStatus.OPEN)


class TestGeneratePeriodName:
    def test_january(self) -> None:
        assert generate_period_name(2025, 1) == "2025-01"

    def test_december(self) -> None:
        assert generate_period_name(2025, 12) == "2025-12"

    def test_zero_padded(self) -> None:
        assert generate_period_name(2025, 3) == "2025-03"


class TestGeneratePeriods:
    def test_generates_requested_count(self) -> None:
        periods = generate_periods(
            tenant_id="t1",
            functional_currency="USD",
            fiscal_year_start_month=1,
            from_date=date(2025, 1, 1),
            months=3,
        )
        assert len(periods) == 3

    def test_first_period_starts_on_first(self) -> None:
        periods = generate_periods(
            tenant_id="t1",
            functional_currency="USD",
            fiscal_year_start_month=1,
            from_date=date(2025, 1, 1),
            months=1,
        )
        assert periods[0]["start_date"].day == 1

    def test_months_are_contiguous(self) -> None:
        periods = generate_periods(
            tenant_id="t1",
            functional_currency="USD",
            fiscal_year_start_month=1,
            from_date=date(2025, 1, 1),
            months=3,
        )
        for i in range(len(periods) - 1):
            # end of month i + 1 day == start of month i+1
            from datetime import timedelta
            assert periods[i]["end_date"] + timedelta(days=1) == periods[i + 1]["start_date"]

    def test_period_names(self) -> None:
        periods = generate_periods(
            tenant_id="t1",
            functional_currency="USD",
            fiscal_year_start_month=1,
            from_date=date(2025, 1, 1),
            months=3,
        )
        assert [p["name"] for p in periods] == ["2025-01", "2025-02", "2025-03"]

    def test_tenant_id_set_on_each(self) -> None:
        periods = generate_periods(
            tenant_id="tenant-abc",
            functional_currency="USD",
            fiscal_year_start_month=1,
            from_date=date(2025, 1, 1),
            months=2,
        )
        assert all(p["tenant_id"] == "tenant-abc" for p in periods)
