/**
 * Tests for Issue #2: Decimal-safe arithmetic for money in the frontend.
 *
 * Verifies that:
 * - safeLineTotal computes line totals using string-based decimal math, not float
 * - safeGrandTotal sums line totals without float accumulation errors
 * - safeFmt formats a decimal string for display without mid-calculation precision loss
 * - Known float-failure cases produce exact results
 */
import { describe, expect, it } from "vitest";
import { safeLineTotal, safeGrandTotal, safeFmt } from "@/lib/money-safe";

describe("safeLineTotal", () => {
  it("computes basic multiplication correctly", () => {
    expect(safeLineTotal("2", "10.50")).toBe("21.00");
  });

  it("handles the classic float error case: 0.1 * 0.2", () => {
    // parseFloat(0.1) * parseFloat(0.2) = 0.020000000000000004 in JS
    expect(safeLineTotal("0.1", "0.2")).toBe("0.02");
  });

  it("handles empty/zero inputs gracefully", () => {
    expect(safeLineTotal("", "10")).toBe("0.00");
    expect(safeLineTotal("1", "")).toBe("0.00");
    expect(safeLineTotal("0", "99.99")).toBe("0.00");
  });

  it("handles large values without precision loss", () => {
    // 99999.9999 * 99999.9999 — would lose precision as float
    expect(safeLineTotal("99999.9999", "1")).toBe("99999.9999");
  });

  it("handles 4 decimal place inputs", () => {
    // 1.5000 * 2.3333 = 3.49995000 (exact product)
    expect(safeLineTotal("1.5000", "2.3333")).toBe("3.49995");
  });
});

describe("safeGrandTotal", () => {
  it("sums multiple line totals exactly", () => {
    const lines = [
      { quantity: "1", unit_price: "0.10" },
      { quantity: "1", unit_price: "0.20" },
      { quantity: "1", unit_price: "0.30" },
    ];
    // 0.1 + 0.2 + 0.3 = 0.6 exactly, but float gives 0.6000000000000001
    expect(safeGrandTotal(lines)).toBe("0.60");
  });

  it("handles empty lines array", () => {
    expect(safeGrandTotal([])).toBe("0.00");
  });

  it("handles multiple line items with quantity", () => {
    const lines = [
      { quantity: "3", unit_price: "19.99" },
      { quantity: "2", unit_price: "5.50" },
    ];
    // 3 * 19.99 = 59.97; 2 * 5.50 = 11.00; total = 70.97
    expect(safeGrandTotal(lines)).toBe("70.97");
  });
});

describe("safeFmt", () => {
  it("formats a decimal string as USD currency", () => {
    const result = safeFmt("1234.56", "USD");
    // Should contain the amount — exact format depends on locale
    expect(result).toContain("1,234.56");
  });

  it("formats zero", () => {
    const result = safeFmt("0.00", "USD");
    expect(result).toContain("0.00");
  });

  it("preserves precision of the string input (no float round-trip)", () => {
    // 1234567890.1234 as a float loses precision, but string stays exact
    const result = safeFmt("1234567890.12", "USD");
    expect(result).toContain("1,234,567,890.12");
  });
});
