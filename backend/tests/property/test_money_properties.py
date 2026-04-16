"""Property-based tests for Money arithmetic invariants (Hypothesis).

All rules from CLAUDE.md §8 must hold for all valid inputs.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.money import Currency, CurrencyMismatchError, Money

# Strategy: safe decimal strings (avoid exponents, NaN, Inf)
_decimal_str = st.decimals(
    min_value=Decimal("-1000000"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
).map(str)

_currency = st.sampled_from(list(Currency))


@st.composite
def money(draw: st.DrawFn, currency: Currency | None = None) -> Money:
    c = currency or draw(_currency)
    return Money(draw(_decimal_str), c)


@given(money())
def test_identity_add_zero(m: Money) -> None:
    """m + 0 == m"""
    assert m + Money.zero(m.currency) == m


@given(money())
def test_identity_sub_zero(m: Money) -> None:
    """m - 0 == m"""
    assert m - Money.zero(m.currency) == m


@given(money(), money())
def test_commutativity_same_currency(a: Money, b: Money) -> None:
    """a + b == b + a (same currency)"""
    if a.currency != b.currency:
        try:
            _ = a + b
            raise AssertionError("Should have raised")
        except CurrencyMismatchError:
            pass
    else:
        assert a + b == b + a


@given(money(), money(), money())
@settings(max_examples=200)
def test_associativity_same_currency(a: Money, b: Money, c: Money) -> None:
    """(a + b) + c == a + (b + c) (same currency)"""
    if not (a.currency == b.currency == c.currency):
        return  # skip cross-currency; tested separately
    assert (a + b) + c == a + (b + c)


@given(money())
def test_negation(m: Money) -> None:
    """m + (-m) == 0"""
    assert m + (-m) == Money.zero(m.currency)


@given(money())
def test_abs_non_negative(m: Money) -> None:
    assert abs(m).is_positive or abs(m).is_zero


@given(money())
def test_no_float_in_result(m: Money) -> None:
    """amount is always Decimal, never float."""
    assert isinstance(m.amount, Decimal)


@given(money(), st.integers(min_value=1, max_value=1000))
def test_multiplication_by_int(m: Money, n: int) -> None:
    """m * n == m + m + ... (n times)"""
    result = m * n
    accumulated = Money.zero(m.currency)
    for _ in range(n):
        accumulated = accumulated + m
    # Allow for rounding differences accumulated over n additions (each quantized to 4dp)
    diff = abs((result - accumulated).amount)
    assert diff <= Decimal("0.0001") * n


@given(money(), money())
def test_cross_currency_add_raises(a: Money, b: Money) -> None:
    """Adding different currencies always raises CurrencyMismatchError."""
    if a.currency != b.currency:
        try:
            _ = a + b
            raise AssertionError("Must raise CurrencyMismatchError")
        except CurrencyMismatchError:
            pass


@given(money())
def test_storage_str_parses_back(m: Money) -> None:
    """to_storage_str() roundtrips through Decimal without loss."""
    s = m.to_storage_str()
    assert Money(s, m.currency) == m
