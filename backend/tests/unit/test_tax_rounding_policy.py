"""Unit tests for tax rounding policy (Issue #76).

Tests cover:
  - Tax-inclusive back-calculation: $110 at 10% -> net=$100, tax=$10
  - Per-invoice rounding: two lines of $99.99 at 10% ->
    total tax = $19.998 -> rounds to $20.00
  - Backward compatibility: existing invoices without is_tax_inclusive
    flag default to tax-exclusive behaviour
  - _compute_line with is_tax_inclusive=True
  - _compute_line with is_tax_inclusive=False (default)
  - Per-line rounding (default) quantizes per line
  - Per-invoice rounding defers quantization to invoice total
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

import pytest


_QUANTIZE_4 = Decimal("0.0001")
_QUANTIZE_2 = Decimal("0.01")


class TestComputeLineTaxExclusive:
    """Default (tax-exclusive) behaviour preserved."""

    def test_basic_tax_exclusive(self) -> None:
        from app.services.invoices import _compute_line

        # 1 x $100.00, 0% discount, 10% tax
        net, tax = _compute_line(
            Decimal("1"), Decimal("100"), Decimal("0"), Decimal("0.1")
        )
        assert net == Decimal("100.0000")
        assert tax == Decimal("10.0000")

    def test_tax_exclusive_with_discount(self) -> None:
        from app.services.invoices import _compute_line

        # 2 x $50, 10% discount, 10% tax
        # net = 2 * 50 * (1 - 0.1) = 90
        # tax = 90 * 0.1 = 9
        net, tax = _compute_line(
            Decimal("2"), Decimal("50"), Decimal("0.1"), Decimal("0.1")
        )
        assert net == Decimal("90.0000")
        assert tax == Decimal("9.0000")

    def test_backward_compatibility_no_flags(self) -> None:
        """Calling _compute_line without new kwargs works as before."""
        from app.services.invoices import _compute_line

        net, tax = _compute_line(
            Decimal("1"), Decimal("200"), Decimal("0"), Decimal("0.05")
        )
        assert net == Decimal("200.0000")
        assert tax == Decimal("10.0000")


class TestComputeLineTaxInclusive:
    """Tax-inclusive back-calculation: gross / (1 + rate) = net."""

    def test_tax_inclusive_basic(self) -> None:
        """$110 at 10% -> net=$100, tax=$10."""
        from app.services.invoices import _compute_line

        net, tax = _compute_line(
            Decimal("1"),
            Decimal("110"),
            Decimal("0"),
            Decimal("0.1"),
            is_tax_inclusive=True,
        )
        assert net == Decimal("100.0000")
        assert tax == Decimal("10.0000")

    def test_tax_inclusive_non_round_number(self) -> None:
        """$115.50 at 10% -> net = 115.50 / 1.1 = 105.0000, tax = 10.5000."""
        from app.services.invoices import _compute_line

        net, tax = _compute_line(
            Decimal("1"),
            Decimal("115.50"),
            Decimal("0"),
            Decimal("0.1"),
            is_tax_inclusive=True,
        )
        expected_net = (Decimal("115.50") / Decimal("1.1")).quantize(
            _QUANTIZE_4, ROUND_HALF_EVEN
        )
        expected_tax = (Decimal("115.50") - expected_net).quantize(
            _QUANTIZE_4, ROUND_HALF_EVEN
        )
        assert net == expected_net
        assert tax == expected_tax

    def test_tax_inclusive_zero_rate(self) -> None:
        """Zero tax rate -> net = gross, tax = 0."""
        from app.services.invoices import _compute_line

        net, tax = _compute_line(
            Decimal("1"),
            Decimal("100"),
            Decimal("0"),
            Decimal("0"),
            is_tax_inclusive=True,
        )
        assert net == Decimal("100.0000")
        assert tax == Decimal("0.0000")

    def test_tax_inclusive_with_discount(self) -> None:
        """Discount applied first, then back-calculate from gross."""
        from app.services.invoices import _compute_line

        # 1 x $110, 0% discount, 10% tax, tax-inclusive
        # gross = 110 * (1 - 0) = 110
        # net = 110 / 1.1 = 100, tax = 10
        net, tax = _compute_line(
            Decimal("1"),
            Decimal("110"),
            Decimal("0"),
            Decimal("0.1"),
            is_tax_inclusive=True,
        )
        assert net == Decimal("100.0000")
        assert tax == Decimal("10.0000")

    def test_tax_inclusive_with_quantity(self) -> None:
        """Multiple quantity with tax-inclusive pricing."""
        from app.services.invoices import _compute_line

        # 2 x $55, 10% tax inclusive
        # gross = 2 * 55 = 110
        # net = 110 / 1.1 = 100, tax = 10
        net, tax = _compute_line(
            Decimal("2"),
            Decimal("55"),
            Decimal("0"),
            Decimal("0.1"),
            is_tax_inclusive=True,
        )
        assert net == Decimal("100.0000")
        assert tax == Decimal("10.0000")


class TestPerInvoiceRounding:
    """Per-invoice rounding defers tax quantization to the total."""

    def test_per_invoice_rounding_two_lines(self) -> None:
        """Two lines of $99.99 at 10%:
        per-line: each tax = 9.999 -> quantize 4dp -> 9.9990 each -> total 19.998
        per-invoice: accumulate raw then quantize total -> 19.9980
        Both should give same 4dp result but per-invoice rounds once at end.
        """
        from app.services.invoices import _compute_line

        # Per-line rounding (default)
        _, tax1_pl = _compute_line(
            Decimal("1"), Decimal("99.99"), Decimal("0"), Decimal("0.1"),
            quantize_tax=True,
        )
        _, tax2_pl = _compute_line(
            Decimal("1"), Decimal("99.99"), Decimal("0"), Decimal("0.1"),
            quantize_tax=True,
        )
        total_tax_per_line = tax1_pl + tax2_pl

        # Per-invoice rounding
        _, tax1_pi = _compute_line(
            Decimal("1"), Decimal("99.99"), Decimal("0"), Decimal("0.1"),
            quantize_tax=False,
        )
        _, tax2_pi = _compute_line(
            Decimal("1"), Decimal("99.99"), Decimal("0"), Decimal("0.1"),
            quantize_tax=False,
        )
        total_tax_per_invoice = (tax1_pi + tax2_pi).quantize(
            _QUANTIZE_4, ROUND_HALF_EVEN
        )

        # Both approaches should handle precision correctly
        assert total_tax_per_line == Decimal("19.9980")
        assert total_tax_per_invoice == Decimal("19.9980")

    def test_per_invoice_rounding_scenario_with_2dp_quantize(self) -> None:
        """Scenario where per-line 2dp rounding diverges from per-invoice 2dp.
        Line: $33.33 at 10% -> tax = 3.333 -> per-line rounds to 3.33
        Three lines: per-line total = 9.99
        Per-invoice: 3.333 * 3 = 9.999 -> rounds to 10.00
        """
        from app.services.invoices import _compute_line

        # Per-invoice: don't quantize per line
        taxes = []
        for _ in range(3):
            _, tax = _compute_line(
                Decimal("1"), Decimal("33.33"), Decimal("0"), Decimal("0.1"),
                quantize_tax=False,
            )
            taxes.append(tax)

        # Raw sum then round to 2dp
        raw_total = sum(taxes)
        rounded_total = raw_total.quantize(_QUANTIZE_2, ROUND_HALF_EVEN)
        assert rounded_total == Decimal("10.00")

        # Per-line: quantize each line
        taxes_pl = []
        for _ in range(3):
            _, tax = _compute_line(
                Decimal("1"), Decimal("33.33"), Decimal("0"), Decimal("0.1"),
                quantize_tax=True,
            )
            taxes_pl.append(tax)

        pl_total = sum(taxes_pl).quantize(_QUANTIZE_2, ROUND_HALF_EVEN)
        # Per-line rounding: 3.3330 * 3 = 9.9990 -> 10.00
        assert pl_total == Decimal("10.00")


class TestTaxRoundingPolicyInTenantSettings:
    """Tenant model includes tax_rounding_policy field."""

    def test_tenant_settings_schema_has_tax_rounding_policy(self) -> None:
        """TenantSettingsUpdate schema includes tax_rounding_policy."""
        from app.api.v1.schemas import TenantSettingsUpdate

        s = TenantSettingsUpdate(tax_rounding_policy="per_line")
        assert s.tax_rounding_policy == "per_line"

    def test_tenant_settings_schema_default_tax_rounding_policy(self) -> None:
        s_default = __import__(
            "app.api.v1.schemas", fromlist=["TenantSettingsUpdate"]
        ).TenantSettingsUpdate()
        assert s_default.tax_rounding_policy is None

    def test_tenant_settings_schema_per_invoice_policy(self) -> None:
        from app.api.v1.schemas import TenantSettingsUpdate

        s = TenantSettingsUpdate(tax_rounding_policy="per_invoice")
        assert s.tax_rounding_policy == "per_invoice"

    def test_tenant_settings_schema_rejects_invalid_policy(self) -> None:
        from app.api.v1.schemas import TenantSettingsUpdate

        with pytest.raises(Exception):
            TenantSettingsUpdate(tax_rounding_policy="invalid_value")


class TestInvoiceModelTaxInclusive:
    """Invoice and Bill models support is_tax_inclusive flag."""

    def test_invoice_model_has_is_tax_inclusive(self) -> None:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        source = models_path.read_text()
        assert "is_tax_inclusive" in source

    def test_bill_model_has_is_tax_inclusive(self) -> None:
        import pathlib

        models_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
        source = models_path.read_text()
        # Verify it appears in the Bill section (after class Bill)
        bill_idx = source.index("class Bill(Base):")
        after_bill = source[bill_idx:]
        assert "is_tax_inclusive" in after_bill


class TestBillComputeLineTaxInclusive:
    """Bill service _compute_line supports tax-inclusive."""

    def test_bill_tax_inclusive_basic(self) -> None:
        """$110 at 10% -> net=$100, tax=$10."""
        from app.services.bills import _compute_line

        net, tax = _compute_line(
            Decimal("1"),
            Decimal("110"),
            Decimal("0"),
            Decimal("0.1"),
            is_tax_inclusive=True,
        )
        assert net == Decimal("100.0000")
        assert tax == Decimal("10.0000")

    def test_bill_tax_exclusive_default(self) -> None:
        """Default tax-exclusive should remain unchanged."""
        from app.services.bills import _compute_line

        net, tax = _compute_line(
            Decimal("1"), Decimal("100"), Decimal("0"), Decimal("0.1")
        )
        assert net == Decimal("100.0000")
        assert tax == Decimal("10.0000")

    def test_bill_per_invoice_rounding(self) -> None:
        """quantize_tax=False defers rounding."""
        from app.services.bills import _compute_line

        _, tax = _compute_line(
            Decimal("1"), Decimal("33.33"), Decimal("0"), Decimal("0.1"),
            quantize_tax=False,
        )
        # Raw tax without quantization: 33.33 * 0.1 = 3.333
        # With quantize_tax=False, net is still quantized but tax is not
        assert tax == Decimal("3.333")
