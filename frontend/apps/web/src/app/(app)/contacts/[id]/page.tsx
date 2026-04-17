"use client";

import { showToast } from "@/lib/toast";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  type Contact,
  type ContactKycResponse,
  type SanctionsScreeningResult,
  type Invoice,
  type Bill,
  type Payment,
  contactsApi,
  kycApi,
  sanctionsApi,
  invoicesApi,
  billsApi,
  paymentsApi,
} from "@/lib/api";
import { PageHeader } from "@/components/page-header";

const TYPE_LABELS: Record<string, string> = {
  customer: "Customer",
  supplier: "Supplier",
  both: "Customer & Supplier",
  employee: "Employee",
};

const TYPE_COLORS: Record<string, string> = {
  customer: "bg-blue-100 text-blue-700",
  supplier: "bg-purple-100 text-purple-700",
  both: "bg-green-100 text-green-700",
  employee: "bg-orange-100 text-orange-700",
};

const KYC_STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-700",
  approved: "bg-green-100 text-green-700",
  expired: "bg-red-100 text-red-700",
  flagged: "bg-red-100 text-red-800",
};

const SANCTIONS_STATUS_COLORS: Record<string, string> = {
  not_checked: "bg-gray-100 text-gray-600",
  clear: "bg-green-100 text-green-700",
  flagged: "bg-red-100 text-red-800",
  under_review: "bg-yellow-100 text-yellow-700",
};

const INVOICE_STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-100 text-gray-600",
  authorised: "bg-blue-100 text-blue-700",
  paid: "bg-green-100 text-green-700",
  voided: "bg-red-100 text-red-600",
  overdue: "bg-orange-100 text-orange-700",
};

const BILL_STATUS_COLORS: Record<string, string> = {
  draft: "bg-gray-100 text-gray-600",
  submitted: "bg-yellow-100 text-yellow-700",
  approved: "bg-blue-100 text-blue-700",
  paid: "bg-green-100 text-green-700",
  voided: "bg-red-100 text-red-600",
};

const PAYMENT_STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-700",
  applied: "bg-green-100 text-green-700",
  voided: "bg-red-100 text-red-600",
};

function fmt(amount: string): string {
  return parseFloat(amount).toFixed(2);
}

function fmtDate(d: string | null): string {
  if (!d) return "—";
  return new Date(d).toLocaleDateString();
}

type Tab = "invoices" | "bills" | "payments";

