import * as SecureStore from 'expo-secure-store';

const BASE = 'https://aegis-erp-api-551455410644.asia-southeast1.run.app';

async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync('aegis_access');
}

export async function apiRequest<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const token = await getToken();
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

export async function login(email: string, password: string) {
  const res = await fetch(`${BASE}/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error('Login failed');
  const data = (await res.json()) as {
    access_token: string;
    refresh_token: string;
  };
  await SecureStore.setItemAsync('aegis_access', data.access_token);
  await SecureStore.setItemAsync('aegis_refresh', data.refresh_token);
  return data;
}

export async function logout() {
  await SecureStore.deleteItemAsync('aegis_access');
  await SecureStore.deleteItemAsync('aegis_refresh');
}

// ---- Typed response shapes (minimal, extend as API evolves) ----

export type AccountRow = {
  id: string;
  code: string;
  name: string;
  account_type: string;
  balance?: string;
};

export type JournalEntry = {
  id: string;
  reference: string;
  description: string;
  entry_date: string;
  status: string;
  debit_total: string;
  credit_total: string;
};

export type JournalListResponse = {
  items: JournalEntry[];
  total: number;
  limit: number;
  offset: number;
};

export type Invoice = {
  id: string;
  number: string;
  contact_name: string;
  issue_date: string;
  due_date: string;
  total_amount: string;
  currency: string;
  status: string;
};

export type Bill = {
  id: string;
  number: string;
  vendor_name: string;
  issue_date: string;
  due_date: string;
  total_amount: string;
  currency: string;
  status: string;
};

export type ExpenseClaim = {
  id: string;
  description: string;
  total_amount: string;
  currency: string;
  status: string;
  created_by: string;
  created_at: string;
};

export type ExpenseClaimCreate = {
  description: string;
  currency: string;
  lines: Array<{
    account_id: string;
    description: string;
    amount: string;
    receipt_url?: string;
  }>;
};

export type TrialBalance = {
  accounts: Array<{
    code: string;
    name: string;
    account_type: string;
    debit_total: string;
    credit_total: string;
    balance: string;
  }>;
  generated_at: string;
};

// ---- API helpers ----

export const accountsApi = {
  list: () => apiRequest<AccountRow[]>('GET', '/v1/accounts'),
};

export const journalsApi = {
  list: (limit = 20) =>
    apiRequest<JournalListResponse>('GET', `/v1/journals?limit=${limit}`),
};

export const invoicesApi = {
  list: () => apiRequest<Invoice[]>('GET', '/v1/invoices'),
};

export const billsApi = {
  list: () => apiRequest<Bill[]>('GET', '/v1/bills'),
  approve: (id: string) => apiRequest<Bill>('POST', `/v1/bills/${id}/approve`),
};

export const expenseClaimsApi = {
  list: () => apiRequest<ExpenseClaim[]>('GET', '/v1/expense-claims'),
  create: (body: ExpenseClaimCreate) =>
    apiRequest<ExpenseClaim>('POST', '/v1/expense-claims', body),
  submit: (id: string) =>
    apiRequest<ExpenseClaim>('POST', `/v1/expense-claims/${id}/submit`),
  approve: (id: string) =>
    apiRequest<ExpenseClaim>('POST', `/v1/expense-claims/${id}/approve`),
};

export const reportsApi = {
  trialBalance: () => apiRequest<TrialBalance>('GET', '/v1/reports/trial-balance'),
};
