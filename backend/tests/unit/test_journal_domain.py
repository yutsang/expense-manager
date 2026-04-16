"""Unit tests for journal domain — JournalLineInput, validate_balance."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.ledger.journal import (
    JournalBalanceError,
    JournalLineInput,
    validate_balance,
)


class TestJournalLineInput:
    def test_valid_debit_line(self) -> None:
        ln = JournalLineInput(
            account_id="acc-1",
            debit=Decimal("100"),
            credit=Decimal("0"),
            currency="USD",
            functional_debit=Decimal("100"),
            functional_credit=Decimal("0"),
        )
        assert ln.debit == Decimal("100")
        assert ln.credit == Decimal("0")

    def test_valid_credit_line(self) -> None:
        ln = JournalLineInput(
            account_id="acc-2",
            debit=Decimal("0"),
            credit=Decimal("100"),
            currency="USD",
            functional_debit=Decimal("0"),
            functional_credit=Decimal("100"),
        )
        assert ln.credit == Decimal("100")

    def test_both_debit_and_credit_nonzero_raises(self) -> None:
        # A line cannot have both debit and credit — enforced in __post_init__
        with pytest.raises(ValueError, match="both debit and credit"):
            JournalLineInput(
                account_id="acc-1",
                debit=Decimal("50"),
                credit=Decimal("50"),
                currency="USD",
                functional_debit=Decimal("50"),
                functional_credit=Decimal("50"),
            )

    def test_optional_fields_defaults(self) -> None:
        ln = JournalLineInput(
            account_id="acc-1",
            debit=Decimal("100"),
            credit=Decimal("0"),
            currency="USD",
            functional_debit=Decimal("100"),
            functional_credit=Decimal("0"),
        )
        assert ln.description == ""  # empty string default
        assert ln.contact_id is None
        assert ln.fx_rate is None  # None default

    def test_fx_rate_stored(self) -> None:
        ln = JournalLineInput(
            account_id="acc-1",
            debit=Decimal("100"),
            credit=Decimal("0"),
            currency="EUR",
            fx_rate=Decimal("1.09"),
            functional_debit=Decimal("109"),
            functional_credit=Decimal("0"),
        )
        assert ln.fx_rate == Decimal("1.09")

    def test_negative_debit_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            JournalLineInput(
                account_id="acc-1",
                debit=Decimal("-1"),
                credit=Decimal("0"),
                currency="USD",
                functional_debit=Decimal("-1"),
                functional_credit=Decimal("0"),
            )

    def test_negative_credit_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            JournalLineInput(
                account_id="acc-1",
                debit=Decimal("0"),
                credit=Decimal("-50"),
                currency="USD",
                functional_debit=Decimal("0"),
                functional_credit=Decimal("-50"),
            )


class TestValidateBalance:
    def _make_lines(self, debits: list[str], credits: list[str]) -> list[JournalLineInput]:
        lines = []
        for i, (d, c) in enumerate(zip(debits, credits, strict=False)):
            lines.append(
                JournalLineInput(
                    account_id=f"acc-{i}",
                    debit=Decimal(d),
                    credit=Decimal(c),
                    currency="USD",
                    functional_debit=Decimal(d),
                    functional_credit=Decimal(c),
                )
            )
        return lines

    def test_balanced_two_lines(self) -> None:
        lines = self._make_lines(["100", "0"], ["0", "100"])
        validate_balance(lines)  # should not raise

    def test_balanced_multi_line(self) -> None:
        lines = self._make_lines(
            ["300", "0", "0"],
            ["0", "200", "100"],
        )
        validate_balance(lines)

    def test_unbalanced_raises(self) -> None:
        lines = self._make_lines(["100", "0"], ["0", "50"])
        with pytest.raises(JournalBalanceError):
            validate_balance(lines)

    def test_all_zero_raises(self) -> None:
        lines = self._make_lines(["0", "0"], ["0", "0"])
        with pytest.raises(JournalBalanceError, match="zero"):
            validate_balance(lines)

    def test_empty_raises(self) -> None:
        with pytest.raises(JournalBalanceError):
            validate_balance([])

    def test_single_line_raises(self) -> None:
        # A single line with debit=100 credit=0 is unbalanced → should raise
        lines = self._make_lines(["100"], ["0"])
        with pytest.raises(JournalBalanceError):
            validate_balance(lines)

    def test_large_balanced(self) -> None:
        """10-line split entry."""
        lines = [
            JournalLineInput(
                account_id="dr",
                debit=Decimal("10000"),
                credit=Decimal("0"),
                currency="USD",
                functional_debit=Decimal("10000"),
                functional_credit=Decimal("0"),
            )
        ]
        for i in range(10):
            lines.append(
                JournalLineInput(
                    account_id=f"cr-{i}",
                    debit=Decimal("0"),
                    credit=Decimal("1000"),
                    currency="USD",
                    functional_debit=Decimal("0"),
                    functional_credit=Decimal("1000"),
                )
            )
        validate_balance(lines)
