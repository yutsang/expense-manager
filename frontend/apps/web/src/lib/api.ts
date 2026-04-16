/**
 * Typed API helpers for the Aegis ERP backend.
 * Uses the hand-written @aegis/api-client fetch wrapper.
 *
 * Tenant context is injected via X-Tenant-ID header.
 * Until full auth is wired, we read tenant_id from localStorage (dev only).
 */

// Always use relative URLs so requests flow through the Next.js/Vercel proxy.
// In dev: next.config.mjs rewrites /v1/* → localhost:8000/v1/*
// In prod: vercel.json rewrites /v1/* → cloud-run-url/v1/*
// This ensures auth cookies (set on vercel.app) are forwarded correctly.
export const BASE = "";

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

function getToken(): string | null {
  if (typeof window !== "undefined") {
    return localStorage.getItem("aegis_token");
  }
  return null;
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
  };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    credentials: "include",
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });

  if (!res.ok) {
    // 401 means the stored token is missing or expired — clear auth and force re-login
    if (res.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("aegis_token");
      localStorage.removeItem("aegis_tenant_id");
      localStorage.removeItem("aegis-auth");
      document.cookie = "aegis_client=; path=/; max-age=0";
      window.location.href = "/login";
      throw new ApiError(401, "Session expired. Redirecting to login…");
    }
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
  seedDefault: () =>
    request<{ items: Account[]; total: number }>("POST", "/v1/accounts/seed-default"),
  seedDemo: () =>
    request<{ seeded: boolean; reason?: string; contacts?: number; kyc_records?: number; tax_codes?: number }>(
      "POST",
      "/v1/accounts/seed-demo"
    ),
};

// ── Periods ─────────────────────────────────────────────────────────────────

