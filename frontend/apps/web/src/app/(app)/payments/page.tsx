"use client";

import { showToast } from "@/lib/toast";
import { useEffect, useState } from "react";
import {
  type Contact,
  type Payment,
  type PaymentCreate,
  contactsApi,
  paymentsApi,
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

type Tab = "received" | "made";

const TABS: { id: Tab; label: string }[] = [
  { id: "received", label: "Received (from customers)" },
  { id: "made", label: "Made (to suppliers)" },
];

const EMPTY_FORM: PaymentCreate = {
  payment_type: "received",
  contact_id: "",
  amount: "",
  currency: "USD",
  fx_rate: "1",
  payment_date: new Date().toISOString().slice(0, 10),
  reference: "",
  bank_account_ref: "",
};

export default function PaymentsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("received");
  const [payments, setPayments] = useState<Payment[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<PaymentCreate>({ ...EMPTY_FORM });

  const load = async (tab: Tab) => {
    try {
      setLoading(true);
      const [pymtRes, contRes] = await Promise.all([
        paymentsApi.list({ payment_type: tab }),
        contactsApi.list(),
      ]);
      setPayments(pymtRes.items);
      setContacts(contRes.items);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(activeTab);
  }, [activeTab]);

  const switchTab = (tab: Tab) => {
    setActiveTab(tab);
    setShowForm(false);
    setForm({ ...EMPTY_FORM, payment_type: tab });
  };

  const openForm = () => {
    setForm({ ...EMPTY_FORM, payment_type: activeTab });
    setShowForm(true);
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      const body: PaymentCreate = {
        payment_type: form.payment_type,
        contact_id: form.contact_id,
        amount: form.amount,
        payment_date: form.payment_date,
        ...(form.currency ? { currency: form.currency } : {}),
        ...(form.fx_rate ? { fx_rate: form.fx_rate } : {}),
        ...(form.reference ? { reference: form.reference } : {}),
        ...(form.bank_account_ref ? { bank_account_ref: form.bank_account_ref } : {}),
      };
      await paymentsApi.create(body);
      setShowForm(false);
      setForm({ ...EMPTY_FORM, payment_type: activeTab });
      await load(activeTab);
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleVoid = async (payment: Payment) => {
    if (!confirm(`Void payment ${payment.number}?`)) return;
    try {
      await paymentsApi.void(payment.id);
      await load(activeTab);
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    }
  };

  const contactName = (id: string) => contacts.find((c) => c.id === id)?.name ?? id;

  const headerActions = (
    <button
      onClick={openForm}
      className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
    >
      + New Payment
    </button>
  );

  return (
    <>
      <PageHeader
        title="Payments"
        subtitle="Record and track payments received and made"
        actions={headerActions}
      />
    <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg border bg-muted/30 p-1 w-fit">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => switchTab(tab.id)}
            className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Create form */}
      {showForm && (
        <div className="rounded-xl border bg-card p-6 shadow-sm">
          <h2 className="mb-4 font-semibold">
            New {activeTab === "received" ? "Payment Received" : "Payment Made"}
          </h2>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  {activeTab === "received" ? "Customer" : "Supplier"} *
                </label>
                <select
                  value={form.contact_id}
                  onChange={(e) => setForm({ ...form, contact_id: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  required
                >
                  <option value="">Select contact…</option>
                  {contacts.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Amount *
                </label>
                <input
                  type="number"
                  min="0.01"
                  step="0.01"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  placeholder="0.00"
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Currency
                </label>
                <input
                  value={form.currency ?? "USD"}
                  onChange={(e) => setForm({ ...form, currency: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  placeholder="USD"
                  maxLength={3}
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Payment Date *
                </label>
                <input
                  type="date"
                  value={form.payment_date}
                  onChange={(e) => setForm({ ...form, payment_date: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Reference
                </label>
                <input
                  value={form.reference ?? ""}
                  onChange={(e) => setForm({ ...form, reference: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  placeholder="Ref / cheque no."
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Bank Account Ref
                </label>
                <input
                  value={form.bank_account_ref ?? ""}
                  onChange={(e) => setForm({ ...form, bank_account_ref: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  placeholder="Bank account ref"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t pt-4">
              <button
                type="submit"
                disabled={saving}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
              >
                {saving ? "Saving…" : "Save Payment"}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="rounded-lg border px-4 py-2 text-sm hover:bg-muted"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* List */}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : payments.length === 0 ? (
        <div className="rounded-xl border bg-card p-12 text-center">
          <p className="text-muted-foreground">
            No {activeTab === "received" ? "payments received" : "payments made"} found.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Number</th>
                <th className="px-4 py-3 text-left font-medium">Contact</th>
                <th className="px-4 py-3 text-left font-medium">Date</th>
                <th className="px-4 py-3 text-right font-medium">Amount</th>
                <th className="px-4 py-3 text-left font-medium">Reference</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {payments.map((payment) => (
                <tr key={payment.id} className="hover:bg-muted/20">
                  <td className="px-4 py-3 font-mono text-xs font-medium">{payment.number}</td>
                  <td className="px-4 py-3">{contactName(payment.contact_id)}</td>
                  <td className="px-4 py-3 text-muted-foreground">{payment.payment_date}</td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums">
                    {fmt(payment.amount, payment.currency)}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{payment.reference ?? "—"}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={payment.status} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    {payment.status !== "voided" && (
                      <button
                        onClick={() => handleVoid(payment)}
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
