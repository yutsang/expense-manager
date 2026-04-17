"""Pure depreciation calculation — no I/O, no database.

Supports straight-line and declining-balance methods.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

_QUANTIZE_4 = Decimal("0.0001")


def calculate_depreciation(
    *,
    cost: Decimal,
    residual_value: Decimal,
    useful_life_months: int,
    method: str,
    months_elapsed: int,
) -> Decimal:
    """Calculate depreciation for a single month.

    Args:
        cost: Original acquisition cost.
        residual_value: Estimated salvage value at end of useful life.
        useful_life_months: Total useful life in months.
        method: 'straight_line' or 'declining_balance'.
        months_elapsed: How many months of depreciation have already been recorded
                        (1-indexed: first month = 1).

    Returns:
        Decimal depreciation amount for the month, quantized to 4 decimal places.

    Raises:
        ValueError: If useful_life_months <= 0 or unknown method.
    """
    if useful_life_months <= 0:
        raise ValueError("useful_life_months must be > 0")

    depreciable = cost - residual_value
    if depreciable <= Decimal("0"):
        return Decimal("0.0000")

    if method == "straight_line":
        if months_elapsed > useful_life_months:
            return Decimal("0.0000")
        monthly = (depreciable / useful_life_months).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
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
            return Decimal("0.0000")

        depr = (book_value * rate).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)
        # Clamp so we don't go below residual
        if book_value - depr < residual_value:
            depr = (book_value - residual_value).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

        return depr

    else:
        raise ValueError(f"Unknown depreciation method: {method}")
