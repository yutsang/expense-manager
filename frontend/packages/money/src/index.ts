/**
 * @aegis/money — frontend Money utilities (Dinero.js v2 with bigint amounts).
 *
 * Rules (CLAUDE.md §8):
 * - NEVER use Number/float for money amounts. Always bigint minor units.
 * - Parse from API JSON (string-quoted decimal) via fromApiString().
 * - Display via formatMoney() only — never toString() on the raw amount.
 * - Cross-currency arithmetic is a type error.
 */
import { dinero, add, subtract, multiply, toDecimal, type Dinero } from "dinero.js";
import {
  USD, AUD, GBP, EUR, HKD, SGD, JPY, CAD, NZD, CNY, MYR, TWD,
} from "@dinero.js/currencies";

export type { Dinero };

const CURRENCY_MAP: Record<string, typeof USD> = {
  USD, AUD, GBP, EUR, HKD, SGD, JPY, CAD, NZD, CNY, MYR, TWD,
};

/**
 * Parse a money object from the API wire format:
 * { "amount": "1234.5600", "currency": "USD" }
 *
 * Converts the decimal string to bigint minor units (e.g., "1234.56" → 123456n for USD).
 */
export function fromApiMoney(apiMoney: { amount: string; currency: string }): Dinero<bigint> {
  const currency = CURRENCY_MAP[apiMoney.currency.toUpperCase()];
  if (!currency) throw new Error(`Unknown currency: ${apiMoney.currency}`);

  const scale = currency.exponent;
  // Parse the decimal string to bigint minor units
  const [intPart = "0", fracPart = ""] = apiMoney.amount.split(".");
  const fracPadded = fracPart.padEnd(scale, "0").slice(0, scale);
  const amount = BigInt(intPart) * BigInt(10 ** scale) + BigInt(fracPadded || "0");

  return dinero({ amount, currency, scale });
}

/**
 * Format a Dinero value for display (e.g., "USD 1,234.56").
 * Never use this for arithmetic — only for rendering.
 */
export function formatMoney(money: Dinero<bigint>, locale = "en-US"): string {
  return toDecimal(money, ({ value, currency }) => {
    const num = parseFloat(value);
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currency.code,
      minimumFractionDigits: currency.exponent,
    }).format(num);
  });
}

export { add, subtract, multiply };
