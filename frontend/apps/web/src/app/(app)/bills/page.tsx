"use client";

import { showToast } from "@/lib/toast";
import { useEffect, useState } from "react";
import { type Account, type Bill, type Contact, accountsApi, billsApi, contactsApi } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { safeFmt, safeLineTotal, safeGrandTotal } from "@/lib/money-safe";

function fmt(amount: string, currency = "USD") {
  return safeFmt(amount, currency);
}

interface LineInput {
  account_id: string;
  description: string;
  quantity: string;
  unit_price: string;
}

export default function BillsPage() {
  const [bills, setBills] = useState<Bill[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filterStatus, setFilterStatus] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkProcessing, setBulkProcessing] = useState(false);

  const [form, setForm] = useState({
    contact_id: "",
    issue_date: new Date().toISOString().slice(0, 10),
    due_date: "",
    currency: "USD",
    supplier_reference: "",
    lines: [{ account_id: "", description: "", quantity: "1", unit_price: "0" }] as LineInput[],
  });

  const load = async () => {
    setError(null);
    try {
      setLoading(true);
      const [billRes, contRes, accRes] = await Promise.all([
        billsApi.list(filterStatus ? { status: filterStatus } : {}),
        contactsApi.list({ contact_type: "supplier" }),
        accountsApi.list(),
      ]);
      setBills(billRes.items);
      setContacts(contRes.items);
      setAccounts(accRes.items.filter((a) => a.type === "expense"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load bills");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [filterStatus]);

  const addLine = () =>
    setForm((f) => ({ ...f, lines: [...f.lines, { account_id: "", description: "", quantity: "1", unit_price: "0" }] }));

  const removeLine = (i: number) =>
    setForm((f) => ({ ...f, lines: f.lines.filter((_, idx) => idx !== i) }));

  const updateLine = (i: number, field: keyof LineInput, val: string) =>
    setForm((f) => {
      const lines = [...f.lines];
      const prev = lines[i] as LineInput;
      lines[i] = { account_id: prev.account_id, description: prev.description, quantity: prev.quantity, unit_price: prev.unit_price, [field]: val };
      return { ...f, lines };
    });

  const lineTotal = (l: LineInput) => safeLineTotal(l.quantity, l.unit_price);

  const grandTotal = safeGrandTotal(form.lines);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      await billsApi.create({
        contact_id: form.contact_id,
        issue_date: form.issue_date,
        due_date: form.due_date || null,
        currency: form.currency,
        fx_rate: "1",
        supplier_reference: form.supplier_reference || null,
        lines: form.lines.map((l) => ({
          account_id: l.account_id,
          description: l.description,
          quantity: l.quantity,
          unit_price: l.unit_price,
          discount_pct: "0",
        })),
      });
      setShowForm(false);
      setForm({
        contact_id: "",
        issue_date: new Date().toISOString().slice(0, 10),
        due_date: "",
        currency: "USD",
        supplier_reference: "",
        lines: [{ account_id: "", description: "", quantity: "1", unit_price: "0" }],
      });
      await load();
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const contactName = (id: string) => contacts.find((c) => c.id === id)?.name ?? id;

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedIds.size === bills.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(bills.map((b) => b.id)));
    }
  }

  const selectedBills = bills.filter((b) => selectedIds.has(b.id));
  const allSelectedAwaitingApproval = selectedBills.length > 0 && selectedBills.every((b) => b.status === "awaiting_approval");
  const anySelectedVoidable = selectedBills.length > 0 && selectedBills.every((b) => b.status !== "void" && b.status !== "paid");

  async function handleBulkApprove() {
    if (!allSelectedAwaitingApproval) return;
    setBulkProcessing(true);
    const ids = Array.from(selectedIds);
    const results = await Promise.allSettled(ids.map((id) => billsApi.approve(id)));
    const succeeded = results.filter((r) => r.status === "fulfilled").length;
    const failed = results.filter((r) => r.status === "rejected").length;
    if (failed > 0) {
      showToast("warning", `${succeeded} approved, ${failed} failed`);
    } else {
      showToast("success", `${succeeded} bill(s) approved`);
    }
    setSelectedIds(new Set());
    setBulkProcessing(false);
    await load();
  }

  async function handleBulkVoid() {
    if (!anySelectedVoidable) return;
    if (!confirm(`Void ${selectedIds.size} selected bill(s)?`)) return;
    setBulkProcessing(true);
    const ids = Array.from(selectedIds);
    const results = await Promise.allSettled(ids.map((id) => billsApi.void(id)));
    const succeeded = results.filter((r) => r.status === "fulfilled").length;
    const failed = results.filter((r) => r.status === "rejected").length;
    if (failed > 0) {
      showToast("warning", `${succeeded} voided, ${failed} failed`);
    } else {
      showToast("success", `${succeeded} bill(s) voided`);
    }
    setSelectedIds(new Set());
    setBulkProcessing(false);
    await load();
  }

  const headerActions = (
    <button
      onClick={() => setShowForm(true)}
      className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
    >
      + New Bill
    </button>
  );

  return (
    <>
      <PageHeader
        title="Bills"
        subtitle="Purchase bills from suppliers"
        actions={headerActions}
      />
      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">

        {/* Approval inbox banner */}
        {bills.filter((b) => b.status === "awaiting_approval").length > 0 && (
          <div className="rounded-lg border border-yellow-200 bg-yellow-50 dark:bg-yellow-950/30 dark:border-yellow-800 px-4 py-3 text-sm text-yellow-800 dark:text-yellow-300">
            <strong>{bills.filter((b) => b.status === "awaiting_approval").length}</strong> bill(s) awaiting your approval.
          </div>
        )}

        {/* Filter */}
        <div className="flex gap-3 flex-wrap">
          {["", "draft", "awaiting_approval", "approved", "paid", "void"].map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${filterStatus === s ? "bg-indigo-600 text-white" : "border hover:bg-muted"}`}
            >
              {s.replace("_", " ") || "All"}
            </button>
          ))}
        </div>

        {/* List */}
        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : bills.length === 0 ? (
          <div className="rounded-xl border bg-card p-12 text-center">
            <p className="text-muted-foreground">No bills found.</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40">
                <tr>
                  <th className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      checked={bills.length > 0 && selectedIds.size === bills.length}
                      onChange={toggleSelectAll}
                      disabled={bulkProcessing || bills.length === 0}
                      className="h-4 w-4 rounded border-gray-300"
                    />
                  </th>
                  <th className="px-4 py-3 text-left font-medium">Number</th>
                  <th className="px-4 py-3 text-left font-medium">Supplier</th>
                  <th className="px-4 py-3 text-left font-medium">Supplier Ref</th>
                  <th className="px-4 py-3 text-left font-medium">Bill Date</th>
                  <th className="px-4 py-3 text-left font-medium">Due</th>
                  <th className="px-4 py-3 text-right font-medium">Total</th>
                  <th className="px-4 py-3 text-right font-medium">Due Amount</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {bills.map((bill) => (
                  <tr key={bill.id} className={`hover:bg-muted/20 ${selectedIds.has(bill.id) ? "bg-indigo-50 dark:bg-indigo-950/20" : ""}`}>
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(bill.id)}
                        onChange={() => toggleSelect(bill.id)}
                        disabled={bulkProcessing}
                        className="h-4 w-4 rounded border-gray-300"
                      />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs font-medium">{bill.number}</td>
                    <td className="px-4 py-3">{contactName(bill.contact_id)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{bill.supplier_reference ?? "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{bill.issue_date}</td>
                    <td className="px-4 py-3 text-muted-foreground">{bill.due_date ?? "—"}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">{fmt(bill.total, bill.currency)}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">{fmt(bill.amount_due, bill.currency)}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={bill.status} />
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      {bill.status === "draft" && (
                        <button
                          onClick={() => { void billsApi.submit(bill.id).then(load); }}
                          className="text-xs font-medium text-yellow-600 hover:underline"
                        >
                          Submit
                        </button>
                      )}
                      {bill.status === "awaiting_approval" && (
                        <button
                          onClick={() => { void billsApi.approve(bill.id).then(load); }}
                          className="text-xs font-medium text-blue-600 hover:underline"
                        >
                          Approve
                        </button>
                      )}
                      {bill.status !== "void" && bill.status !== "paid" && (
                        <button
                          onClick={() => { if (confirm(`Void ${bill.number}?`)) void billsApi.void(bill.id).then(load); }}
                          className="text-xs text-muted-foreground hover:text-red-600"
                        >
                          Void
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Floating bulk action bar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-gray-900 px-6 py-3 shadow-xl">
          <div className="flex items-center gap-4 text-sm text-white">
            <span className="font-medium">{selectedIds.size} selected</span>
            <div className="h-4 w-px bg-gray-600" />
            {allSelectedAwaitingApproval && (
              <button
                onClick={() => { void handleBulkApprove(); }}
                disabled={bulkProcessing}
                className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {bulkProcessing ? "Processing..." : "Approve Selected"}
              </button>
            )}
            {anySelectedVoidable && (
              <button
                onClick={() => { void handleBulkVoid(); }}
                disabled={bulkProcessing}
                className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {bulkProcessing ? "Processing..." : "Void Selected"}
              </button>
            )}
            <button
              onClick={() => setSelectedIds(new Set())}
              disabled={bulkProcessing}
              className="text-xs text-gray-400 hover:text-white disabled:opacity-50"
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {/* Slide-over panel */}
      {showForm && (
        <>
          <div
            className="fixed inset-0 bg-black/30 z-40"
            onClick={() => setShowForm(false)}
          />
          <div className="fixed right-0 top-0 h-full w-[480px] bg-background border-l shadow-xl z-50 flex flex-col overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold">New Bill</h2>
              <button
                onClick={() => setShowForm(false)}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
              >
                ✕
              </button>
            </div>
            <form onSubmit={(e) => { void handleCreate(e); }} className="space-y-4 flex-1">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Supplier *</label>
                <select
                  value={form.contact_id}
                  onChange={(e) => setForm({ ...form, contact_id: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm bg-background"
                  required
                >
                  <option value="">Select supplier…</option>
                  {contacts.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Bill Date *</label>
                  <input
                    type="date"
                    value={form.issue_date}
                    onChange={(e) => setForm({ ...form, issue_date: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm bg-background"
                    required
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Due Date</label>
                  <input
                    type="date"
                    value={form.due_date}
                    onChange={(e) => setForm({ ...form, due_date: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm bg-background"
                  />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Supplier Ref</label>
                <input
                  value={form.supplier_reference}
                  onChange={(e) => setForm({ ...form, supplier_reference: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm bg-background"
                  placeholder="INV-2025-001"
                />
              </div>

              {/* Lines */}
              <div>
                <p className="mb-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  Line Items
                </p>
                {form.lines.map((line, i) => (
                  <div key={i} className="mb-3 space-y-2 rounded-lg border p-3 bg-muted/20">
                    <div className="grid grid-cols-2 gap-2">
                      <select
                        value={line.account_id}
                        onChange={(e) => updateLine(i, "account_id", e.target.value)}
                        className="col-span-2 rounded-lg border px-2 py-1.5 text-sm bg-background"
                        required
                      >
                        <option value="">Account…</option>
                        {accounts.map((a) => (
                          <option key={a.id} value={a.id}>{a.code} {a.name}</option>
                        ))}
                      </select>
                      <input
                        value={line.description}
                        onChange={(e) => updateLine(i, "description", e.target.value)}
                        placeholder="Description"
                        className="col-span-2 rounded-lg border px-2 py-1.5 text-sm bg-background"
                      />
                      <div>
                        <label className="text-xs text-muted-foreground">Qty</label>
                        <input
                          type="number"
                          min="0.01"
                          step="0.01"
                          value={line.quantity}
                          onChange={(e) => updateLine(i, "quantity", e.target.value)}
                          className="w-full rounded-lg border px-2 py-1.5 text-sm bg-background"
                        />
                      </div>
                      <div>
                        <label className="text-xs text-muted-foreground">Unit Price</label>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={line.unit_price}
                          onChange={(e) => updateLine(i, "unit_price", e.target.value)}
                          className="w-full rounded-lg border px-2 py-1.5 text-sm bg-background"
                        />
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">
                        Line total: <span className="font-mono font-medium">{lineTotal(line)}</span>
                      </span>
                      {form.lines.length > 1 && (
                        <button
                          type="button"
                          onClick={() => removeLine(i)}
                          className="text-xs text-red-400 hover:text-red-600"
                        >
                          Remove
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                <button type="button" onClick={addLine} className="text-xs text-indigo-600 hover:underline">
                  + Add line
                </button>
              </div>

              <div className="border-t pt-4 flex items-center justify-between">
                <div>
                  <span className="text-sm text-muted-foreground">Total: </span>
                  <span className="text-lg font-bold">{fmt(grandTotal, form.currency)}</span>
                </div>
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={saving}
                    className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60 transition-colors"
                  >
                    {saving ? "Saving…" : "Save Draft"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowForm(false)}
                    className="rounded-lg border px-4 py-2 text-sm hover:bg-muted transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </form>
          </div>
        </>
      )}
    </>
  );
}
