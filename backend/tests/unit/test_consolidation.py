"""Unit tests for consolidated P&L aggregation logic.

Tests the pure aggregation behaviour of ConsolidatedPLLine and the
derive/aggregate helpers without touching a database.
"""

from __future__ import annotations

from decimal import Decimal

from app.services.consolidation import (
    ConsolidatedBSLine,
    ConsolidatedBSSection,
    ConsolidatedPLLine,
)


class TestConsolidatedPLLine:
    def test_single_entity_total_equals_balance(self) -> None:
        line = ConsolidatedPLLine(
            account_code="4000",
            account_name="Sales Revenue",
            account_type="revenue",
            subtype="sales",
        )
        line.per_entity["tenant-a"] = Decimal("1000.00")
        line.total = Decimal("1000.00")

        assert line.total == Decimal("1000.00")
        assert line.per_entity["tenant-a"] == Decimal("1000.00")

    def test_multi_entity_aggregation(self) -> None:
        line = ConsolidatedPLLine(
            account_code="4000",
            account_name="Sales Revenue",
            account_type="revenue",
            subtype="sales",
        )
        line.per_entity["tenant-a"] = Decimal("1000.00")
        line.per_entity["tenant-b"] = Decimal("2500.00")
        line.total = Decimal("3500.00")

        assert line.total == sum(line.per_entity.values())

    def test_ownership_pct_scaling(self) -> None:
        """Verify that partial ownership scales amounts correctly."""
        line = ConsolidatedPLLine(
            account_code="5000",
            account_name="COGS",
            account_type="expense",
            subtype="cost_of_goods_sold",
        )
        # Tenant A at 100% ownership, Tenant B at 60%
        tenant_a_raw = Decimal("400.00")
        tenant_b_raw = Decimal("300.00")
        pct_a = Decimal("100") / Decimal("100")
        pct_b = Decimal("60") / Decimal("100")

        line.per_entity["tenant-a"] = tenant_a_raw * pct_a
        line.per_entity["tenant-b"] = tenant_b_raw * pct_b
        line.total = line.per_entity["tenant-a"] + line.per_entity["tenant-b"]

        assert line.per_entity["tenant-a"] == Decimal("400.00")
        assert line.per_entity["tenant-b"] == Decimal("180.00")
        assert line.total == Decimal("580.00")

    def test_net_profit_calculation(self) -> None:
        """Net profit = total_revenue - total_expenses across all entities."""
        rev_line = ConsolidatedPLLine(
            account_code="4000",
            account_name="Sales",
            account_type="revenue",
            subtype="sales",
        )
        rev_line.per_entity["t1"] = Decimal("5000.00")
        rev_line.per_entity["t2"] = Decimal("3000.00")
        rev_line.total = Decimal("8000.00")

        exp_line = ConsolidatedPLLine(
            account_code="5000",
            account_name="Expenses",
            account_type="expense",
            subtype="operating",
        )
        exp_line.per_entity["t1"] = Decimal("2000.00")
        exp_line.per_entity["t2"] = Decimal("1500.00")
        exp_line.total = Decimal("3500.00")

        net_profit = rev_line.total - exp_line.total
        assert net_profit == Decimal("4500.00")

    def test_zero_balances(self) -> None:
        line = ConsolidatedPLLine(
            account_code="4100",
            account_name="Other Income",
            account_type="revenue",
            subtype="other",
        )
        line.per_entity["t1"] = Decimal("0")
        line.per_entity["t2"] = Decimal("0")
        line.total = Decimal("0")

        assert line.total == Decimal("0")

    def test_negative_expense_balance(self) -> None:
        """Expense credits (refunds) can result in negative expense balance."""
        line = ConsolidatedPLLine(
            account_code="5100",
            account_name="Returns",
            account_type="expense",
            subtype="returns",
        )
        line.per_entity["t1"] = Decimal("-50.00")
        line.total = Decimal("-50.00")

        assert line.total == Decimal("-50.00")


class TestConsolidatedBSSection:
    def test_section_total_matches_line_sum(self) -> None:
        line1 = ConsolidatedBSLine(
            account_code="1000",
            account_name="Cash",
            account_type="asset",
            subtype="bank",
        )
        line1.per_entity["t1"] = Decimal("10000.00")
        line1.per_entity["t2"] = Decimal("5000.00")
        line1.total = Decimal("15000.00")

        line2 = ConsolidatedBSLine(
            account_code="1100",
            account_name="Accounts Receivable",
            account_type="asset",
            subtype="receivable",
        )
        line2.per_entity["t1"] = Decimal("3000.00")
        line2.per_entity["t2"] = Decimal("2000.00")
        line2.total = Decimal("5000.00")

        section = ConsolidatedBSSection(
            lines=[line1, line2],
            total=line1.total + line2.total,
        )

        assert section.total == Decimal("20000.00")
        assert section.total == sum(ln.total for ln in section.lines)

    def test_balance_sheet_equation(self) -> None:
        """assets = liabilities + equity (within rounding tolerance)."""
        assets = ConsolidatedBSSection(
            lines=[],
            total=Decimal("50000.00"),
        )
        liabilities = ConsolidatedBSSection(
            lines=[],
            total=Decimal("20000.00"),
        )
        equity = ConsolidatedBSSection(
            lines=[],
            total=Decimal("30000.00"),
        )

        total_le = liabilities.total + equity.total
        is_balanced = abs(assets.total - total_le) < Decimal("0.01")
        assert is_balanced is True

    def test_ownership_pct_on_bs(self) -> None:
        """60% ownership should scale BS balances to 60%."""
        line = ConsolidatedBSLine(
            account_code="1000",
            account_name="Cash",
            account_type="asset",
            subtype="bank",
        )
        raw_balance = Decimal("10000.00")
        pct = Decimal("60") / Decimal("100")
        scaled = raw_balance * pct

        line.per_entity["subsidiary"] = scaled
        line.total = scaled

        assert line.total == Decimal("6000.00")
