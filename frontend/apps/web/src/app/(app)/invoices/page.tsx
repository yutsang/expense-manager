"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BASE, type Account, type Contact, type Invoice, type TaxCode, accountsApi, contactsApi, invoicesApi, taxCodesApi } from "@/lib/api";
import { getTenantIdOrRedirect } from "@/lib/get-tenant-id";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { safeFmt, safeLineTotal, safeGrandTotal, safeSum } from "@/lib/money-safe";
import { safeLineTax, safeInvoiceTotals } from "@/lib/invoice-tax";
import { showToast } from "@/lib/toast";

function fmt(amount: string, currency = "USD") {
  return safeFmt(amount, currency);
}

interface LineInput {
  account_id: string;
  description: string;
  quantity: string;
  unit_price: string;
  tax_code_id: string;
}

export default function InvoicesPage() {
  const router = useRouter();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [taxCodes, setTaxCodes] = useState<TaxCode[]>([]);
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
    lines: [{ account_id: "", description: "", quantity: "1", unit_price: "0", tax_code_id: "" }] as LineInput[],
  });

  const load = async () => {
    setError(null);
    try {
      setLoading(true);
      const [invRes, contRes, accRes, tcRes] = await Promise.all([
        invoicesApi.list(filterStatus ? { status: filterStatus } : {}),
        contactsApi.list({ contact_type: "customer" }),
        accountsApi.list(),
        taxCodesApi.list({ active_only: true }),
      ]);
      setInvoices(invRes.items);
      setContacts(contRes.items);
      setAccounts(accRes.items.filter((a) => a.type === "revenue"));
      setTaxCodes(tcRes.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load invoices");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [filterStatus]);

  const addLine = () =>
    setForm((f) => ({ ...f, lines: [...f.lines, { account_id: "", description: "", quantity: "1", unit_price: "0", tax_code_id: "" }] }));

  const removeLine = (i: number) =>
    setForm((f) => ({ ...f, lines: f.lines.filter((_, idx) => idx !== i) }));

  const updateLine = (i: number, field: keyof LineInput, val: string) =>
    setForm((f) => {
      const lines = [...f.lines];
      const prev = lines[i] as LineInput;
      lines[i] = { account_id: prev.account_id, description: prev.description, quantity: prev.quantity, unit_price: prev.unit_price, tax_code_id: prev.tax_code_id, [field]: val };
      return { ...f, lines };
    });

  const lineTotal = (l: LineInput) => safeLineTotal(l.quantity, l.unit_price);

  const lineTax = (l: LineInput): string => {
    const tc = taxCodes.find((t) => t.id === l.tax_code_id);
    return safeLineTax(l.quantity, l.unit_price, tc?.rate ?? "0");
  };

  const { subtotal, taxTotal, grandTotal } = safeInvoiceTotals(
    form.lines.map((l) => ({
      quantity: l.quantity,
      unit_price: l.unit_price,
      tax_rate: taxCodes.find((t) => t.id === l.tax_code_id)?.rate ?? "0",
    })),
  );

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      await invoicesApi.create({
        contact_id: form.contact_id,
        issue_date: form.issue_date,
        due_date: form.due_date || null,
        currency: form.currency,
        fx_rate: "1",
        lines: form.lines.map((l) => ({
          account_id: l.account_id,
          description: l.description,
          quantity: l.quantity,
          unit_price: l.unit_price,
          discount_pct: "0",
          tax_code_id: l.tax_code_id || null,
        })),
      });
      setShowForm(false);
      setForm({
        contact_id: "",
        issue_date: new Date().toISOString().slice(0, 10),
        due_date: "",
        currency: "USD",
        lines: [{ account_id: "", description: "", quantity: "1", unit_price: "0", tax_code_id: "" }],
      });
      await load();
    } catch (e) {
      showToast("error", "Failed to save invoice", e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleAuthorise = async (id: string) => {
    try {
      await invoicesApi.authorise(id);
      await load();
    } catch (e) {
      showToast("error", "Failed to authorise invoice", e instanceof Error ? e.message : String(e));
    }
  };

  const handleVoid = async (id: string, number: string) => {
    if (!confirm(`Void invoice ${number}?`)) return;
    try {
      await invoicesApi.void(id);
      await load();
    } catch (e) {
      showToast("error", "Failed to void invoice", e instanceof Error ? e.message : String(e));
    }
  };

  const handleDownloadPdf = async (invoiceId: string, number: string) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("aegis_token") : null;
    let tenantId: string;
    try {
      tenantId = getTenantIdOrRedirect(router);
    } catch {
      return;
    }
    const headers: Record<string, string> = { "X-Tenant-ID": tenantId };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await fetch(`${BASE}/v1/invoices/${invoiceId}/pdf`, { headers });
    if (!res.ok) {
      showToast("error", "PDF generation failed", res.statusText);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `invoice-${number}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleSendReminder = async (id: string, number: string) => {
    if (!confirm(`Send payment reminder for invoice ${number}?`)) return;
    try {
      const res = await invoicesApi.sendReminder(id);
      if (res.sent) {
        await load();
      } else {
        showToast("warning", "Reminder not sent", "Email not configured or contact has no email.");
      }
    } catch (e) {
      showToast("error", "Failed to send reminder", e instanceof Error ? e.message : String(e));
    }
  };

  const reminderLabel = (inv: Invoice): string | null => {
    if (!inv.last_reminder_sent_at) return null;
    const diffMs = Date.now() - new Date(inv.last_reminder_sent_at).getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return "Reminded today";
    return `Reminded ${diffDays}d ago`;
  };

  const isOverdue = (inv: Invoice): boolean => {
    if (!inv.due_date) return false;
    return inv.due_date < new Date().toISOString().slice(0, 10) &&
      (inv.status === "sent" || inv.status === "partial");
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
    if (selectedIds.size === invoices.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(invoices.map((inv) => inv.id)));
    }
  }

  const selectedInvoices = invoices.filter((inv) => selectedIds.has(inv.id));
  const allSelectedDraft = selectedInvoices.length > 0 && selectedInvoices.every((inv) => inv.status === "draft");
  const anySelectedVoidable = selectedInvoices.length > 0 && selectedInvoices.every((inv) => inv.status !== "void" && inv.status !== "paid");

  async function handleBulkAuthorise() {
    if (!allSelectedDraft) return;
    setBulkProcessing(true);
    const ids = Array.from(selectedIds);
    const results = await Promise.allSettled(ids.map((id) => invoicesApi.authorise(id)));
    const succeeded = results.filter((r) => r.status === "fulfilled").length;
    const failed = results.filter((r) => r.status === "rejected").length;
    if (failed > 0) {
      showToast("warning", `${succeeded} authorised, ${failed} failed`);
    } else {
      showToast("success", `${succeeded} invoice(s) authorised`);
    }
    setSelectedIds(new Set());
    setBulkProcessing(false);
    await load();
  }

  async function handleBulkVoid() {
    if (!anySelectedVoidable) return;
    if (!confirm(`Void ${selectedIds.size} selected invoice(s)?`)) return;
    setBulkProcessing(true);
    const ids = Array.from(selectedIds);
    const results = await Promise.allSettled(ids.map((id) => invoicesApi.void(id)));
    const succeeded = results.filter((r) => r.status === "fulfilled").length;
    const failed = results.filter((r) => r.status === "rejected").length;
    if (failed > 0) {
      showToast("warning", `${succeeded} voided, ${failed} failed`);
    } else {
      showToast("success", `${succeeded} invoice(s) voided`);
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
      + New Invoice
    </button>
  );

  return (
    <>
      <PageHeader
        title="Invoices"
        subtitle="Sales invoices to customers"
        actions={headerActions}
      />
      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">

        {/* Filter */}
        <div className="flex gap-3">
          {["", "draft", "authorised", "paid", "void"].map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${filterStatus === s ? "bg-indigo-600 text-white" : "border hover:bg-muted"}`}
            >
              {s || "All"}
            </button>
          ))}
        </div>

        {/* Invoice list */}
        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : invoices.length === 0 ? (
          <div className="rounded-xl border bg-card p-12 text-center">
            <p className="text-muted-foreground">No invoices found. Create your first invoice above.</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40">
                <tr>
                  <th className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      checked={invoices.length > 0 && selectedIds.size === invoices.length}
                      onChange={toggleSelectAll}
                      disabled={bulkProcessing || invoices.length === 0}
                      className="h-4 w-4 rounded border-gray-300"
                    />
                  </th>
                  <th className="px-4 py-3 text-left font-medium">Number</th>
                  <th className="px-4 py-3 text-left font-medium">Customer</th>
                  <th className="px-4 py-3 text-left font-medium">Issue Date</th>
                  <th className="px-4 py-3 text-left font-medium">Due Date</th>
                  <th className="px-4 py-3 text-right font-medium">Total</th>
                  <th className="px-4 py-3 text-right font-medium">Amount Due</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {invoices.map((inv) => (
                  <tr key={inv.id} className={`hover:bg-muted/20 ${selectedIds.has(inv.id) ? "bg-indigo-50 dark:bg-indigo-950/20" : ""}`}>
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(inv.id)}
                        onChange={() => toggleSelect(inv.id)}
                        disabled={bulkProcessing}
                        className="h-4 w-4 rounded border-gray-300"
                      />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs font-medium">{inv.number}</td>
                    <td className="px-4 py-3">{contactName(inv.contact_id)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{inv.issue_date}</td>
                    <td className="px-4 py-3 text-muted-foreground">{inv.due_date ?? "—"}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">{fmt(inv.total, inv.currency)}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">{fmt(inv.amount_due, inv.currency)}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-1">
                        <StatusBadge status={inv.status} />
                        {isOverdue(inv) && reminderLabel(inv) && (
                          <span className="text-[10px] text-amber-600 font-medium">
                            {reminderLabel(inv)}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      {inv.status === "draft" && (
                        <button
                          onClick={() => { void handleAuthorise(inv.id); }}
                          className="text-xs font-medium text-blue-600 hover:underline"
                        >
                          Authorise
                        </button>
                      )}
                      {isOverdue(inv) && (
                        <button
                          onClick={() => { void handleSendReminder(inv.id, inv.number); }}
                          className="text-xs font-medium text-amber-600 hover:text-amber-800"
                          title="Send payment reminder"
                        >
                          🔔 Remind
                        </button>
                      )}
                      {inv.status !== "void" && inv.status !== "paid" && (
                        <button
                          onClick={() => { void handleVoid(inv.id, inv.number); }}
                          className="text-xs text-muted-foreground hover:text-red-600"
                        >
                          Void
                        </button>
                      )}
                      <button
                        onClick={() => { void handleDownloadPdf(inv.id, inv.number); }}
                        title="Download PDF"
                        className="inline-flex items-center gap-0.5 text-xs text-muted-foreground hover:text-indigo-600 transition-colors"
                      >
                        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        PDF
                      </button>
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
            {allSelectedDraft && (
              <button
                onClick={() => { void handleBulkAuthorise(); }}
                disabled={bulkProcessing}
                className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {bulkProcessing ? "Processing..." : "Authorise Selected"}
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
              <h2 className="text-lg font-semibold">New Invoice</h2>
              <button
                onClick={() => setShowForm(false)}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
              >
                ✕
              </button>
            </div>
            <form onSubmit={(e) => { void handleCreate(e); }} className="space-y-4 flex-1">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Customer *</label>
                <select
                  value={form.contact_id}
                  onChange={(e) => setForm({ ...form, contact_id: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm bg-background"
                  required
                >
                  <option value="">Select customer…</option>
                  {contacts.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Issue Date *</label>
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
                      <div className="col-span-2">
                        <label className="text-xs text-muted-foreground">Tax Code</label>
                        <select
                          value={line.tax_code_id}
                          onChange={(e) => updateLine(i, "tax_code_id", e.target.value)}
                          className="w-full rounded-lg border px-2 py-1.5 text-sm bg-background"
                        >
                          <option value="">No tax</option>
                          {taxCodes.map((tc) => (
                            <option key={tc.id} value={tc.id}>
                              {tc.code} - {tc.name} ({(parseFloat(tc.rate) * 100).toFixed(1)}%)
                            </option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">
                        Line total: <span className="font-mono font-medium">{lineTotal(line)}</span>
                        {line.tax_code_id && (
                          <> + tax <span className="font-mono font-medium">{lineTax(line)}</span></>
                        )}
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

              <div className="border-t pt-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Subtotal</span>
                  <span className="font-mono">{fmt(subtotal, form.currency)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Tax</span>
                  <span className="font-mono">{fmt(taxTotal, form.currency)}</span>
                </div>
                <div className="flex justify-between text-base font-bold">
                  <span>Total</span>
                  <span className="font-mono">{fmt(grandTotal, form.currency)}</span>
                </div>
              </div>
              <div className="pt-4 flex items-center justify-end">

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
