"""Unit tests for API v1 Pydantic schemas."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.api.v1.schemas import (
    AccountCreate,
    ApiMoney,
    FxRateUpsert,
    JournalCreate,
    JournalLineCreate,
    JournalVoidRequest,
)


class TestApiMoney:
    def test_valid_decimal_string(self) -> None:
        m = ApiMoney(amount="100.50", currency="USD")
        assert m.amount == "100.50"

    def test_zero_allowed(self) -> None:
        m = ApiMoney(amount="0.00", currency="USD")
        assert m.amount == "0.00"

    def test_invalid_amount_raises(self) -> None:
        with pytest.raises(Exception):
            ApiMoney(amount="not-a-number", currency="USD")


class TestAccountCreate:
    def test_valid_asset_account(self) -> None:
        a = AccountCreate(
            code="1000",
            name="Cash",
            type="asset",
            normal_balance="debit",
        )
        assert a.code == "1000"
        assert a.subtype == "other"  # default

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(Exception):
            AccountCreate(
                code="9999",
                name="Bad",
                type="invalid_type",
                normal_balance="debit",
            )

    def test_invalid_normal_balance_raises(self) -> None:
        with pytest.raises(Exception):
            AccountCreate(
                code="9999",
                name="Bad",
                type="asset",
                normal_balance="sideways",
            )

    def test_code_cannot_be_empty(self) -> None:
        with pytest.raises(Exception):
            AccountCreate(code="", name="Cash", type="asset", normal_balance="debit")


class TestJournalLineCreate:
    def test_defaults(self) -> None:
        ln = JournalLineCreate(account_id="acc-1")
        assert ln.debit == "0"
        assert ln.credit == "0"
        assert ln.currency == "USD"
        assert ln.fx_rate == "1"

    def test_negative_debit_raises(self) -> None:
        with pytest.raises(Exception):
            JournalLineCreate(account_id="acc-1", debit="-1")

    def test_negative_credit_raises(self) -> None:
        with pytest.raises(Exception):
            JournalLineCreate(account_id="acc-1", credit="-5")

    def test_negative_fx_rate_raises(self) -> None:
        with pytest.raises(Exception):
            JournalLineCreate(account_id="acc-1", fx_rate="-0.5")


class TestJournalCreate:
    def test_requires_at_least_two_lines(self) -> None:
        from datetime import date
        with pytest.raises(Exception):
            JournalCreate(
                date=date(2025, 1, 1),
                period_id="p1",
                description="Test",
                lines=[JournalLineCreate(account_id="acc-1", debit="100")],
            )

    def test_valid_two_line_entry(self) -> None:
        from datetime import date
        j = JournalCreate(
            date=date(2025, 1, 1),
            period_id="p1",
            description="Test entry",
            lines=[
                JournalLineCreate(account_id="acc-1", debit="100"),
                JournalLineCreate(account_id="acc-2", credit="100"),
            ],
        )
        assert len(j.lines) == 2
        assert j.source_type == "manual"  # default


class TestFxRateUpsert:
    def test_valid(self) -> None:
        from datetime import date
        r = FxRateUpsert(
            from_currency="USD",
            to_currency="EUR",
            rate_date=date(2025, 1, 1),
            rate="0.92",
        )
        assert r.from_currency == "USD"

    def test_zero_rate_raises(self) -> None:
        from datetime import date
        with pytest.raises(Exception):
            FxRateUpsert(
                from_currency="USD",
                to_currency="EUR",
                rate_date=date(2025, 1, 1),
                rate="0",
            )

    def test_negative_rate_raises(self) -> None:
        from datetime import date
        with pytest.raises(Exception):
            FxRateUpsert(
                from_currency="USD",
                to_currency="EUR",
                rate_date=date(2025, 1, 1),
                rate="-1.5",
            )


class TestJournalVoidRequest:
    def test_default_reason_empty(self) -> None:
        v = JournalVoidRequest()
        assert v.reason == ""

    def test_reason_can_be_set(self) -> None:
        v = JournalVoidRequest(reason="Duplicate entry")
        assert v.reason == "Duplicate entry"
