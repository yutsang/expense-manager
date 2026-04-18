/**
 * Tests for invoice tax calculation helpers (Bug #56).
 *
 * Verifies that:
 * - safeLineTax computes tax per line using decimal-safe arithmetic
 * - safeInvoiceTotals computes subtotal, tax total, and grand total correctly
 * - Known float-failure cases produce exact results
 */
import { describe, expect, it } from "vitest";
import { safeLineTax, safeInvoiceTotals } from "@/lib/invoice-tax";

describe("safeLineTax", () => {
  it("computes 10% tax on a simple line", () => {
    // 2 * 100.00 = 200.00, tax = 200.00 * 0.10 = 20.00
    expect(safeLineTax("2", "100.00", "0.10")).toBe("20.00");
  });

  it("returns 0.00 when tax rate is 0", () => {
    expect(safeLineTax("5", "50.00", "0")).toBe("0.00");
  });

  it("returns 0.00 when tax rate is empty", () => {
    expect(safeLineTax("5", "50.00", "")).toBe("0.00");
  });

  it("returns 0.00 when line amount is 0", () => {
    expect(safeLineTax("0", "100.00", "0.10")).toBe("0.00");
  });

  it("handles fractional tax rates without float error", () => {
    // 1 * 33.33, tax at 7.5% = 33.33 * 0.075 = 2.49975
    const result = safeLineTax("1", "33.33", "0.075");
    expect(result).toBe("2.49975");
  });

  it("handles the classic float error case", () => {
    // 3 * 0.10 = 0.30, tax at 20% = 0.30 * 0.20 = 0.06
    // float: 0.1 * 3 * 0.2 = 0.06000000000000001
    const result = safeLineTax("3", "0.10", "0.20");
    expect(result).toBe("0.06");
  });
});

describe("safeInvoiceTotals", () => {
  it("computes subtotal, tax, and grand total for multiple lines", () => {
    const lines = [
      { quantity: "2", unit_price: "100.00", tax_rate: "0.10" },
      { quantity: "1", unit_price: "50.00", tax_rate: "0.10" },
    ];
    // subtotal: 200 + 50 = 250
    // tax: 20 + 5 = 25
    // grand total: 275
    const { subtotal, taxTotal, grandTotal } = safeInvoiceTotals(lines);
    expect(subtotal).toBe("250.00");
    expect(taxTotal).toBe("25.00");
    expect(grandTotal).toBe("275.00");
  });

  it("handles lines with no tax", () => {
    const lines = [
      { quantity: "3", unit_price: "19.99", tax_rate: "0" },
    ];
    const { subtotal, taxTotal, grandTotal } = safeInvoiceTotals(lines);
    expect(subtotal).toBe("59.97");
    expect(taxTotal).toBe("0.00");
    expect(grandTotal).toBe("59.97");
  });

  it("handles empty lines array", () => {
    const { subtotal, taxTotal, grandTotal } = safeInvoiceTotals([]);
    expect(subtotal).toBe("0.00");
    expect(taxTotal).toBe("0.00");
    expect(grandTotal).toBe("0.00");
  });

  it("handles mixed tax and no-tax lines", () => {
    const lines = [
      { quantity: "1", unit_price: "100.00", tax_rate: "0.10" },
      { quantity: "1", unit_price: "200.00", tax_rate: "0" },
    ];
    const { subtotal, taxTotal, grandTotal } = safeInvoiceTotals(lines);
    expect(subtotal).toBe("300.00");
    expect(taxTotal).toBe("10.00");
    expect(grandTotal).toBe("310.00");
  });
});
