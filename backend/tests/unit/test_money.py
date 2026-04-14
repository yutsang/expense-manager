"""Unit tests for the Money value object.

Covers the rules in CLAUDE.md §8:
- No float allowed
- Exact decimal storage (4dp)
- ROUND_HALF_EVEN
- Same-currency arithmetic only
- Multiplication by Decimal/int OK; by float or Money raises
- Equality: same currency AND exact amount
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.money import Currency, CurrencyMismatchError, Money


class TestMoneyConstruction:
    def test_from_string(self) -> None:
        m = Money("1.23", Currency.USD)
        assert m.amount == Decimal("1.2300")

    def test_from_int(self) -> None:
        m = Money(100, Currency.AUD)
        assert m.amount == Decimal("100.0000")

    def test_from_decimal(self) -> None:
        m = Money(Decimal("99.9999"), Currency.GBP)
        assert m.amount == Decimal("99.9999")

    def test_float_raises(self) -> None:
        with pytest.raises(TypeError, match="float is not allowed"):
            Money(1.23, Currency.USD)  # type: ignore[arg-type]

    def test_four_decimal_storage(self) -> None:
        m = Money("1.123456", Currency.USD)  # rounds to 4dp
        assert m.amount == Decimal("1.1235")  # ROUND_HALF_EVEN

    def test_banker_rounding(self) -> None:
        # ROUND_HALF_EVEN: when exactly halfway, round so the last kept digit is even.
        # 2.00005 → 4th decimal = 0 (even) → rounds DOWN → 2.0000
        m_down = Money("2.00005", Currency.USD)
        assert m_down.amount == Decimal("2.0000")
        # 2.00015 → 4th decimal = 1 (odd) → rounds UP → 2.0002
        m_up = Money("2.00015", Currency.USD)
        assert m_up.amount == Decimal("2.0002")

    def test_currency_from_str(self) -> None:
        m = Money("10", "usd")
        assert m.currency == Currency.USD

    def test_unknown_currency_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown currency"):
            Money("10", "XYZ")


class TestMoneyArithmetic:
    def test_add_same_currency(self) -> None:
        a = Money("1.00", Currency.USD)
        b = Money("2.50", Currency.USD)
        assert a + b == Money("3.50", Currency.USD)

    def test_sub_same_currency(self) -> None:
        a = Money("5.00", Currency.USD)
        b = Money("1.25", Currency.USD)
        assert a - b == Money("3.75", Currency.USD)

    def test_add_different_currency_raises(self) -> None:
        with pytest.raises(CurrencyMismatchError):
            Money("1", Currency.USD) + Money("1", Currency.EUR)

    def test_mul_by_decimal(self) -> None:
        m = Money("100", Currency.USD)
        result = m * Decimal("0.15")  # 15% tax
        assert result == Money("15", Currency.USD)

    def test_mul_by_int(self) -> None:
        m = Money("9.99", Currency.USD)
        assert m * 3 == Money("29.97", Currency.USD)

    def test_rmul(self) -> None:
        m = Money("10", Currency.USD)
        assert Decimal("2") * m == Money("20", Currency.USD)

    def test_mul_by_float_raises(self) -> None:
        with pytest.raises(TypeError, match="float"):
            Money("10", Currency.USD) * 1.5  # type: ignore[operator]

    def test_mul_money_by_money_raises(self) -> None:
        with pytest.raises(TypeError, match="Money"):
            Money("10", Currency.USD) * Money("2", Currency.USD)  # type: ignore[operator]

    def test_neg(self) -> None:
        m = Money("5", Currency.USD)
        assert -m == Money("-5", Currency.USD)

    def test_abs(self) -> None:
        m = Money("-3", Currency.USD)
        assert abs(m) == Money("3", Currency.USD)


class TestMoneyComparison:
    def test_equal_same_currency_amount(self) -> None:
        assert Money("1", Currency.USD) == Money("1.0000", Currency.USD)

    def test_not_equal_different_currency(self) -> None:
        assert Money("1", Currency.USD) != Money("1", Currency.EUR)

    def test_not_equal_different_amount(self) -> None:
        assert Money("1", Currency.USD) != Money("2", Currency.USD)

    def test_lt_gt(self) -> None:
        a = Money("1", Currency.USD)
        b = Money("2", Currency.USD)
        assert a < b
        assert b > a

    def test_cross_currency_comparison_raises(self) -> None:
        with pytest.raises(CurrencyMismatchError):
            _ = Money("1", Currency.USD) < Money("1", Currency.EUR)


class TestMoneyUtilities:
    def test_is_zero(self) -> None:
        assert Money("0", Currency.USD).is_zero
        assert not Money("0.0001", Currency.USD).is_zero

    def test_is_positive(self) -> None:
        assert Money("1", Currency.USD).is_positive
        assert not Money("-1", Currency.USD).is_positive

    def test_is_negative(self) -> None:
        assert Money("-1", Currency.USD).is_negative
        assert not Money("0", Currency.USD).is_negative

    def test_display_usd(self) -> None:
        m = Money("1234.5678", Currency.USD)
        assert m.display() == "1234.57 USD"

    def test_display_jpy(self) -> None:
        m = Money("1000", Currency.JPY)
        assert m.display() == "1000 JPY"  # 0 decimal places

    def test_to_storage_str(self) -> None:
        m = Money("1.23", Currency.USD)
        assert m.to_storage_str() == "1.2300"

    def test_zero_factory(self) -> None:
        m = Money.zero(Currency.EUR)
        assert m.is_zero
        assert m.currency == Currency.EUR

    def test_hash(self) -> None:
        d = {Money("1", Currency.USD): "found"}
        assert d[Money("1.0000", Currency.USD)] == "found"
