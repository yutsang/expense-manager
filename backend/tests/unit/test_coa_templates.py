"""Tests for CoA templates — T0.13 DoD: US tenant yields 80+ accounts, correct types."""
from __future__ import annotations

from app.infra.templates import get_coa_template, get_tax_codes_template

REQUIRED_SYSTEM_ACCOUNTS = {
    "asset": {"1100"},   # AR
    "liability": {"2000"},  # AP
    "equity": {"3300"},  # Retained Earnings
    "revenue": {"4920"},  # FX Gain
    "expense": {"7020"},  # FX Loss
}
VALID_TYPES = {"asset", "liability", "equity", "revenue", "expense"}
VALID_NORMAL_BALANCES = {"debit", "credit"}


class TestUSTemplate:
    def setup_method(self) -> None:
        self.accounts = get_coa_template("US")

    def test_minimum_account_count(self) -> None:
        assert len(self.accounts) >= 50, f"Expected ≥50 accounts, got {len(self.accounts)}"

    def test_codes_are_unique(self) -> None:
        codes = [a["code"] for a in self.accounts]
        assert len(codes) == len(set(codes)), "Duplicate account codes"

    def test_all_have_required_fields(self) -> None:
        required = {"code", "name", "type", "normal_balance"}
        for acct in self.accounts:
            missing = required - acct.keys()
            assert not missing, f"Account {acct.get('code')} missing: {missing}"

    def test_all_types_valid(self) -> None:
        for acct in self.accounts:
            assert acct["type"] in VALID_TYPES, f"Invalid type for {acct['code']}: {acct['type']}"

    def test_all_normal_balances_valid(self) -> None:
        for acct in self.accounts:
            assert acct["normal_balance"] in VALID_NORMAL_BALANCES

    def test_system_accounts_present(self) -> None:
        by_code = {a["code"]: a for a in self.accounts}
        assert "1100" in by_code, "AR (1100) missing"
        assert "2000" in by_code, "AP (2000) missing"
        assert "3300" in by_code, "Retained Earnings (3300) missing"
        assert by_code["1100"].get("is_system") is True
        assert by_code["2000"].get("is_system") is True
        assert by_code["3300"].get("is_system") is True

    def test_parent_codes_exist(self) -> None:
        codes = {a["code"] for a in self.accounts}
        for acct in self.accounts:
            if "parent_code" in acct:
                assert acct["parent_code"] in codes, (
                    f"{acct['code']} references unknown parent {acct['parent_code']}"
                )

    def test_retained_earnings_is_equity(self) -> None:
        by_code = {a["code"]: a for a in self.accounts}
        re = by_code["3300"]
        assert re["type"] == "equity"
        assert re["normal_balance"] == "credit"

    def test_tax_codes_present(self) -> None:
        tcs = get_tax_codes_template("US")
        assert len(tcs) >= 1
        for tc in tcs:
            assert "code" in tc and "name" in tc and "rate" in tc


class TestAUTemplate:
    def setup_method(self) -> None:
        self.accounts = get_coa_template("AU")

    def test_minimum_account_count(self) -> None:
        assert len(self.accounts) >= 35

    def test_gst_tax_codes(self) -> None:
        tcs = get_tax_codes_template("AU")
        codes = {tc["code"] for tc in tcs}
        assert "GST" in codes
        assert "FRE" in codes


class TestFallback:
    def test_unknown_country_falls_back_to_us(self) -> None:
        template = get_coa_template("ZZ")
        us_template = get_coa_template("US")
        assert template == us_template
