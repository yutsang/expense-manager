"""Pure depreciation calculation — no I/O, no database.

Supports straight-line and declining-balance methods.
Handles partial first-month pro-rating when acquisition_date is provided.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

_QUANTIZE_4 = Decimal("0.0001")
_ZERO = Decimal("0.0000")


def _prorate_factor(acquisition_date: date, period_end_date: date | None) -> Decimal:
    """Return the fraction of the first month to depreciate.

    If the asset was acquired on day 1, factor is 1. If acquired on the 16th
    of a 30-day month, factor is 15/30 = 0.5.
    """
    year = acquisition_date.year
    month = acquisition_date.month
    days_in_month = calendar.monthrange(year, month)[1]

    if period_end_date is not None and (period_end_date.year, period_end_date.month) != (year, month):
        # If the period ends in a different month, use the full month
            return Decimal("1")

    day = acquisition_date.day
    days_remaining = days_in_month - day + 1  # include the acquisition day
    return (Decimal(str(days_remaining)) / Decimal(str(days_in_month))).quantize(
        _QUANTIZE_4, ROUND_HALF_EVEN
    )


def calculate_depreciation(
    *,
    cost: Decimal,
    residual_value: Decimal,
    useful_life_months: int,
    method: str,
    months_elapsed: int,
    acquisition_date: date | None = None,
    period_end_date: date | None = None,
) -> Decimal:
    """Calculate depreciation for a single month.

    Args:
        cost: Original acquisition cost.
        residual_value: Estimated salvage value at end of useful life.
        useful_life_months: Total useful life in months.
        method: 'straight_line' or 'declining_balance'.
        months_elapsed: How many months of depreciation have already been recorded
                        (1-indexed: first month = 1).
        acquisition_date: The date the asset was acquired. When provided and
            months_elapsed == 1, the first month is pro-rated based on how many
            days remain in the acquisition month.
        period_end_date: End date of the current depreciation period. Used to
            determine whether the acquisition month matches the period month.

    Returns:
        Decimal depreciation amount for the month, quantized to 4 decimal places.

    Raises:
        ValueError: If useful_life_months <= 0 or unknown method.
    """
    if useful_life_months <= 0:
        raise ValueError("useful_life_months must be > 0")

    depreciable = cost - residual_value
    if depreciable <= Decimal("0"):
        return _ZERO

    if method == "straight_line":
        if months_elapsed > useful_life_months:
            return _ZERO
        monthly = (depreciable / useful_life_months).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

        # Pro-rate the first month if acquisition_date is provided
        if months_elapsed == 1 and acquisition_date is not None:
            factor = _prorate_factor(acquisition_date, period_end_date)
            monthly = (monthly * factor).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

        # Clamp: total accumulated must never exceed depreciable amount
        if monthly > depreciable:
            monthly = depreciable.quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

        return monthly

    elif method == "declining_balance":
        # Double declining balance rate
        rate = Decimal("2") / Decimal(str(useful_life_months))

        # Calculate current book value after previous months
        book_value = cost
        for _ in range(1, months_elapsed):
            depr = (book_value * rate).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
            book_value -= depr
            if book_value <= residual_value:
                book_value = residual_value
                break

        if book_value <= residual_value:
            return _ZERO

        depr = (book_value * rate).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

        # Pro-rate the first month if acquisition_date is provided
        if months_elapsed == 1 and acquisition_date is not None:
            factor = _prorate_factor(acquisition_date, period_end_date)
            depr = (depr * factor).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

        # Clamp so we don't go below residual
        if book_value - depr < residual_value:
            depr = (book_value - residual_value).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

        return depr

    else:
        raise ValueError(f"Unknown depreciation method: {method}")
