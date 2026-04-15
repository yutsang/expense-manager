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

const DEV_TENANT_ID = "00000000-0000-0000-0000-000000000001";

function getTenantId(): string {
  if (typeof window !== "undefined") {
    return localStorage.getItem("aegis_tenant_id") ?? DEV_TENANT_ID;
  }
  return DEV_TENANT_ID;
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
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
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

export interface DashboardData {
  cash_balance: string;
  accounts_receivable: string;
  accounts_payable: string;
  revenue_mtd: string;
  expenses_mtd: string;
  invoices_overdue: number;
  bills_awaiting_approval: number;
  generated_at: string;
}

export interface PLLine {
  account_id: string;
  code: string;
  name: string;
  subtype: string;
  balance: string;
}

export interface PLReport {
  from_date: string;
  to_date: string;
  total_revenue: string;
  total_expenses: string;
  net_profit: string;
  is_profitable: boolean;
  revenue_lines: PLLine[];
  expense_lines: PLLine[];
  generated_at: string;
}

export interface BalanceSheetLine {
  account_id: string;
  code: string;
  name: string;
  subtype: string;
  balance: string;
}

export interface BalanceSheetSection {
  total: string;
  lines: BalanceSheetLine[];
}

export interface BalanceSheetReport {
  as_of: string;
  assets: BalanceSheetSection;
  liabilities: BalanceSheetSection;
  equity: BalanceSheetSection;
  total_liabilities_and_equity: string;
  is_balanced: boolean;
  generated_at: string;
}

export interface AgingRow {
  contact_id: string;
  contact_name: string;
  invoice_number: string;
  issue_date: string;
  due_date: string | null;
  total: string;
  amount_due: string;
  days_overdue: number;
  bucket: string;
}

export interface AgingReport {
  as_of: string;
  current_total: string;
  bucket_1_30: string;
  bucket_31_60: string;
  bucket_61_90: string;
  bucket_90_plus: string;
  grand_total: string;
  rows: AgingRow[];
  generated_at: string;
}

export interface CashFlowLine {
  label: string;
  amount: string;
  is_subtotal: boolean;
}

export interface CashFlowReport {
  from_date: string;
  to_date: string;
  operating_activities: CashFlowLine[];
  investing_activities: CashFlowLine[];
  financing_activities: CashFlowLine[];
  net_operating: string;
  net_investing: string;
  net_financing: string;
  net_change: string;
  opening_cash: string;
  closing_cash: string;
  generated_at: string;
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
  dashboard: () => request<DashboardData>("GET", "/v1/reports/dashboard"),
  pl: (fromDate: string, toDate: string) =>
    request<PLReport>("GET", `/v1/reports/pl?from_date=${fromDate}&to_date=${toDate}`),
  balanceSheet: (asOf: string) =>
    request<BalanceSheetReport>("GET", `/v1/reports/balance-sheet?as_of=${asOf}`),
  arAging: (asOf: string) =>
    request<AgingReport>("GET", `/v1/reports/ar-aging?as_of=${asOf}`),
  apAging: (asOf: string) =>
    request<AgingReport>("GET", `/v1/reports/ap-aging?as_of=${asOf}`),
  cashFlow: (fromDate: string, toDate: string) =>
    request<CashFlowReport>("GET", `/v1/reports/cash-flow?from_date=${fromDate}&to_date=${toDate}`),
};

// ── Contacts ─────────────────────────────────────────────────────────────────

export interface Contact {
  id: string;
  contact_type: string;
  name: string;
  code: string | null;
  email: string | null;
  phone: string | null;
  currency: string;
  is_archived: boolean;
}

export const contactsApi = {
  list: (params?: { contact_type?: string; include_archived?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.contact_type) q.set("contact_type", params.contact_type);
    if (params?.include_archived) q.set("include_archived", "true");
    return request<{ items: Contact[]; next_cursor: string | null }>(
      "GET",
      `/v1/contacts?${q}`
    );
  },
  get: (id: string) => request<Contact>("GET", `/v1/contacts/${id}`),
  create: (body: Partial<Contact> & { contact_type: string; name: string }) =>
    request<Contact>("POST", "/v1/contacts", body),
  update: (id: string, body: Partial<Contact>) =>
    request<Contact>("PATCH", `/v1/contacts/${id}`, body),
  archive: (id: string) => request<void>("DELETE", `/v1/contacts/${id}`),
};

// ── Tax Codes ────────────────────────────────────────────────────────────────

export interface TaxCode {
  id: string;
  code: string;
  name: string;
  rate: string;
  tax_type: string;
  country: string;
  is_active: boolean;
}

export const taxCodesApi = {
  list: (params?: { country?: string; active_only?: boolean }) => {
    const q = new URLSearchParams();
    if (params?.country) q.set("country", params.country);
    if (params?.active_only === false) q.set("active_only", "false");
    return request<{ items: TaxCode[] }>("GET", `/v1/tax-codes?${q}`);
  },
};

// ── Invoices ─────────────────────────────────────────────────────────────────

export interface InvoiceLine {
  id: string;
  line_no: number;
  account_id: string;
  description: string | null;
  quantity: string;
  unit_price: string;
  line_amount: string;
  tax_amount: string;
}

export interface Invoice {
  id: string;
  number: string;
  status: string;
  contact_id: string;
  issue_date: string;
  due_date: string | null;
  currency: string;
  subtotal: string;
  tax_total: string;
  total: string;
  amount_due: string;
  created_at: string;
  lines: InvoiceLine[];
}

export const invoicesApi = {
  list: (params?: { status?: string; contact_id?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.contact_id) q.set("contact_id", params.contact_id);
    return request<{ items: Invoice[]; next_cursor: string | null }>(
      "GET",
      `/v1/invoices?${q}`
    );
  },
  get: (id: string) => request<Invoice>("GET", `/v1/invoices/${id}`),
  create: (body: unknown) => request<Invoice>("POST", "/v1/invoices", body),
  authorise: (id: string) => request<Invoice>("POST", `/v1/invoices/${id}/authorise`),
  void: (id: string) => request<Invoice>("POST", `/v1/invoices/${id}/void`),
};

// ── Bills ────────────────────────────────────────────────────────────────────

export interface BillLine {
  id: string;
  line_no: number;
  account_id: string;
  description: string | null;
  quantity: string;
  unit_price: string;
  line_amount: string;
  tax_amount: string;
}

export interface Bill {
  id: string;
  number: string;
  status: string;
  contact_id: string;
  supplier_reference: string | null;
  issue_date: string;
  due_date: string | null;
  currency: string;
  subtotal: string;
  tax_total: string;
  total: string;
  amount_due: string;
  created_at: string;
  lines: BillLine[];
}

export const billsApi = {
  list: (params?: { status?: string; contact_id?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.contact_id) q.set("contact_id", params.contact_id);
    return request<{ items: Bill[]; next_cursor: string | null }>(
      "GET",
      `/v1/bills?${q}`
    );
  },
  get: (id: string) => request<Bill>("GET", `/v1/bills/${id}`),
  create: (body: unknown) => request<Bill>("POST", "/v1/bills", body),
  submit: (id: string) => request<Bill>("POST", `/v1/bills/${id}/submit`),
  approve: (id: string) => request<Bill>("POST", `/v1/bills/${id}/approve`),
  void: (id: string) => request<Bill>("POST", `/v1/bills/${id}/void`),
};

// ── Auth ─────────────────────────────────────────────────────────────────────

export interface SignupRequest {
  email: string;
  password: string;
  display_name: string;
  tenant_name: string;
  country?: string;
  currency?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface AuthUser {
  id: string;
  email: string;
  display_name: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: AuthUser;
  tenant_ids: string[];
}

export interface SignupResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: AuthUser;
  tenant_id: string;
  tenant_name: string;
}

export const authApi = {
  signup: (body: SignupRequest) => request<SignupResponse>("POST", "/v1/auth/signup", body),
  login: (body: LoginRequest) => request<LoginResponse>("POST", "/v1/auth/login", body),
  logout: () => request<void>("POST", "/v1/auth/logout"),
};

// ── Payments ─────────────────────────────────────────────────────────────────

export interface Payment {
  id: string;
  number: string;
  payment_type: "received" | "made";
  contact_id: string;
  amount: string;
  currency: string;
  fx_rate: string;
  payment_date: string;
  reference: string | null;
  bank_account_ref: string | null;
  status: "pending" | "applied" | "voided";
  created_at: string;
  updated_at: string;
}

export interface PaymentCreate {
  payment_type: "received" | "made";
  contact_id: string;
  amount: string;
  currency?: string;
  fx_rate?: string;
  payment_date: string;
  reference?: string;
  bank_account_ref?: string;
}

export interface PaymentAllocationCreate {
  invoice_id?: string;
  bill_id?: string;
  amount_applied: string;
}

export interface PaymentAllocation {
  id: string;
  payment_id: string;
  invoice_id: string | null;
  bill_id: string | null;
  amount_applied: string;
  created_at: string;
}

export const paymentsApi = {
  list: (params?: { payment_type?: string; status?: string }) => {
    const q = new URLSearchParams();
    if (params?.payment_type) q.set("payment_type", params.payment_type);
    if (params?.status) q.set("status", params.status);
    const qs = q.toString();
    return request<{ items: Payment[]; total: number }>(
      "GET",
      `/v1/payments${qs ? `?${qs}` : ""}`
    );
  },
  create: (body: PaymentCreate) => request<Payment>("POST", "/v1/payments", body),
  get: (id: string) => request<Payment>("GET", `/v1/payments/${id}`),
  allocate: (id: string, body: PaymentAllocationCreate) =>
    request<PaymentAllocation>("POST", `/v1/payments/${id}/allocate`, body),
  void: (id: string, reason?: string) =>
    request<Payment>("POST", `/v1/payments/${id}/void`, { reason: reason ?? "Voided by user" }),
};
