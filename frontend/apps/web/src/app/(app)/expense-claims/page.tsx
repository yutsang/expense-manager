"use client";

import { showToast } from "@/lib/toast";
import { useEffect, useState } from "react";
import {
  expenseClaimsApi,
  contactsApi,
  accountsApi,
  taxCodesApi,
  type ExpenseClaim,
  type Contact,
  type Account,
  type TaxCode,
} from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";

const STATUS_TABS = ["all", "draft", "submitted", "approved", "rejected", "paid"] as const;
type StatusTab = (typeof STATUS_TABS)[number];

function fmt(amount: string) {
  return new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD" }).format(
    parseFloat(amount)
  );
}

interface LineInput {
  account_id: string;
  description: string;
  amount: string;
  tax_code_id: string;
}

const EMPTY_LINE: LineInput = { account_id: "", description: "", amount: "", tax_code_id: "" };

export default function ExpenseClaimsPage() {
  const [claims, setClaims] = useState<ExpenseClaim[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [taxCodes, setTaxCodes] = useState<TaxCode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusTab, setStatusTab] = useState<StatusTab>("all");
  const [showCreate, setShowCreate] = useState(false);

  // Create form
  const [createForm, setCreateForm] = useState({
    contact_id: "",
    claim_date: new Date().toISOString().slice(0, 10),
    title: "",
    description: "",
  });
  const [lines, setLines] = useState<LineInput[]>([{ ...EMPTY_LINE }]);
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const params = statusTab !== "all" ? { status: statusTab } : undefined;
      const res = await expenseClaimsApi.list(params);
      setClaims(res.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load expense claims");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [statusTab]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void contactsApi.list({ contact_type: "employee" }).then((r) => setContacts(r.items));
    void accountsApi.list().then((r) => setAccounts(r.items));
    void taxCodesApi.list({}).then((r) => setTaxCodes(r.items));
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      await expenseClaimsApi.create({
        contact_id: createForm.contact_id,
        claim_date: createForm.claim_date,
        title: createForm.title,
        ...(createForm.description ? { description: createForm.description } : {}),
        lines: lines
          .filter((l) => l.account_id && l.amount)
          .map((l) => ({
            account_id: l.account_id,
            amount: l.amount,
            ...(l.description ? { description: l.description } : {}),
            ...(l.tax_code_id ? { tax_code_id: l.tax_code_id } : {}),
          })),
      });
      setCreateForm({
        contact_id: "",
        claim_date: new Date().toISOString().slice(0, 10),
        title: "",
        description: "",
      });
      setLines([{ ...EMPTY_LINE }]);
      setShowCreate(false);
      await load();
    } catch (err: unknown) {
      showToast("error", "Create failed", err instanceof Error ? err.message : undefined);
    } finally {
      setCreating(false);
    }
  }

  async function handleAction(
    claim: ExpenseClaim,
    action: "submit" | "approve" | "reject" | "pay"
  ) {
    const labels: Record<string, string> = {
      submit: "Submit",
      approve: "Approve",
      reject: "Reject",
      pay: "Mark as Paid",
    };
    if (!window.confirm(`${labels[action]} claim "${claim.title}"?`)) return;
    try {
      await expenseClaimsApi[action](claim.id);
      await load();
    } catch (err: unknown) {
      showToast("error", `${action} failed`, err instanceof Error ? err.message : undefined);
    }
  }

  function addLine() {
    setLines((ls) => [...ls, { ...EMPTY_LINE }]);
  }

  function updateLine(idx: number, field: keyof LineInput, value: string) {
    setLines((ls) => ls.map((l, i) => (i === idx ? { ...l, [field]: value } : l)));
  }

  function removeLine(idx: number) {
    setLines((ls) => ls.filter((_, i) => i !== idx));
  }

  const getActions = (claim: ExpenseClaim) => {
    const actions: { label: string; key: "submit" | "approve" | "reject" | "pay"; color: string }[] = [];
    if (claim.status === "draft") actions.push({ label: "Submit", key: "submit", color: "text-blue-600" });
    if (claim.status === "submitted") {
      actions.push({ label: "Approve", key: "approve", color: "text-green-600" });
      actions.push({ label: "Reject", key: "reject", color: "text-red-500" });
    }
    if (claim.status === "approved") actions.push({ label: "Pay", key: "pay", color: "text-purple-600" });
    return actions;
  };

  const contactName = (id: string) => contacts.find((c) => c.id === id)?.name ?? id;

  return (
    <>
      <PageHeader
        title="Expense Claims"
        subtitle="Employee expense reimbursements"
        actions={
          <button
            onClick={() => setShowCreate((v) => !v)}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
          >
            + New Claim
          </button>
        }
      />
      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">
        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}

        {/* Create form */}
        {showCreate && (
          <div className="rounded-lg border bg-card p-4 shadow-sm space-y-4">
            <h2 className="text-sm font-semibold">New Expense Claim</h2>
            <form onSubmit={(e) => void handleCreate(e)} className="space-y-4">
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Employee *</label>
                  <select
                    required
                    value={createForm.contact_id}
                    onChange={(e) => setCreateForm((f) => ({ ...f, contact_id: e.target.value }))}
                    className="w-full rounded-md border px-3 py-1.5 text-sm"
                  >
                    <option value="">— Select —</option>
                    {contacts.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Claim Date *</label>
                  <input
                    required
                    type="date"
                    value={createForm.claim_date}
                    onChange={(e) => setCreateForm((f) => ({ ...f, claim_date: e.target.value }))}
                    className="w-full rounded-md border px-3 py-1.5 text-sm"
                  />
                </div>
                <div className="col-span-2">
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Title *</label>
                  <input
                    required
                    value={createForm.title}
                    onChange={(e) => setCreateForm((f) => ({ ...f, title: e.target.value }))}
                    className="w-full rounded-md border px-3 py-1.5 text-sm"
                    placeholder="Conference travel expenses"
                  />
                </div>
                <div className="col-span-2 sm:col-span-4">
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Description</label>
                  <input
                    value={createForm.description}
                    onChange={(e) => setCreateForm((f) => ({ ...f, description: e.target.value }))}
                    className="w-full rounded-md border px-3 py-1.5 text-sm"
                    placeholder="Optional details"
                  />
                </div>
              </div>

              {/* Lines */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Lines</p>
                  <button
                    type="button"
                    onClick={addLine}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    + Add line
                  </button>
                </div>
                <div className="space-y-2">
                  {lines.map((line, idx) => (
                    <div key={idx} className="grid grid-cols-4 gap-2 sm:grid-cols-8 items-end">
                      <div className="col-span-2">
                        <label className="mb-1 block text-xs text-muted-foreground">Account *</label>
                        <select
                          value={line.account_id}
                          onChange={(e) => updateLine(idx, "account_id", e.target.value)}
                          className="w-full rounded border px-2 py-1.5 text-sm"
                        >
                          <option value="">— Select —</option>
                          {accounts.filter((a) => a.type === "expense").map((a) => (
                            <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
                          ))}
                        </select>
                      </div>
                      <div className="col-span-2">
                        <label className="mb-1 block text-xs text-muted-foreground">Description</label>
                        <input
                          value={line.description}
                          onChange={(e) => updateLine(idx, "description", e.target.value)}
                          className="w-full rounded border px-2 py-1.5 text-sm"
                          placeholder="Flights"
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs text-muted-foreground">Amount *</label>
                        <input
                          type="number"
                          step="0.01"
                          value={line.amount}
                          onChange={(e) => updateLine(idx, "amount", e.target.value)}
                          className="w-full rounded border px-2 py-1.5 text-sm"
                          placeholder="0.00"
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs text-muted-foreground">Tax Code</label>
                        <select
                          value={line.tax_code_id}
                          onChange={(e) => updateLine(idx, "tax_code_id", e.target.value)}
                          className="w-full rounded border px-2 py-1.5 text-sm"
                        >
                          <option value="">— None —</option>
                          {taxCodes.map((t) => (
                            <option key={t.id} value={t.id}>{t.code}</option>
                          ))}
                        </select>
                      </div>
                      <div className="flex items-end pb-1">
                        {lines.length > 1 && (
                          <button
                            type="button"
                            onClick={() => removeLine(idx)}
                            className="text-xs text-red-500 hover:underline"
                          >
                            Remove
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                >
                  {creating ? "Creating…" : "Create Claim"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="rounded-md border px-4 py-1.5 text-sm font-medium hover:bg-muted"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Status tabs */}
        <div className="flex gap-1 border-b">
          {STATUS_TABS.map((s) => (
            <button
              key={s}
              onClick={() => setStatusTab(s)}
              className={`px-4 py-2 text-sm font-medium capitalize transition-colors ${
                statusTab === s
                  ? "border-b-2 border-primary text-primary"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Table */}
        {loading ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            Loading…
          </div>
        ) : claims.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
            No expense claims found.
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b bg-muted/40 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-3">Claim #</th>
                  <th className="px-4 py-3">Employee</th>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Title</th>
                  <th className="px-4 py-3 text-right">Total</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {claims.map((claim) => {
                  const actions = getActions(claim);
                  return (
                    <tr key={claim.id} className="hover:bg-muted/20">
                      <td className="px-4 py-2.5 font-mono text-sm text-muted-foreground">{claim.number}</td>
                      <td className="px-4 py-2.5 text-sm">{contactName(claim.contact_id)}</td>
                      <td className="px-4 py-2.5 text-sm text-muted-foreground">{claim.claim_date}</td>
                      <td className="px-4 py-2.5 text-sm">{claim.title}</td>
                      <td className="px-4 py-2.5 text-right font-mono tabular-nums text-sm">{fmt(claim.total)}</td>
                      <td className="px-4 py-2.5">
                        <StatusBadge status={claim.status} />
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          {actions.map((action) => (
                            <button
                              key={action.key}
                              onClick={() => void handleAction(claim, action.key)}
                              className={`text-xs hover:underline ${action.color}`}
                            >
                              {action.label}
                            </button>
                          ))}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
