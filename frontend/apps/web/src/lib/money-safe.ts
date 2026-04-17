/**
 * Decimal-safe arithmetic for money in the frontend.
 *
 * Issue #2: Replace parseFloat with string-based decimal math for monetary
 * calculations. Uses integer arithmetic internally to avoid IEEE 754 errors.
 *
 * Per CLAUDE.md §8: "NEVER use float or Number for money."
 * These helpers operate on decimal strings and return decimal strings.
 * parseFloat is only used in safeFmt at the final display step.
 */

/**
 * Multiply two decimal strings and return the result as a decimal string
 * with the appropriate precision. Uses integer arithmetic internally.
 */
function decimalMultiply(a: string, b: string): string {
  if (!a || !b) return "0";

  const [aInt = "0", aFrac = ""] = a.split(".");
  const [bInt = "0", bFrac = ""] = b.split(".");

  const aScale = aFrac.length;
  const bScale = bFrac.length;
  const totalScale = aScale + bScale;

  // Convert to integers by removing decimal points
  const aBI = BigInt(aInt + aFrac || "0");
  const bBI = BigInt(bInt + bFrac || "0");

  const product = aBI * bBI;

  if (totalScale === 0) return product.toString();

  const productStr = product.toString().replace("-", "");
  const isNegative = product < 0n;

  const paddedStr = productStr.padStart(totalScale + 1, "0");
  const intPart = paddedStr.slice(0, paddedStr.length - totalScale);
  const fracPart = paddedStr.slice(paddedStr.length - totalScale);

  // Trim trailing zeros but keep at least 2 decimal places
  let trimmed = fracPart.replace(/0+$/, "");
  if (trimmed.length < 2) trimmed = fracPart.slice(0, 2).padEnd(2, "0");

  return `${isNegative ? "-" : ""}${intPart}.${trimmed}`;
}

/**
 * Add two decimal strings and return the result as a decimal string.
 */
function decimalAdd(a: string, b: string): string {
  const [aInt = "0", aFrac = ""] = a.split(".");
  const [bInt = "0", bFrac = ""] = b.split(".");

  const maxScale = Math.max(aFrac.length, bFrac.length, 2);
  const aPadded = aFrac.padEnd(maxScale, "0");
  const bPadded = bFrac.padEnd(maxScale, "0");

  const aBI = BigInt(aInt + aPadded);
  const bBI = BigInt(bInt + bPadded);
  const sum = aBI + bBI;

  const sumStr = sum.toString().replace("-", "");
  const isNegative = sum < 0n;
  const paddedStr = sumStr.padStart(maxScale + 1, "0");
  const intPart = paddedStr.slice(0, paddedStr.length - maxScale);
  const fracPart = paddedStr.slice(paddedStr.length - maxScale);

  return `${isNegative ? "-" : ""}${intPart}.${fracPart}`;
}

/**
 * Compute a line total from quantity and unit_price strings.
 * Returns a decimal string (e.g. "21.00").
 */
export function safeLineTotal(quantity: string, unitPrice: string): string {
  const q = quantity || "0";
  const p = unitPrice || "0";

  if (q === "0" || p === "0") return "0.00";

  return decimalMultiply(q, p);
}

/**
 * Compute a grand total from an array of line inputs.
 * Each line has { quantity: string, unit_price: string }.
 * Returns a decimal string.
 */
export function safeGrandTotal(
  lines: ReadonlyArray<{ quantity: string; unit_price: string }>,
): string {
  let total = "0.00";
  for (const line of lines) {
    const lineTotal = safeLineTotal(line.quantity, line.unit_price);
    total = decimalAdd(total, lineTotal);
  }
  return total;
}

/**
 * Format a decimal string for display as currency.
 * parseFloat is used ONLY here, at the final rendering step — never mid-calculation.
 */
export function safeFmt(amount: string, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(parseFloat(amount));
}
