/**
 * Typed API helpers for the Aegis ERP backend.
 * Uses the hand-written @aegis/api-client fetch wrapper.
 *
 * Tenant context is injected via X-Tenant-ID header.
 * Until full auth is wired, we read tenant_id from localStorage (dev only).
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

function getTenantId(): string {
  if (typeof window !== "undefined") {
    return localStorage.getItem("aegis_tenant_id") ?? "dev-tenant";
  }
  return "dev-tenant";
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
    "X-Tenant-ID": getTenantId(),
    "X-Actor-ID": "dev-actor",
  };

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    credentials: "include",
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const err = await res.json();
      detail = err.detail ?? detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface Account {
  id: string;
  code: string;
  name: string;
  type: string;
  subtype: string;
  normal_balance: string;
  parent_id: string | null;
  is_active: boolean;
  is_system: boolean;
  currency: string | null;
  description: string | null;
}

export interface Period {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: string;
}

export interface JournalLine {
  id: string;
  line_no: number;
  account_id: string;
  description: string | null;
  debit: string;
  credit: string;
  currency: string;
  functional_debit: string;
  functional_credit: string;
}

export interface JournalEntry {
  id: string;
  number: string;
  date: string;
  period_id: string;
  description: string;
  status: string;
  source_type: string;
  total_debit: string;
  total_credit: string;
  posted_at: string | null;
  lines: JournalLine[];
}

export interface TrialBalanceRow {
  account_id: string;
  code: string;
  name: string;
  type: string;
  normal_balance: string;
  total_debit: string;
  total_credit: string;
  balance: string;
}

export interface TrialBalanceReport {
  as_of: string;
  tenant_id: string;
  total_debit: string;
  total_credit: string;
  is_balanced: boolean;
  generated_at: string;
  rows: TrialBalanceRow[];
}

export interface GLLine {
  date: string;
  journal_number: string;
  journal_id: string;
  description: string;
  debit: string;
  credit: string;
  running_balance: string;
}

export interface GLReport {
  account_id: string;
  account_code: string;
  account_name: string;
  normal_balance: string;
  from_date: string;
  to_date: string;
  opening_balance: string;
  closing_balance: string;
  lines: GLLine[];
}

// ── Accounts ────────────────────────────────────────────────────────────────

export const accountsApi = {
  list: (includeInactive = false) =>
    request<{ items: Account[]; total: number }>(
      "GET",
      `/v1/accounts?include_inactive=${includeInactive}`
    ),
  get: (id: string) => request<Account>("GET", `/v1/accounts/${id}`),
  create: (body: Partial<Account>) =>
    request<Account>("POST", "/v1/accounts", body),
  update: (id: string, body: { name?: string; description?: string }) =>
    request<Account>("PATCH", `/v1/accounts/${id}`, body),
  archive: (id: string) => request<void>("DELETE", `/v1/accounts/${id}`),
};

// ── Periods ─────────────────────────────────────────────────────────────────

export const periodsApi = {
  list: () => request<{ items: Period[] }>("GET", "/v1/periods"),
};

// ── Journals ─────────────────────────────────────────────────────────────────

export const journalsApi = {
  list: (params?: { status?: string; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.limit) q.set("limit", String(params.limit));
    return request<{ items: JournalEntry[]; next_cursor: string | null }>(
      "GET",
      `/v1/journals?${q}`
    );
  },
  get: (id: string) => request<JournalEntry>("GET", `/v1/journals/${id}`),
  create: (body: unknown) => request<JournalEntry>("POST", "/v1/journals", body),
  post: (id: string) =>
    request<JournalEntry>("POST", `/v1/journals/${id}/post`),
  void: (id: string, reason: string) =>
    request<JournalEntry>("POST", `/v1/journals/${id}/void`, { reason }),
};

// ── Reports ─────────────────────────────────────────────────────────────────

export const reportsApi = {
  trialBalance: (asOf: string) =>
    request<TrialBalanceReport>("GET", `/v1/reports/trial-balance?as_of=${asOf}`),
  generalLedger: (accountId: string, fromDate: string, toDate: string) =>
    request<GLReport>(
      "GET",
      `/v1/reports/general-ledger?account_id=${accountId}&from_date=${fromDate}&to_date=${toDate}`
    ),
};
