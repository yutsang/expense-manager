/**
 * Tax calculation helpers for invoice/bill line items.
 *
 * Uses the same BigInt-based decimal arithmetic as money-safe.ts
 * to avoid IEEE 754 precision loss on tax amounts.
 */

import { safeLineTotal, safeSum } from "@/lib/money-safe";

/**
 * Internal: multiply two decimal strings using integer arithmetic.
 * Duplicated from money-safe.ts (not exported there) to avoid coupling.
 */
function decimalMultiply(a: string, b: string): string {
  if (!a || !b) return "0";

  const [aInt = "0", aFrac = ""] = a.split(".");
  const [bInt = "0", bFrac = ""] = b.split(".");

  const aScale = aFrac.length;
  const bScale = bFrac.length;
  const totalScale = aScale + bScale;

  const aBI = BigInt(aInt + aFrac || "0");
  const bBI = BigInt(bInt + bFrac || "0");

  const product = aBI * bBI;

  if (totalScale === 0) return product.toString();

  const productStr = product.toString().replace("-", "");
  const isNegative = product < 0n;

  const paddedStr = productStr.padStart(totalScale + 1, "0");
  const intPart = paddedStr.slice(0, paddedStr.length - totalScale);
  const fracPart = paddedStr.slice(paddedStr.length - totalScale);

  // Keep at least 2 decimal places
  let trimmed = fracPart.replace(/0+$/, "");
  if (trimmed.length < 2) trimmed = fracPart.slice(0, 2).padEnd(2, "0");

  return `${isNegative ? "-" : ""}${intPart}.${trimmed}`;
}

/**
 * Calculate tax amount for a single line item.
 *
 * @param quantity - decimal string (e.g. "2")
 * @param unitPrice - decimal string (e.g. "100.00")
 * @param taxRate - decimal string between 0 and 1 (e.g. "0.10" for 10%)
 * @returns tax amount as a decimal string (e.g. "20.00")
 */
export function safeLineTax(
  quantity: string,
  unitPrice: string,
  taxRate: string,
): string {
  if (!taxRate || taxRate === "0") return "0.00";
  const lineAmount = safeLineTotal(quantity, unitPrice);
  if (lineAmount === "0.00") return "0.00";
  return decimalMultiply(lineAmount, taxRate);
}

interface InvoiceLine {
  quantity: string;
  unit_price: string;
  tax_rate: string;
}

/**
 * Calculate subtotal, tax total, and grand total for an invoice/bill.
 *
 * @param lines - array of line items with quantity, unit_price, and tax_rate
 * @returns { subtotal, taxTotal, grandTotal } as decimal strings
 */
export function safeInvoiceTotals(
  lines: ReadonlyArray<InvoiceLine>,
): { subtotal: string; taxTotal: string; grandTotal: string } {
  const lineAmounts = lines.map((l) => safeLineTotal(l.quantity, l.unit_price));
  const lineTaxes = lines.map((l) =>
    safeLineTax(l.quantity, l.unit_price, l.tax_rate),
  );

  const subtotal = safeSum(lineAmounts);
  const taxTotal = safeSum(lineTaxes);
  const grandTotal = safeSum([subtotal, taxTotal]);

  return { subtotal, taxTotal, grandTotal };
}
