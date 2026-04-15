"use client";

import { useEffect, useState } from "react";
import { type Account, type Bill, type Contact, accountsApi, billsApi, contactsApi } from "@/lib/api";
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

export default function BillsPage() {
  const [bills, setBills] = useState<Bill[]>([]);
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
    supplier_reference: "",
    lines: [{ account_id: "", description: "", quantity: "1", unit_price: "0" }] as LineInput[],
  });

  const load = async () => {
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
      alert(`Error: ${e}`);
    } finally {
      setSaving(false);
    }
  };

  const contactName = (id: string) => contacts.find((c) => c.id === id)?.name ?? id;

  const headerActions = (
    <button
      onClick={() => setShowForm(true)}
      className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
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
        <div className="rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
          <strong>{bills.filter((b) => b.status === "awaiting_approval").length}</strong> bill(s) awaiting your approval.
        </div>
      )}

      {/* Filter */}
      <div className="flex gap-3">
        {["", "draft", "awaiting_approval", "approved", "paid", "void"].map((s) => (
          <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${filterStatus === s ? "bg-primary text-primary-foreground" : "border hover:bg-muted"}`}
          >
            {s.replace("_", " ") || "All"}
          </button>
        ))}
      </div>

      {/* Create form */}
      {showForm && (
        <div className="rounded-xl border bg-card p-6 shadow-sm">
          <h2 className="mb-4 font-semibold">New Bill</h2>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-4 gap-4">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Supplier *</label>
                <select
                  value={form.contact_id}
                  onChange={(e) => setForm({ ...form, contact_id: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  required
                >
                  <option value="">Select supplier…</option>
                  {contacts.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Bill Date *</label>
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
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Supplier Ref</label>
                <input
                  value={form.supplier_reference}
                  onChange={(e) => setForm({ ...form, supplier_reference: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  placeholder="INV-2025-001"
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
              <div>
                <span className="text-sm text-muted-foreground">Total: </span>
                <span className="text-lg font-bold">{fmt(grandTotal, form.currency)}</span>
              </div>
              <div className="flex gap-2">
                <button type="submit" disabled={saving} className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
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

      {/* List */}
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
                <tr key={bill.id} className="hover:bg-muted/20">
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
                      <button onClick={() => billsApi.submit(bill.id).then(load)} className="text-xs font-medium text-yellow-600 hover:underline">
                        Submit
                      </button>
                    )}
                    {bill.status === "awaiting_approval" && (
                      <button onClick={() => billsApi.approve(bill.id).then(load)} className="text-xs font-medium text-blue-600 hover:underline">
                        Approve
                      </button>
                    )}
                    {bill.status !== "void" && bill.status !== "paid" && (
                      <button
                        onClick={() => { if (confirm(`Void ${bill.number}?`)) billsApi.void(bill.id).then(load); }}
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