export default function ContactDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [contact, setContact] = useState<Contact | null>(null);
  const [kyc, setKyc] = useState<ContactKycResponse | null>(null);
  const [sanctionsResult, setSanctionsResult] = useState<SanctionsScreeningResult | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [bills, setBills] = useState<Bill[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("invoices");

  const [screening, setScreening] = useState(false);
  const [screenError, setScreenError] = useState<string | null>(null);

  const [showEdit, setShowEdit] = useState(false);
  const [editForm, setEditForm] = useState({ name: "", email: "", phone: "", currency: "" });
  const [saving, setSaving] = useState(false);

  const [showKycEdit, setShowKycEdit] = useState(false);
  const [kycForm, setKycForm] = useState({
    kyc_status: "",
    id_type: "",
    id_number: "",
    id_expiry_date: "",
    notes: "",
    last_review_date: "",
    next_review_date: "",
  });
  const [savingKyc, setSavingKyc] = useState(false);

  const [archiving, setArchiving] = useState(false);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        const [contactData, invoiceData, billData, paymentData] = await Promise.all([
          contactsApi.get(id),
          invoicesApi.list({ contact_id: id }),
          billsApi.list({ contact_id: id }),
          paymentsApi.list(),
        ]);
        setContact(contactData);
        setInvoices(invoiceData.items);
        setBills(billData.items);
        setPayments(paymentData.items.filter((p) => p.contact_id === id));

        try {
          const kycData = await kycApi.get(id);
          setKyc(kycData);
        } catch {
          // KYC record may not exist yet
        }

        try {
          const sanctionsData = await sanctionsApi.getScreenResult(id);
          if (sanctionsData) setSanctionsResult(sanctionsData);
        } catch {
          // no prior screen result
        }
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  const openEdit = () => {
    if (!contact) return;
    setEditForm({
      name: contact.name,
      email: contact.email ?? "",
      phone: contact.phone ?? "",
      currency: contact.currency,
    });
    setShowEdit(true);
  };

  const handleSaveContact = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!contact) return;
    try {
      setSaving(true);
      const updated = await contactsApi.update(id, {
        name: editForm.name,
        email: editForm.email || null,
        phone: editForm.phone || null,
        currency: editForm.currency,
      });
      setContact(updated);
      setShowEdit(false);
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleArchive = async () => {
    if (!contact) return;
    if (!confirm(`Archive ${contact.name}?`)) return;
    try {
      setArchiving(true);
      await contactsApi.archive(id);
      router.push("/contacts");
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    } finally {
      setArchiving(false);
    }
  };

  const handleRunSanctions = async () => {
    try {
      setScreening(true);
      setScreenError(null);
      const result = await sanctionsApi.screenContact(id);
      setSanctionsResult(result);
      try {
        const kycData = await kycApi.get(id);
        setKyc(kycData);
      } catch {
        // ignore
      }
    } catch (e) {
      setScreenError(String(e));
    } finally {
      setScreening(false);
    }
  };

  const openKycEdit = () => {
    setKycForm({
      kyc_status: kyc?.kyc_status ?? "pending",
      id_type: kyc?.id_type ?? "",
      id_number: kyc?.id_number ?? "",
      id_expiry_date: kyc?.id_expiry_date ?? "",
      notes: kyc?.notes ?? "",
      last_review_date: kyc?.last_review_date ?? "",
      next_review_date: kyc?.next_review_date ?? "",
    });
    setShowKycEdit(true);
  };

  const handleSaveKyc = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSavingKyc(true);
      const updated = await kycApi.update(id, {
        kyc_status: kycForm.kyc_status || null,
        id_type: kycForm.id_type || null,
        id_number: kycForm.id_number || null,
        id_expiry_date: kycForm.id_expiry_date || null,
        notes: kycForm.notes || null,
        last_review_date: kycForm.last_review_date || null,
        next_review_date: kycForm.next_review_date || null,
      });
      setKyc(updated);
      setShowKycEdit(false);
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    } finally {
      setSavingKyc(false);
    }
  };

  const totalInvoiced = invoices.reduce((s, i) => s + parseFloat(i.total), 0);
  const totalBilled = bills.reduce((s, b) => s + parseFloat(b.total), 0);
  const outstandingAR = invoices
    .filter((i) => i.status !== "paid" && i.status !== "voided")
    .reduce((s, i) => s + parseFloat(i.amount_due), 0);
  const outstandingAP = bills
    .filter((b) => b.status !== "paid" && b.status !== "voided")
    .reduce((s, b) => s + parseFloat(b.amount_due), 0);

  if (loading) {
    return (
      <>
        <PageHeader title="Contact" subtitle="Loading…" />
        <div className="mx-auto max-w-7xl px-6 py-10">
          <p className="text-sm text-muted-foreground">Loading…</p>
        </div>
      </>
    );
  }

  if (error || !contact) {
    return (
      <>
        <PageHeader title="Contact" />
        <div className="mx-auto max-w-7xl px-6 py-10">
          <p className="text-sm text-red-600">{error ?? "Contact not found."}</p>
        </div>
      </>
    );
  }

  const sanctionsStatusKey =
    sanctionsResult
      ? sanctionsResult.match_status === "clear"
        ? "clear"
        : sanctionsResult.match_status === "confirmed_match"
        ? "flagged"
        : "under_review"
      : kyc?.sanctions_status ?? "not_checked";

  const headerActions = (
    <div className="flex gap-2">
      <button
        onClick={openEdit}
        className="rounded-lg border px-4 py-2 text-sm font-medium hover:bg-muted"
      >
        Edit
      </button>
      {!contact.is_archived && (
        <button
          onClick={handleArchive}
          disabled={archiving}
          className="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
        >
          {archiving ? "Archiving…" : "Archive"}
        </button>
      )}
    </div>
  );

  return (
    <>
      <PageHeader
        title={contact.name}
        subtitle={TYPE_LABELS[contact.contact_type] ?? contact.contact_type}
        actions={headerActions}
      />

      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">

        {/* Edit Contact Modal */}
        {showEdit && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="w-full max-w-md rounded-xl border bg-background p-6 shadow-xl">
              <h2 className="mb-4 font-semibold">Edit Contact</h2>
              <form onSubmit={handleSaveContact} className="space-y-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Name</label>
                  <input
                    value={editForm.name}
                    onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    required
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Email</label>
                  <input
                    type="email"
                    value={editForm.email}
                    onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Phone</label>
                  <input
                    value={editForm.phone}
                    onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Currency</label>
                  <input
                    value={editForm.currency}
                    onChange={(e) => setEditForm({ ...editForm, currency: e.target.value.toUpperCase() })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    maxLength={3}
                  />
                </div>
                <div className="flex gap-2 pt-2">
                  <button
                    type="submit"
                    disabled={saving}
                    className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                  >
                    {saving ? "Saving…" : "Save"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowEdit(false)}
                    className="rounded-lg border px-4 py-2 text-sm hover:bg-muted"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Edit KYC Modal */}
        {showKycEdit && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="w-full max-w-md rounded-xl border bg-background p-6 shadow-xl">
              <h2 className="mb-4 font-semibold">Edit KYC Record</h2>
              <form onSubmit={handleSaveKyc} className="space-y-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">KYC Status</label>
                  <select
                    value={kycForm.kyc_status}
                    onChange={(e) => setKycForm({ ...kycForm, kyc_status: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                  >
                    <option value="pending">Pending</option>
                    <option value="approved">Approved</option>
                    <option value="expired">Expired</option>
                    <option value="flagged">Flagged</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">ID Type</label>
                  <input
                    value={kycForm.id_type}
                    onChange={(e) => setKycForm({ ...kycForm, id_type: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    placeholder="passport, drivers_license…"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">ID Number</label>
                  <input
                    value={kycForm.id_number}
                    onChange={(e) => setKycForm({ ...kycForm, id_number: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">ID Expiry Date</label>
                  <input
                    type="date"
                    value={kycForm.id_expiry_date}
                    onChange={(e) => setKycForm({ ...kycForm, id_expiry_date: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Last Review Date</label>
                  <input
                    type="date"
                    value={kycForm.last_review_date}
                    onChange={(e) => setKycForm({ ...kycForm, last_review_date: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Next Review Date</label>
                  <input
                    type="date"
                    value={kycForm.next_review_date}
                    onChange={(e) => setKycForm({ ...kycForm, next_review_date: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Notes</label>
                  <textarea
                    value={kycForm.notes}
                    onChange={(e) => setKycForm({ ...kycForm, notes: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    rows={3}
                  />
                </div>
                <div className="flex gap-2 pt-2">
                  <button
                    type="submit"
                    disabled={savingKyc}
                    className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                  >
                    {savingKyc ? "Saving…" : "Save"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowKycEdit(false)}
                    className="rounded-lg border px-4 py-2 text-sm hover:bg-muted"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Top section: contact info + KYC/sanctions */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">

          {/* Contact info card */}
          <div className="lg:col-span-2 rounded-xl border bg-card p-6 shadow-sm space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-lg font-semibold">{contact.name}</h2>
                  {contact.is_archived && (
                    <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                      Archived
                    </span>
                  )}
                </div>
                <span className={`mt-1 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_COLORS[contact.contact_type] ?? "bg-muted"}`}>
                  {TYPE_LABELS[contact.contact_type] ?? contact.contact_type}
                </span>
              </div>
              <span className="rounded-lg border px-3 py-1 text-sm font-mono font-medium">
                {contact.currency}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4 border-t pt-4">
              <div>
                <p className="text-xs font-medium text-muted-foreground">Email</p>
                <p className="mt-0.5 text-sm">{contact.email ?? "—"}</p>
              </div>
              <div>
                <p className="text-xs font-medium text-muted-foreground">Phone</p>
                <p className="mt-0.5 text-sm">{contact.phone ?? "—"}</p>
              </div>
              {contact.code && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Code</p>
                  <p className="mt-0.5 font-mono text-sm">{contact.code}</p>
                </div>
              )}
            </div>
          </div>

          {/* KYC & Sanctions card */}
          <div className="rounded-xl border bg-card p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">KYC & Sanctions</h3>
              <button
                onClick={openKycEdit}
                className="text-xs text-muted-foreground underline hover:text-foreground"
              >
                Edit KYC
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <p className="text-xs font-medium text-muted-foreground">KYC Status</p>
                <span className={`mt-1 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${KYC_STATUS_COLORS[kyc?.kyc_status ?? "pending"] ?? "bg-muted"}`}>
                  {kyc?.kyc_status ?? "pending"}
                </span>
              </div>

              <div>
                <p className="text-xs font-medium text-muted-foreground">Sanctions</p>
                <span className={`mt-1 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${SANCTIONS_STATUS_COLORS[sanctionsStatusKey] ?? "bg-muted"}`}>
                  {sanctionsStatusKey.replace("_", " ")}
                </span>
                {sanctionsResult && (
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Score: {sanctionsResult.match_score} · {fmtDate(sanctionsResult.screened_at)}
                  </p>
                )}
              </div>

              <div>
                <p className="text-xs font-medium text-muted-foreground">Last Review</p>
                <p className="mt-0.5 text-sm">{fmtDate(kyc?.last_review_date ?? null)}</p>
              </div>

              {kyc?.next_review_date && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Next Review</p>
                  <p className="mt-0.5 text-sm">{fmtDate(kyc.next_review_date)}</p>
                </div>
              )}
            </div>

            {screenError && (
              <p className="text-xs text-red-600">{screenError}</p>
            )}

            <button
              onClick={handleRunSanctions}
              disabled={screening}
              className="w-full rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            >
              {screening ? "Screening…" : "Run Sanctions Screen"}
            </button>
          </div>
        </div>

        {/* Summary stats */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <p className="text-xs font-medium text-muted-foreground">Total Invoiced</p>
            <p className="mt-1 text-xl font-semibold">{contact.currency} {fmt(totalInvoiced.toFixed(2))}</p>
          </div>
          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <p className="text-xs font-medium text-muted-foreground">Total Billed</p>
            <p className="mt-1 text-xl font-semibold">{contact.currency} {fmt(totalBilled.toFixed(2))}</p>
          </div>
          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <p className="text-xs font-medium text-muted-foreground">Outstanding AR</p>
            <p className={`mt-1 text-xl font-semibold ${outstandingAR > 0 ? "text-blue-600" : ""}`}>
              {contact.currency} {fmt(outstandingAR.toFixed(2))}
            </p>
          </div>
          <div className="rounded-xl border bg-card p-4 shadow-sm">
            <p className="text-xs font-medium text-muted-foreground">Outstanding AP</p>
            <p className={`mt-1 text-xl font-semibold ${outstandingAP > 0 ? "text-orange-600" : ""}`}>
              {contact.currency} {fmt(outstandingAP.toFixed(2))}
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="rounded-xl border bg-card shadow-sm">
          <div className="border-b">
            <div className="flex gap-0">
              {(["invoices", "bills", "payments"] as Tab[]).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-6 py-3 text-sm font-medium capitalize border-b-2 transition-colors ${
                    activeTab === tab
                      ? "border-primary text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tab === "invoices"
                    ? `Invoices (${invoices.length})`
                    : tab === "bills"
                    ? `Bills (${bills.length})`
                    : `Payments (${payments.length})`}
                </button>
              ))}
            </div>
          </div>

          <div className="p-0">
            {activeTab === "invoices" && (
              invoices.length === 0 ? (
                <p className="px-6 py-8 text-center text-sm text-muted-foreground">No invoices for this contact.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead className="border-b bg-muted/40">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium">Number</th>
                      <th className="px-4 py-3 text-left font-medium">Issue Date</th>
                      <th className="px-4 py-3 text-left font-medium">Due Date</th>
                      <th className="px-4 py-3 text-left font-medium">Status</th>
                      <th className="px-4 py-3 text-right font-medium">Amount Due</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {invoices.map((inv) => (
                      <tr key={inv.id} className="hover:bg-muted/20">
                        <td className="px-4 py-3 font-mono text-xs">{inv.number}</td>
                        <td className="px-4 py-3">{fmtDate(inv.issue_date)}</td>
                        <td className="px-4 py-3">{fmtDate(inv.due_date)}</td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${INVOICE_STATUS_COLORS[inv.status] ?? "bg-muted"}`}>
                            {inv.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-medium">
                          {inv.currency} {fmt(inv.amount_due)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            )}

            {activeTab === "bills" && (
              bills.length === 0 ? (
                <p className="px-6 py-8 text-center text-sm text-muted-foreground">No bills for this contact.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead className="border-b bg-muted/40">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium">Number</th>
                      <th className="px-4 py-3 text-left font-medium">Issue Date</th>
                      <th className="px-4 py-3 text-left font-medium">Due Date</th>
                      <th className="px-4 py-3 text-left font-medium">Status</th>
                      <th className="px-4 py-3 text-right font-medium">Amount Due</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {bills.map((bill) => (
                      <tr key={bill.id} className="hover:bg-muted/20">
                        <td className="px-4 py-3 font-mono text-xs">{bill.number}</td>
                        <td className="px-4 py-3">{fmtDate(bill.issue_date)}</td>
                        <td className="px-4 py-3">{fmtDate(bill.due_date)}</td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${BILL_STATUS_COLORS[bill.status] ?? "bg-muted"}`}>
                            {bill.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-medium">
                          {bill.currency} {fmt(bill.amount_due)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            )}

            {activeTab === "payments" && (
              payments.length === 0 ? (
                <p className="px-6 py-8 text-center text-sm text-muted-foreground">No payments for this contact.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead className="border-b bg-muted/40">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium">Number</th>
                      <th className="px-4 py-3 text-left font-medium">Date</th>
                      <th className="px-4 py-3 text-left font-medium">Type</th>
                      <th className="px-4 py-3 text-left font-medium">Status</th>
                      <th className="px-4 py-3 text-right font-medium">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {payments.map((pmt) => (
                      <tr key={pmt.id} className="hover:bg-muted/20">
                        <td className="px-4 py-3 font-mono text-xs">{pmt.number}</td>
                        <td className="px-4 py-3">{fmtDate(pmt.payment_date)}</td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${pmt.payment_type === "received" ? "bg-green-100 text-green-700" : "bg-orange-100 text-orange-700"}`}>
                            {pmt.payment_type}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${PAYMENT_STATUS_COLORS[pmt.status] ?? "bg-muted"}`}>
                            {pmt.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right font-medium">
                          {pmt.currency} {fmt(pmt.amount)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )
            )}
          </div>
        </div>
      </div>
    </>
  );
}
