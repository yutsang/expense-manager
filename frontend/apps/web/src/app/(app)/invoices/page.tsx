"use client";

import { useEffect, useState } from "react";
import { type Account, type Contact, type Invoice, accountsApi, contactsApi, invoicesApi } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";

function fmt(amount: string, currency = "USD") {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(parseFloat(amount));
}

interface LineInput {
  account_id: string;
  description: string;
  quantity: string;
  unit_price: string;
}

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [filterStatus, setFilterStatus] = useState("");

  const [form, setForm] = useState({
    contact_id: "",
    issue_date: new Date().toISOString().slice(0, 10),
    due_date: "",
    currency: "USD",
    lines: [{ account_id: "", description: "", quantity: "1", unit_price: "0" }] as LineInput[],
  });

  const load = async () => {
    try {
      setLoading(true);
      const [invRes, contRes, accRes] = await Promise.all([
        invoicesApi.list(filterStatus ? { status: filterStatus } : {}),
        contactsApi.list({ contact_type: "customer" }),
        accountsApi.list(),
      ]);
      setInvoices(invRes.items);
      setContacts(contRes.items);
      setAccounts(accRes.items.filter((a) => a.type === "revenue"));
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filterStatus]);

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

  const lineTotal = (l: LineInput) =>
    (parseFloat(l.quantity || "0") * parseFloat(l.unit_price || "0")).toFixed(2);

  const grandTotal = form.lines.reduce((s, l) => s + parseFloat(lineTotal(l)), 0).toFixed(2);

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
        })),
      });
      setShowForm(false);
      setForm({
        contact_id: "",
        issue_date: new Date().toISOString().slice(0, 10),
        due_date: "",
        currency: "USD",
        lines: [{ account_id: "", description: "", quantity: "1", unit_price: "0" }],
      });
      await load();
    } catch (e) {
      alert(`Error: ${e}`);
    } finally {
      setSaving(false);
    }
  };

  const handleAuthorise = async (id: string) => {
    try {
      await invoicesApi.authorise(id);
      await load();
    } catch (e) {
      alert(`Error: ${e}`);
    }
  };

  const handleVoid = async (id: string, number: string) => {
    if (!confirm(`Void invoice ${number}?`)) return;
    try {
      await invoicesApi.void(id);
      await load();
    } catch (e) {
      alert(`Error: ${e}`);
    }
  };

  const contactName = (id: string) => contacts.find((c) => c.id === id)?.name ?? id;

  const headerActions = (
    <button
      onClick={() => setShowForm(true)}
      className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
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
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${filterStatus === s ? "bg-primary text-primary-foreground" : "border hover:bg-muted"}`}
          >
            {s || "All"}
          </button>
        ))}
      </div>

      {/* Create form */}
      {showForm && (
        <div className="rounded-xl border bg-card p-6 shadow-sm">
          <h2 className="mb-4 font-semibold">New Invoice</h2>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Customer *</label>
                <select
                  value={form.contact_id}
                  onChange={(e) => setForm({ ...form, contact_id: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  required
                >
                  <option value="">Select customer…</option>
                  {contacts.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Issue Date *</label>
                <input
                  type="date"
                  value={form.issue_date}
                  onChange={(e) => setForm({ ...form, issue_date: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Due Date</label>
                <input
                  type="date"
                  value={form.due_date}
                  onChange={(e) => setForm({ ...form, due_date: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                />
              </div>
            </div>

            {/* Lines */}
            <div>
              <div className="mb-2 grid grid-cols-12 gap-2 text-xs font-medium text-muted-foreground">
                <div className="col-span-4">Account</div>
                <div className="col-span-4">Description</div>
                <div className="col-span-1">Qty</div>
                <div className="col-span-2">Unit Price</div>
                <div className="col-span-1">Total</div>
              </div>
              {form.lines.map((line, i) => (
                <div key={i} className="mb-2 grid grid-cols-12 gap-2 items-center">
                  <div className="col-span-4">
                    <select
                      value={line.account_id}
                      onChange={(e) => updateLine(i, "account_id", e.target.value)}
                      className="w-full rounded-lg border px-2 py-1.5 text-sm"
                      required
                    >
                      <option value="">Account…</option>
                      {accounts.map((a) => (
                        <option key={a.id} value={a.id}>{a.code} {a.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="col-span-4">
                    <input
                      value={line.description}
                      onChange={(e) => updateLine(i, "description", e.target.value)}
                      placeholder="Description"
                      className="w-full rounded-lg border px-2 py-1.5 text-sm"
                    />
                  </div>
                  <div className="col-span-1">
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={line.quantity}
                      onChange={(e) => updateLine(i, "quantity", e.target.value)}
                      className="w-full rounded-lg border px-2 py-1.5 text-sm"
                    />
                  </div>
                  <div className="col-span-2">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      value={line.unit_price}
                      onChange={(e) => updateLine(i, "unit_price", e.target.value)}
                      className="w-full rounded-lg border px-2 py-1.5 text-sm"
                    />
                  </div>
                  <div className="col-span-1 flex items-center gap-1">
                    <span className="text-sm font-mono">{lineTotal(line)}</span>
                    {form.lines.length > 1 && (
                      <button type="button" onClick={() => removeLine(i)} className="text-red-400 hover:text-red-600 ml-auto">✕</button>
                    )}
                  </div>
                </div>
              ))}
              <button type="button" onClick={addLine} className="text-xs text-primary hover:underline">
                + Add line
              </button>
            </div>

            <div className="flex items-center justify-between border-t pt-4">
              <div className="text-right">
                <span className="text-sm text-muted-foreground">Total: </span>
                <span className="text-lg font-bold">{fmt(grandTotal, form.currency)}</span>
              </div>
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                >
                  {saving ? "Saving…" : "Save Draft"}
                </button>
                <button type="button" onClick={() => setShowForm(false)} className="rounded-lg border px-4 py-2 text-sm hover:bg-muted">
                  Cancel
                </button>
              </div>
            </div>
          </form>
        </div>
      )}

      {/* Invoice list */}
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
                <tr key={inv.id} className="hover:bg-muted/20">
                  <td className="px-4 py-3 font-mono text-xs font-medium">{inv.number}</td>
                  <td className="px-4 py-3">{contactName(inv.contact_id)}</td>
                  <td className="px-4 py-3 text-muted-foreground">{inv.issue_date}</td>
                  <td className="px-4 py-3 text-muted-foreground">{inv.due_date ?? "—"}</td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums">{fmt(inv.total, inv.currency)}</td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums">{fmt(inv.amount_due, inv.currency)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={inv.status} />
                  </td>
                  <td className="px-4 py-3 text-right space-x-2">
                    {inv.status === "draft" && (
                      <button
                        onClick={() => handleAuthorise(inv.id)}
                        className="text-xs font-medium text-blue-600 hover:underline"
                      >
                        Authorise
                      </button>
                    )}
                    {inv.status !== "void" && inv.status !== "paid" && (
                      <button
                        onClick={() => handleVoid(inv.id, inv.number)}
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
    </>
  );
}
