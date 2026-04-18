"""Journal entry domain rules — pure logic, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


class JournalBalanceError(ValueError):
    pass


class JournalStatusError(ValueError):
    pass


@dataclass(frozen=True)
class JournalLineInput:
    account_id: str
    debit: Decimal
    credit: Decimal
    currency: str
    description: str = ""
    functional_debit: Decimal = Decimal("0")
    functional_credit: Decimal = Decimal("0")
    fx_rate: Decimal | None = None
    contact_id: str | None = None

    def __post_init__(self) -> None:
        if self.debit < Decimal("0") or self.credit < Decimal("0"):
            raise ValueError("Debit and credit amounts must be non-negative")
        if self.debit > Decimal("0") and self.credit > Decimal("0"):
            raise ValueError("A line cannot have both debit and credit amounts")


def validate_balance(lines: list[JournalLineInput]) -> None:
    """Assert that functional debits equal functional credits. Raises JournalBalanceError."""
    if not lines:
        raise JournalBalanceError("Journal entry must have at least one line")

    total_debit = sum(ln.functional_debit for ln in lines)
    total_credit = sum(ln.functional_credit for ln in lines)

    if total_debit != total_credit:
        raise JournalBalanceError(
            f"Journal entry is unbalanced: "
            f"functional_debit={total_debit}, functional_credit={total_credit}"
        )
    if total_debit == Decimal("0"):
        raise JournalBalanceError("Journal entry has zero balance — no substantive lines")


def compute_totals(lines: list[JournalLineInput]) -> tuple[Decimal, Decimal]:
    """Return (total_functional_debit, total_functional_credit)."""
    return (
        sum(ln.functional_debit for ln in lines),
        sum(ln.functional_credit for ln in lines),
    )


# Maximum FX rounding difference that will be auto-corrected (in functional currency)
_FX_ROUNDING_THRESHOLD = Decimal("0.01")


def reconcile_fx_rounding(lines: list[JournalLineInput]) -> list[JournalLineInput]:
    """Reconcile FX rounding differences on functional amounts.

    When multiple currencies are converted at different FX rates, individually-
    rounded functional amounts may not sum to exact balance.  This function:

    1. If total_functional_debit == total_functional_credit: returns lines unchanged.
    2. If abs(diff) <= _FX_ROUNDING_THRESHOLD (0.01): allocates the penny difference
       to the line with the largest functional amount (adjusting its functional_debit
       or functional_credit).
    3. If abs(diff) > threshold: raises JournalBalanceError.
    """
    total_debit = sum(ln.functional_debit for ln in lines)
    total_credit = sum(ln.functional_credit for ln in lines)
    diff = total_debit - total_credit

    if diff == Decimal("0"):
        return lines

    abs_diff = abs(diff)
    if abs_diff > _FX_ROUNDING_THRESHOLD:
        raise JournalBalanceError(
            f"FX rounding difference {abs_diff} exceeds threshold "
            f"{_FX_ROUNDING_THRESHOLD}: functional_debit={total_debit}, "
            f"functional_credit={total_credit}"
        )

    # Find the line with the largest functional amount to absorb the adjustment
    best_idx = 0
    best_amount = Decimal("0")
    for i, ln in enumerate(lines):
        ln_amount = max(ln.functional_debit, ln.functional_credit)
        if ln_amount > best_amount:
            best_amount = ln_amount
            best_idx = i

    result = list(lines)
    target = result[best_idx]

    if diff > Decimal("0"):
        # Debits exceed credits — reduce the largest debit or increase the largest credit
        if target.functional_debit > Decimal("0"):
            result[best_idx] = JournalLineInput(
                account_id=target.account_id,
                debit=target.debit,
                credit=target.credit,
                currency=target.currency,
                description=target.description,
                functional_debit=target.functional_debit - diff,
                functional_credit=target.functional_credit,
                fx_rate=target.fx_rate,
                contact_id=target.contact_id,
            )
        else:
            result[best_idx] = JournalLineInput(
                account_id=target.account_id,
                debit=target.debit,
                credit=target.credit,
                currency=target.currency,
                description=target.description,
                functional_debit=target.functional_debit,
                functional_credit=target.functional_credit + diff,
                fx_rate=target.fx_rate,
                contact_id=target.contact_id,
            )
    else:
        # Credits exceed debits — reduce the largest credit or increase the largest debit
        neg_diff = -diff
        if target.functional_credit > Decimal("0"):
            result[best_idx] = JournalLineInput(
                account_id=target.account_id,
                debit=target.debit,
                credit=target.credit,
                currency=target.currency,
                description=target.description,
                functional_debit=target.functional_debit,
                functional_credit=target.functional_credit - neg_diff,
                fx_rate=target.fx_rate,
                contact_id=target.contact_id,
            )
        else:
            result[best_idx] = JournalLineInput(
                account_id=target.account_id,
                debit=target.debit,
                credit=target.credit,
                currency=target.currency,
                description=target.description,
                functional_debit=target.functional_debit + neg_diff,
                functional_credit=target.functional_credit,
                fx_rate=target.fx_rate,
                contact_id=target.contact_id,
            )

    return result
