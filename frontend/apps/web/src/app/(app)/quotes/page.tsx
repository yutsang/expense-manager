"use client";

import { showToast } from "@/lib/toast";
import { useEffect, useState } from "react";
import {
  type Contact,
  type SalesDocument,
  type SalesDocumentCreate,
  contactsApi,
  salesDocsApi,
} from "@/lib/api";
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
  description: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
}

const defaultLine = (): LineInput => ({
  description: "",
  quantity: "1",
  unit_price: "0",
  tax_rate: "0",
});

type DocTab = "quote" | "sales_order";

export default function QuotesPage() {
  const [docs, setDocs] = useState<SalesDocument[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<DocTab>("quote");
  const [filterStatus, setFilterStatus] = useState("");

  const [form, setForm] = useState<{
    contact_id: string;
    issue_date: string;
    expiry_date: string;
    currency: string;
    notes: string;
    reference: string;
    lines: LineInput[];
  }>({
    contact_id: "",
    issue_date: new Date().toISOString().slice(0, 10),
    expiry_date: "",
    currency: "USD",
    notes: "",
    reference: "",
    lines: [defaultLine()],
  });

  const load = async () => {
    setError(null);
    try {
      setLoading(true);
      const [docsRes, contRes] = await Promise.all([
        salesDocsApi.list({ doc_type: activeTab }),
        contactsApi.list({ contact_type: "customer" }),
      ]);
      setDocs(filterStatus ? docsRes.items.filter((d) => d.status === filterStatus) : docsRes.items);
      setContacts(contRes.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [activeTab, filterStatus]);

  const addLine = () => setForm((f) => ({ ...f, lines: [...f.lines, defaultLine()] }));

  const removeLine = (i: number) =>
    setForm((f) => ({ ...f, lines: f.lines.filter((_, idx) => idx !== i) }));

  const updateLine = (i: number, field: keyof LineInput, val: string) =>
    setForm((f) => {
      const lines = [...f.lines];
      const prev = lines[i] as LineInput;
      lines[i] = { ...prev, [field]: val };
      return { ...f, lines };
    });

  const lineTotal = (l: LineInput) => {
    const amt = parseFloat(l.quantity || "0") * parseFloat(l.unit_price || "0");
    const tax = amt * parseFloat(l.tax_rate || "0");
    return (amt + tax).toFixed(2);
  };

  const grandTotal = form.lines
    .reduce((s, l) => s + parseFloat(lineTotal(l)), 0)
    .toFixed(2);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      const body: SalesDocumentCreate = {
        doc_type: activeTab,
        contact_id: form.contact_id || null,
        issue_date: form.issue_date,
        expiry_date: form.expiry_date || null,
        currency: form.currency,
        reference: form.reference || null,
        notes: form.notes || null,
        lines: form.lines.map((l, i) => ({
          description: l.description,
          quantity: l.quantity,
          unit_price: l.unit_price,
          tax_rate: l.tax_rate,
          sort_order: i,
        })),
      };
      await salesDocsApi.create(body);
      setShowForm(false);
      setForm({
        contact_id: "",
        issue_date: new Date().toISOString().slice(0, 10),
        expiry_date: "",
        currency: "USD",
        notes: "",
        reference: "",
        lines: [defaultLine()],
      });
      await load();
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleConvert = async (doc: SalesDocument) => {
    const target = doc.doc_type === "quote" ? "sales order" : "invoice";
    if (!confirm(`Convert ${doc.number} to ${target}?`)) return;
    try {
      await salesDocsApi.convert(doc.id);
      await load();
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    }
  };

  const handleVoid = async (doc: SalesDocument) => {
    if (!confirm(`Void ${doc.number}?`)) return;
    try {
      await salesDocsApi.void(doc.id);
      await load();
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    }
  };

  const contactName = (id: string | null) =>
    id ? (contacts.find((c) => c.id === id)?.name ?? id) : "—";

  const tabLabel = activeTab === "quote" ? "Quotes" : "Sales Orders";

  const headerActions = (
    <button
      onClick={() => setShowForm(true)}
      className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
    >
      + New {activeTab === "quote" ? "Quote" : "Sales Order"}
    </button>
  );

  const statuses = activeTab === "quote"
    ? ["", "draft", "sent", "accepted", "rejected", "converted", "voided"]
    : ["", "draft", "sent", "accepted", "converted", "voided"];

  return (
    <>
      <PageHeader
        title="Quotes & Sales Orders"
        subtitle="Pre-sales document chain"
        actions={headerActions}
      />
      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">
        {/* Tabs */}
        <div className="flex gap-1 rounded-lg border bg-muted/20 p-1 w-fit">
          {(["quote", "sales_order"] as DocTab[]).map((t) => (
            <button
              key={t}
              onClick={() => { setActiveTab(t); setFilterStatus(""); }}
              className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${activeTab === t ? "bg-white shadow-sm text-indigo-700 dark:bg-gray-800 dark:text-indigo-400" : "text-muted-foreground hover:text-foreground"}`}
            >
              {t === "quote" ? "Quotes" : "Sales Orders"}
            </button>
          ))}
        </div>

        {/* Status filter */}
        <div className="flex flex-wrap gap-2">
          {statuses.map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${filterStatus === s ? "bg-indigo-600 text-white" : "border hover:bg-muted"}`}
            >
              {s || "All"}
            </button>
          ))}
        </div>

        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}

        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : docs.length === 0 ? (
          <div className="rounded-xl border bg-card p-12 text-center">
            <p className="text-muted-foreground">
              No {tabLabel.toLowerCase()} found. Create one above.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Number</th>
                  <th className="px-4 py-3 text-left font-medium">Contact</th>
                  <th className="px-4 py-3 text-left font-medium">Issue Date</th>
                  <th className="px-4 py-3 text-left font-medium">Expiry</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3 text-right font-medium">Total</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {docs.map((doc) => (
                  <tr key={doc.id} className="hover:bg-muted/20">
                    <td className="px-4 py-3 font-mono text-xs font-medium">{doc.number}</td>
                    <td className="px-4 py-3">{contactName(doc.contact_id)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{doc.issue_date}</td>
                    <td className="px-4 py-3 text-muted-foreground">{doc.expiry_date ?? "—"}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">
                      {fmt(doc.total, doc.currency)}
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      {doc.status !== "converted" && doc.status !== "voided" && (
                        <button
                          onClick={() => { void handleConvert(doc); }}
                          className="text-xs font-medium text-blue-600 hover:underline"
                        >
                          {doc.doc_type === "quote" ? "→ Sales Order" : "→ Invoice"}
                        </button>
                      )}
                      {doc.status !== "voided" && doc.status !== "converted" && (
                        <button
                          onClick={() => { void handleVoid(doc); }}
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

      {/* Create slide-over */}
      {showForm && (
        <>
          <div
            className="fixed inset-0 bg-black/30 z-40"
            onClick={() => setShowForm(false)}
          />
          <div className="fixed right-0 top-0 h-full w-[480px] bg-background border-l shadow-xl z-50 flex flex-col overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold">
                New {activeTab === "quote" ? "Quote" : "Sales Order"}
              </h2>
              <button
                onClick={() => setShowForm(false)}
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
              >
                ✕
              </button>
            </div>
            <form onSubmit={(e) => { void handleCreate(e); }} className="space-y-4 flex-1">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Customer
                </label>
                <select
                  value={form.contact_id}
                  onChange={(e) => setForm({ ...form, contact_id: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm bg-background"
                >
                  <option value="">Select customer…</option>
                  {contacts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Issue Date *
                  </label>
                  <input
                    type="date"
                    value={form.issue_date}
                    onChange={(e) => setForm({ ...form, issue_date: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm bg-background"
                    required
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Expiry Date
                  </label>
                  <input
                    type="date"
                    value={form.expiry_date}
                    onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm bg-background"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Currency
                  </label>
                  <input
                    type="text"
                    value={form.currency}
                    onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
                    maxLength={3}
                    className="w-full rounded-lg border px-3 py-2 text-sm bg-background"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Reference
                  </label>
                  <input
                    type="text"
                    value={form.reference}
                    onChange={(e) => setForm({ ...form, reference: e.target.value })}
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
                    <input
                      value={line.description}
                      onChange={(e) => updateLine(i, "description", e.target.value)}
                      placeholder="Description"
                      className="w-full rounded-lg border px-2 py-1.5 text-sm bg-background"
                    />
                    <div className="grid grid-cols-3 gap-2">
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
                      <div>
                        <label className="text-xs text-muted-foreground">Tax Rate</label>
                        <input
                          type="number"
                          min="0"
                          max="1"
                          step="0.01"
                          value={line.tax_rate}
                          onChange={(e) => updateLine(i, "tax_rate", e.target.value)}
                          className="w-full rounded-lg border px-2 py-1.5 text-sm bg-background"
                        />
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-muted-foreground">
                        Line total:{" "}
                        <span className="font-mono font-medium">{lineTotal(line)}</span>
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
                <button
                  type="button"
                  onClick={addLine}
                  className="text-xs text-indigo-600 hover:underline"
                >
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
