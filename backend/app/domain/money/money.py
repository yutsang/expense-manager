"""
Money value object. NEVER use float for money.

Rules (from CLAUDE.md §8):
- All amounts: Decimal only. Constructed from string, int, or Decimal.
- Storage: NUMERIC(19, 4) → 4 decimal places.
- Rounding: ROUND_HALF_EVEN (banker's rounding) at presentation boundaries only.
- Equality: same currency AND exact amount.
- Cross-currency arithmetic raises CurrencyMismatchError.
- Multiplication by Decimal (for FX, tax) is allowed; Money * Money is not.
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal
from typing import Union

from app.domain.money.currency import Currency

_STORAGE_PLACES = Decimal("0.0001")  # 4 decimal places for DB storage
_ZERO = Decimal("0")

Number = Union[Decimal, int, str]


class CurrencyMismatchError(ValueError):
    """Raised when arithmetic is attempted between different currencies."""

    def __init__(self, a: Currency, b: Currency) -> None:
        super().__init__(f"Currency mismatch: {a} vs {b}. Convert to a common currency first.")


class Money:
    """Immutable money value object.

    Stores amount as Decimal rounded to 4 decimal places (NUMERIC(19,4)).
    Presentation rounding (2 or 0 dp per currency) happens at the API/UI layer only.
    """

    __slots__ = ("_amount", "_currency")

    def __init__(self, amount: Number, currency: Currency | str) -> None:
        if isinstance(currency, str):
            currency = Currency.from_str(currency)
        if isinstance(amount, float):
            raise TypeError(
                "float is not allowed for Money. Use str, int, or Decimal. "
                "Example: Money('1.23', Currency.USD)"
            )
        raw = Decimal(amount) if not isinstance(amount, Decimal) else amount
        self._amount: Decimal = raw.quantize(_STORAGE_PLACES, rounding=ROUND_HALF_EVEN)
        self._currency: Currency = currency

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def amount(self) -> Decimal:
        return self._amount

    @property
    def currency(self) -> Currency:
        return self._currency

    # ── Arithmetic ────────────────────────────────────────────────────────────

    def _check_currency(self, other: "Money") -> None:
        if self._currency != other._currency:
            raise CurrencyMismatchError(self._currency, other._currency)

    def __add__(self, other: "Money") -> "Money":
        self._check_currency(other)
        return Money(self._amount + other._amount, self._currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check_currency(other)
        return Money(self._amount - other._amount, self._currency)

    def __mul__(self, factor: Number) -> "Money":
        if isinstance(factor, Money):
            raise TypeError("Cannot multiply Money by Money. Use a plain Decimal factor.")
        if isinstance(factor, float):
            raise TypeError("Cannot multiply Money by float. Use Decimal.")
        f = Decimal(factor) if not isinstance(factor, Decimal) else factor
        return Money(self._amount * f, self._currency)

    def __rmul__(self, factor: Number) -> "Money":
        return self.__mul__(factor)

    def __neg__(self) -> "Money":
        return Money(-self._amount, self._currency)

    def __abs__(self) -> "Money":
        return Money(abs(self._amount), self._currency)

    # ── Comparison ────────────────────────────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._currency == other._currency and self._amount == other._amount

    def __lt__(self, other: "Money") -> bool:
        self._check_currency(other)
        return self._amount < other._amount

    def __le__(self, other: "Money") -> bool:
        self._check_currency(other)
        return self._amount <= other._amount

    def __gt__(self, other: "Money") -> bool:
        self._check_currency(other)
        return self._amount > other._amount

    def __ge__(self, other: "Money") -> bool:
        self._check_currency(other)
        return self._amount >= other._amount

    # ── Utilities ─────────────────────────────────────────────────────────────

    @property
    def is_zero(self) -> bool:
        return self._amount == _ZERO

    @property
    def is_positive(self) -> bool:
        return self._amount > _ZERO

    @property
    def is_negative(self) -> bool:
        return self._amount < _ZERO

    def display(self) -> str:
        """Round to currency-appropriate places for display only."""
        places = Decimal(10) ** -self._currency.decimal_places
        rounded = self._amount.quantize(places, rounding=ROUND_HALF_EVEN)
        return f"{rounded} {self._currency}"

    def to_storage_str(self) -> str:
        """4dp string for JSON serialization (never float)."""
        return str(self._amount)

    @classmethod
    def zero(cls, currency: Currency | str) -> "Money":
        return cls("0", currency)

    # ── Repr / hash ───────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"Money({self._amount!r}, {self._currency!r})"

    def __str__(self) -> str:
        return self.display()

    def __hash__(self) -> int:
        return hash((self._amount, self._currency))
