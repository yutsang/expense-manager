"""Period domain rules — pure logic, no I/O."""
from __future__ import annotations

from datetime import date
from enum import StrEnum


class PeriodStatus(StrEnum):
    OPEN = "open"
    SOFT_CLOSED = "soft_closed"
    HARD_CLOSED = "hard_closed"
    AUDITED = "audited"


# Legal status transitions
_TRANSITIONS: dict[PeriodStatus, set[PeriodStatus]] = {
    PeriodStatus.OPEN: {PeriodStatus.SOFT_CLOSED, PeriodStatus.HARD_CLOSED},
    PeriodStatus.SOFT_CLOSED: {PeriodStatus.OPEN, PeriodStatus.HARD_CLOSED},
    PeriodStatus.HARD_CLOSED: {PeriodStatus.AUDITED},  # reopen requires auditor
    PeriodStatus.AUDITED: set(),
}


class PeriodTransitionError(ValueError):
    pass


def assert_transition_allowed(current: PeriodStatus, target: PeriodStatus) -> None:
    if target not in _TRANSITIONS.get(current, set()):
        raise PeriodTransitionError(
            f"Cannot transition period from '{current}' to '{target}'"
        )


def can_post(status: PeriodStatus, *, admin_override: bool = False) -> bool:
    """Return True if a journal entry can be posted into this period."""
    if status == PeriodStatus.OPEN:
        return True
    return bool(status == PeriodStatus.SOFT_CLOSED and admin_override)


def generate_period_name(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def generate_periods(
    tenant_id: str,
    functional_currency: str,
    fiscal_year_start_month: int,
    from_date: date,
    months: int = 24,
) -> list[dict]:
    """Generate `months` worth of monthly periods starting from `from_date`'s month."""
    import calendar

    periods = []
    year = from_date.year
    month = from_date.month

    for _ in range(months):
        last_day = calendar.monthrange(year, month)[1]
        start = date(year, month, 1)
        end = date(year, month, last_day)
        periods.append({
            "tenant_id": tenant_id,
            "name": generate_period_name(year, month),
            "start_date": start,
            "end_date": end,
            "status": PeriodStatus.OPEN,
        })
        month += 1
        if month > 12:
            month = 1
            year += 1

    return periods
