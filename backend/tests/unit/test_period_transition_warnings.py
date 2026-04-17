"""Unit tests for build_open_items_warning helper in period transition."""

from __future__ import annotations

from decimal import Decimal

from app.services.periods import build_open_items_warning


class TestBuildOpenItemsWarning:
    def test_warning_with_invoices_only(self) -> None:
        result = build_open_items_warning(
            period_id="p-1",
            period_name="2025-01",
            open_invoices=5,
            open_invoices_total=Decimal("2500.0000"),
            open_bills=0,
            open_bills_total=Decimal("0"),
            currency="USD",
        )
        assert result["status"] == "warning"
        assert result["open_invoices"] == 5
        assert result["open_invoices_total"] == "2500.0000"
        assert result["open_bills"] == 0
        assert result["open_bills_total"] == "0"
        assert "5 open invoices" in result["message"]
        assert "USD" in result["message"]

    def test_warning_with_bills_only(self) -> None:
        result = build_open_items_warning(
            period_id="p-2",
            period_name="2025-02",
            open_invoices=0,
            open_invoices_total=Decimal("0"),
            open_bills=3,
            open_bills_total=Decimal("1200.5000"),
            currency="EUR",
        )
        assert result["status"] == "warning"
        assert result["open_invoices"] == 0
        assert result["open_bills"] == 3
        assert result["open_bills_total"] == "1200.5000"
        assert "3 open bills" in result["message"]
        assert "EUR" in result["message"]

    def test_warning_with_both(self) -> None:
        result = build_open_items_warning(
            period_id="p-3",
            period_name="2025-03",
            open_invoices=2,
            open_invoices_total=Decimal("500.0000"),
            open_bills=4,
            open_bills_total=Decimal("900.0000"),
            currency="GBP",
        )
        assert result["status"] == "warning"
        assert result["open_invoices"] == 2
        assert result["open_bills"] == 4
        assert "2 open invoices" in result["message"]
        assert "4 open bills" in result["message"]
        assert "GBP" in result["message"]

    def test_status_is_always_warning(self) -> None:
        result = build_open_items_warning(
            period_id="p-4",
            period_name="2025-04",
            open_invoices=1,
            open_invoices_total=Decimal("100.0000"),
            open_bills=0,
            open_bills_total=Decimal("0"),
            currency="USD",
        )
        assert result["status"] == "warning"

    def test_totals_are_strings(self) -> None:
        result = build_open_items_warning(
            period_id="p-5",
            period_name="2025-05",
            open_invoices=1,
            open_invoices_total=Decimal("999.9900"),
            open_bills=1,
            open_bills_total=Decimal("123.4500"),
            currency="USD",
        )
        assert isinstance(result["open_invoices_total"], str)
        assert isinstance(result["open_bills_total"], str)

    def test_period_id_and_name_preserved(self) -> None:
        result = build_open_items_warning(
            period_id="abc-123",
            period_name="2025-12",
            open_invoices=1,
            open_invoices_total=Decimal("50.0000"),
            open_bills=0,
            open_bills_total=Decimal("0"),
            currency="AUD",
        )
        assert result["period_id"] == "abc-123"
        assert result["period_name"] == "2025-12"

    def test_message_includes_counts_and_currency(self) -> None:
        result = build_open_items_warning(
            period_id="p-6",
            period_name="2025-06",
            open_invoices=10,
            open_invoices_total=Decimal("5000.0000"),
            open_bills=7,
            open_bills_total=Decimal("3500.0000"),
            currency="JPY",
        )
        msg = result["message"]
        assert "10" in msg
        assert "7" in msg
        assert "JPY" in msg
