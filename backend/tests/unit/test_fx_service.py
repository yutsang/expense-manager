"""Unit tests for FX service sanity bounds logic."""

from __future__ import annotations

from decimal import Decimal

from app.services.fx import FxRateSanityError, _deviation_pct


class TestDeviationPct:
    def test_same_rate_zero_deviation(self) -> None:
        assert _deviation_pct(Decimal("0.65"), Decimal("0.65")) == Decimal("0")

    def test_50_pct_increase(self) -> None:
        result = _deviation_pct(Decimal("0.975"), Decimal("0.65"))
        assert result == Decimal("50")

    def test_50_pct_decrease(self) -> None:
        result = _deviation_pct(Decimal("0.325"), Decimal("0.65"))
        assert result == Decimal("50")

    def test_90_pct_decrease(self) -> None:
        result = _deviation_pct(Decimal("0.065"), Decimal("0.65"))
        assert result == Decimal("90")

    def test_over_90_pct_decrease(self) -> None:
        result = _deviation_pct(Decimal("0.005"), Decimal("0.65"))
        # abs((0.005 - 0.65) / 0.65) * 100 ≈ 99.23...
        assert result > Decimal("90")


class TestFxRateSanityError:
    def test_error_message_format(self) -> None:
        err = FxRateSanityError(
            new_rate=Decimal("0.005"),
            from_currency="USD",
            to_currency="AUD",
            last_rate=Decimal("0.65"),
        )
        assert str(err) == (
            "Rate 0.005 for USD/AUD deviates >90% from last known rate 0.65"
            " — use force=true to override"
        )

    def test_is_value_error(self) -> None:
        err = FxRateSanityError(
            new_rate=Decimal("0.005"),
            from_currency="USD",
            to_currency="AUD",
            last_rate=Decimal("0.65"),
        )
        assert isinstance(err, ValueError)