export const periodsApi = {
  list: () => request<{ items: Period[] }>("GET", "/v1/periods"),
  transition: (id: string, status: string) =>
    request<Period>("POST", `/v1/periods/${id}/transition`, { status }),
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
  create: (data: { code: string; name: string; rate: string; tax_type: string; country?: string }) =>
    request<TaxCode>("POST", "/v1/tax-codes", data),
  update: (id: string, data: Partial<{ code: string; name: string; rate: string; tax_type: string; is_active: boolean }>) =>
    request<TaxCode>("PATCH", `/v1/tax-codes/${id}`, data),
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

// ── Bank Reconciliation ──────────────────────────────────────────────────────

export interface BankAccount {
  id: string;
  name: string;
  bank_name: string | null;
  account_number: string | null;
  currency: string;
  coa_account_id: string | null;
  last_reconciled_date: string | null;
  balance: string;
}

export interface BankTransaction {
  id: string;
  bank_account_id: string;
  date: string;
  description: string;
  reference: string | null;
  amount: string;
  is_reconciled: boolean;
  journal_line_id: string | null;
}

export interface BankReconciliation {
  id: string;
  bank_account_id: string;
  reconciliation_date: string;
  statement_balance: string;
  book_balance: string;
  difference: string;
  status: string;
  created_at: string;
}

export const bankReconciliationApi = {
  listAccounts: () => request<BankAccount[]>("GET", "/v1/bank-accounts"),
  createAccount: (data: Partial<BankAccount> & { name: string; currency: string }) =>
    request<BankAccount>("POST", "/v1/bank-accounts", data),
  listTransactions: (accountId: string) =>
    request<BankTransaction[]>("GET", `/v1/bank-accounts/${accountId}/transactions`),
  createTransaction: (accountId: string, data: Partial<BankTransaction> & { date: string; description: string; amount: string }) =>
    request<BankTransaction>("POST", `/v1/bank-accounts/${accountId}/transactions`, data),
  matchTransaction: (txId: string, journalLineId: string) =>
    request<BankTransaction>("POST", `/v1/bank-transactions/${txId}/match`, { journal_line_id: journalLineId }),
  unmatchTransaction: (txId: string) =>
    request<void>("DELETE", `/v1/bank-transactions/${txId}/match`),
  listReconciliations: (accountId: string) =>
    request<BankReconciliation[]>("GET", `/v1/bank-accounts/${accountId}/reconciliations`),
  createReconciliation: (accountId: string, data: { statement_balance: string; reconciliation_date: string }) =>
    request<BankReconciliation>("POST", `/v1/bank-accounts/${accountId}/reconciliations`, data),
};

// ── Expense Claims ───────────────────────────────────────────────────────────

export interface ExpenseClaimLine {
  id: string;
  account_id: string;
  description: string | null;
  amount: string;
  tax_code_id: string | null;
}

export interface ExpenseClaim {
  id: string;
  number: string;
  status: string;
  contact_id: string;
  claim_date: string;
  title: string;
  description: string | null;
  total: string;
  created_at: string;
  lines: ExpenseClaimLine[];
}

export interface ExpenseClaimsListResponse {
  items: ExpenseClaim[];
  next_cursor: string | null;
}

export const expenseClaimsApi = {
  list: (params?: { status?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    const qs = q.toString();
    return request<ExpenseClaimsListResponse>("GET", `/v1/expense-claims${qs ? `?${qs}` : ""}`);
  },
  create: (data: unknown) => request<ExpenseClaim>("POST", "/v1/expense-claims", data),
  get: (id: string) => request<ExpenseClaim>("GET", `/v1/expense-claims/${id}`),
  submit: (id: string) => request<ExpenseClaim>("POST", `/v1/expense-claims/${id}/submit`),
  approve: (id: string) => request<ExpenseClaim>("POST", `/v1/expense-claims/${id}/approve`),
  reject: (id: string) => request<ExpenseClaim>("POST", `/v1/expense-claims/${id}/reject`),
  pay: (id: string) => request<ExpenseClaim>("POST", `/v1/expense-claims/${id}/pay`),
};

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

// ── AI Assistant ──────────────────────────────────────────────────────────────

export type AiMessageRole = "user" | "assistant" | "tool_result";

export interface AiMessage {
  id: string;
  role: AiMessageRole;
  content: string | null;
  tool_calls: unknown[] | null;
  created_at: string;
}

export interface AiConversation {
  id: string;
  title: string;
  created_at: string;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string;
  confirmed_draft_id?: string;
}

// Streaming fetch — returns a ReadableStream
export function streamChat(body: ChatRequest): Promise<Response> {
  return fetch(`/v1/ai/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
}

export const aiApi = {
  listConversations: () => request<AiConversation[]>("GET", "/v1/ai/conversations"),
  getMessages: (conversationId: string) =>
    request<AiMessage[]>("GET", `/v1/ai/conversations/${conversationId}/messages`),
};

// ── AI Cost ───────────────────────────────────────────────────────────────────

export interface CostPeriod {
  input_tokens: number;
  output_tokens: number;
  messages: number;
}

export interface CostSummary {
  today: CostPeriod;
  this_month: CostPeriod;
  by_day: Array<{ date: string; input_tokens: number; output_tokens: number }>;
}

export function getAiCostSummary(): Promise<CostSummary> {
  return request<CostSummary>("GET", "/v1/ai/cost-summary");
}

// ── Anomalies ─────────────────────────────────────────────────────────────────

export interface Anomaly {
  type: "duplicate" | "round_number" | "statistical_outlier";
  severity: "high" | "medium" | "low";
  journal_id: string;
  journal_number: string;
  description: string;
  amount: string;
  detail: string;
}

export function getAnomalies(): Promise<Anomaly[]> {
  return request<Anomaly[]>("GET", "/v1/reports/anomalies");
}

// ── Cash Flow (standalone helper matching task spec) ──────────────────────────

export function getCashFlow(from_date: string, to_date: string): Promise<CashFlowReport> {
  return reportsApi.cashFlow(from_date, to_date);
}

// ── KYC / Sanctions ──────────────────────────────────────────────────────────

export interface KycListItem {
  contact_id: string;
  contact_name: string;
  contact_type: string;
  kyc_id: string | null;
  id_type: string | null;
  id_number: string | null;
  id_expiry_date: string | null;
  poa_type: string | null;
  poa_date: string | null;
  sanctions_status: string;
  sanctions_checked_at: string | null;
  kyc_status: string;
  kyc_approved_at: string | null;
  kyc_approved_by: string | null;
  last_review_date: string | null;
  next_review_date: string | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
  version: number | null;
}

export interface ContactKycResponse {
  id: string;
  contact_id: string;
  id_type: string | null;
  id_number: string | null;
  id_expiry_date: string | null;
  poa_type: string | null;
  poa_date: string | null;
  sanctions_status: string;
  sanctions_checked_at: string | null;
  kyc_status: string;
  kyc_approved_at: string | null;
  kyc_approved_by: string | null;
  last_review_date: string | null;
  next_review_date: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  version: number;
}

export interface KycUpdate {
  id_type?: string | null;
  id_number?: string | null;
  id_expiry_date?: string | null;
  poa_type?: string | null;
  poa_date?: string | null;
  sanctions_status?: string | null;
  kyc_status?: string | null;
  kyc_approved_by?: string | null;
  last_review_date?: string | null;
  next_review_date?: string | null;
  notes?: string | null;
}

export interface KycDashboardAlerts {
  id_expiring_soon: number;
  id_expired: number;
  poa_stale: number;
  pending_kyc: number;
  flagged: number;
}

export const kycApi = {
  list: () => request<KycListItem[]>("GET", "/v1/kyc"),
  get: (contactId: string) => request<ContactKycResponse>("GET", `/v1/kyc/${contactId}`),
  update: (contactId: string, body: KycUpdate) =>
    request<ContactKycResponse>("PUT", `/v1/kyc/${contactId}`, body),
  dashboardAlerts: () => request<KycDashboardAlerts>("GET", "/v1/kyc/dashboard-alerts"),
};

// ── Sanctions ──────────────────────────────────────────────────────────────

export interface SanctionsSnapshot {
  id: string;
  source: string;
  fetched_at: string;
  entry_count: number;
  sha256_hash: string;
  is_active: boolean;
  notes: string | null;
}

export interface SanctionsScreeningResult {
  id: string;
  contact_id: string;
  screened_at: string;
  match_status: "clear" | "potential_match" | "confirmed_match";
  match_score: number;
  matched_name: string | null;
  details: Array<{ entry_id: string; name: string; score: number; source: string }>;
}

export interface SanctionsEntry {
  id: string;
  ref_id: string;
  entity_type: string;
  primary_name: string;
  aliases: Array<{ type: string; name: string }>;
  countries: string[];
  programs: string[];
  remarks: string | null;
  source: string;
}

export const sanctionsApi = {
  snapshots: () => request<SanctionsSnapshot[]>("GET", "/v1/sanctions/snapshots"),
  refresh: () => request<{ status: string }>("POST", "/v1/sanctions/refresh"),
  entries: (params: { q?: string; source?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.source) qs.set("source", params.source);
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.offset !== undefined) qs.set("offset", String(params.offset));
    return request<{ items: SanctionsEntry[]; total: number }>(
      "GET",
      `/v1/sanctions/entries?${qs.toString()}`
    );
  },
  screenContact: (contactId: string) =>
    request<SanctionsScreeningResult>("POST", `/v1/sanctions/screen/${contactId}`),
  getScreenResult: (contactId: string) =>
    request<SanctionsScreeningResult | null>("GET", `/v1/sanctions/screen/${contactId}`),
};

// ── Receipts ──────────────────────────────────────────────────────────────────

export interface ReceiptOcrLine {
  description: string | null;
  quantity: number | null;
  unit_price: number | null;
  amount: number | null;
}

export interface Receipt {
  id: string;
  filename: string;
  content_type: string;
  file_size_kb: number;
  status: string;
  ocr_vendor: string | null;
  ocr_date: string | null;
  ocr_currency: string | null;
  ocr_total: string | null;
  ocr_raw: { line_items?: ReceiptOcrLine[] };
  linked_bill_id: string | null;
  created_at: string;
}

export const receiptsApi = {
  upload: async (file: File): Promise<Receipt> => {
    const form = new FormData();
    form.append("file", file);
    const token = typeof window !== "undefined" ? localStorage.getItem("aegis_token") : null;
    const tenantId =
      typeof window !== "undefined"
        ? (localStorage.getItem("aegis_tenant_id") ?? "00000000-0000-0000-0000-000000000001")
        : "00000000-0000-0000-0000-000000000001";
    const headers: Record<string, string> = { "X-Tenant-ID": tenantId };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${BASE}/v1/receipts`, {
      method: "POST",
      headers,
      body: form,
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json() as Promise<Receipt>;
  },
  list: () => request<Receipt[]>("GET", "/v1/receipts"),
  get: (id: string) => request<Receipt>("GET", `/v1/receipts/${id}`),
  delete: (id: string) => request<void>("DELETE", `/v1/receipts/${id}`),
};

// ── Audit ─────────────────────────────────────────────────────────────────────

export interface AuditEvent {
  id: string;
  tenant_id: string;
  occurred_at: string;
  actor_type: "user" | "system" | "ai" | "integration";
  actor_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  metadata_: Record<string, unknown>;
}

export interface ChainVerification {
  id: string;
  verified_at: string;
  chain_length: number;
  is_valid: boolean;
  break_at_event_id: string | null;
  error_message: string | null;
}

export interface AuditSample {
  id: string;
  number: string;
  date: string;
  description: string;
  debit_total: string;
}

export interface JeTestingReport {
  cutoff_entries: AuditSample[];
  weekend_holiday_posts: AuditSample[];
  round_number_entries: AuditSample[];
  large_entries: AuditSample[];
  reversed_same_day: AuditSample[];
}

export const auditApi = {
  listEvents: (params?: Record<string, string>) =>
    request<{ items: AuditEvent[]; next_cursor: string | null }>(
      "GET",
      `/v1/audit/events${params ? "?" + new URLSearchParams(params) : ""}`
    ),
  getChainVerification: () =>
    request<{ latest: ChainVerification | null; history: ChainVerification[] }>(
      "GET",
      "/v1/audit/chain-verification"
    ),
  triggerVerification: () =>
    request<ChainVerification>("POST", "/v1/audit/chain-verification"),
  sample: (body: {
    method: string;
    size: number;
    seed: number;
    from_date?: string;
    to_date?: string;
  }) => request<AuditSample[]>("POST", "/v1/audit/samples", body),
  jeTestingReport: (from_date: string, to_date: string) =>
    request<JeTestingReport>(
      "GET",
      `/v1/audit/je-testing?from_date=${from_date}&to_date=${to_date}`
    ),
  downloadEvidencePackage: (from_date: string, to_date: string) =>
    fetch(`${BASE}/v1/audit/evidence-package`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ from_date, to_date }),
    }),
};
