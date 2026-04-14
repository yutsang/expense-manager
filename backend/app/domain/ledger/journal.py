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
