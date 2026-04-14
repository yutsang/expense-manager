/**
 * @aegis/types — shared TypeScript types mirroring the API domain model.
 *
 * These are hand-written until openapi-ts generates them from the OpenAPI spec (T0.17/client-gen).
 * After client-gen runs, import from @aegis/api-client instead and deprecate these.
 */

// ── Money ─────────────────────────────────────────────────────────────────────

export interface ApiMoney {
  /** String-quoted decimal, 4dp (e.g. "1234.5600"). NEVER a float. */
  amount: string;
  currency: string; // ISO 4217
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export type Role =
  | "owner"
  | "admin"
  | "accountant"
  | "bookkeeper"
  | "approver"
  | "viewer"
  | "auditor"
  | "api_client";

export interface User {
  id: string;
  email: string;
  display_name: string;
  locale: string;
  email_verified_at: string | null;
}

export interface Membership {
  id: string;
  tenant_id: string;
  user_id: string;
  role: Role;
  status: "invited" | "active" | "suspended";
  joined_at: string | null;
}

// ── Tenant ────────────────────────────────────────────────────────────────────

export type TenantStatus = "trial" | "active" | "suspended" | "closed";

export interface Tenant {
  id: string;
  name: string;
  legal_name: string;
  country: string;
  functional_currency: string;
  fiscal_year_start_month: number;
  timezone: string;
  status: TenantStatus;
}

// ── Accounting ────────────────────────────────────────────────────────────────

export type AccountType = "asset" | "liability" | "equity" | "revenue" | "expense";
export type NormalBalance = "debit" | "credit";

export interface Account {
  id: string;
  code: string;
  name: string;
  type: AccountType;
  subtype: string;
  normal_balance: NormalBalance;
  parent_id: string | null;
  is_active: boolean;
  is_system: boolean;
}

export type PeriodStatus = "open" | "soft_closed" | "hard_closed" | "audited";

export interface Period {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: PeriodStatus;
}

export interface JournalLine {
  id: string;
  line_no: number;
  account_id: string;
  description: string | null;
  debit: ApiMoney;
  credit: ApiMoney;
}

export type JournalStatus = "draft" | "posted" | "void";
export type JournalSourceType =
  | "manual"
  | "invoice"
  | "bill"
  | "payment"
  | "bank"
  | "fx_reval"
  | "period_close"
  | "ai_draft";

export interface JournalEntry {
  id: string;
  number: string;
  date: string;
  period_id: string;
  description: string;
  source_type: JournalSourceType;
  status: JournalStatus;
  posted_at: string | null;
  lines: JournalLine[];
}

// ── Pagination ────────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  next_cursor: string | null;
  total: number | null;
}

// ── Errors ────────────────────────────────────────────────────────────────────

/** RFC 9457 Problem Details */
export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
}
