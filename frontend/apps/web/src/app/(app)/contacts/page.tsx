"use client";

import { showToast } from "@/lib/toast";
import { useEffect, useState } from "react";
import Link from "next/link";
import { type Contact, contactsApi } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { CsvImportExport } from "@/components/csv-import-export";

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

export default function ContactsPage() {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>("");
  const [showArchived, setShowArchived] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    contact_type: "customer",
    name: "",
    code: "",
    email: "",
    phone: "",
    currency: "USD",
  });

  const load = async () => {
    try {
      setLoading(true);
      const res = await contactsApi.list({
        ...(filterType ? { contact_type: filterType } : {}),
        include_archived: showArchived,
      });
      setContacts(res.items);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [filterType, showArchived]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      await contactsApi.create({
        contact_type: form.contact_type,
        name: form.name,
        code: form.code || null,
        email: form.email || null,
        phone: form.phone || null,
        currency: form.currency,
      });
      setShowForm(false);
      setForm({ contact_type: "customer", name: "", code: "", email: "", phone: "", currency: "USD" });
      await load();
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleArchive = async (id: string, name: string) => {
    if (!confirm(`Archive ${name}?`)) return;
    try {
      await contactsApi.archive(id);
      await load();
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    }
  };

  const headerActions = (
    <>
      <CsvImportExport
        entityType="contacts"
        templateUrl="/v1/contacts/csv-template"
        importUrl="/v1/contacts/import"
        onImportComplete={() => void load()}
      />
      <button
        onClick={() => setShowForm(true)}
        className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
      >
        + New Contact
      </button>
    </>
  );

  return (
    <>
      <PageHeader
        title="Contacts"
        subtitle="Customers, suppliers, and employees"
        actions={headerActions}
      />
    <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">

      {/* Filters */}
      <div className="flex items-center gap-4">
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="rounded-lg border px-3 py-2 text-sm"
        >
          <option value="">All types</option>
          <option value="customer">Customers</option>
          <option value="supplier">Suppliers</option>
          <option value="both">Both</option>
          <option value="employee">Employees</option>
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
          />
          Show archived
        </label>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="rounded-xl border bg-card p-6 shadow-sm">
          <h2 className="mb-4 font-semibold">New Contact</h2>
          <form onSubmit={handleCreate} className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Type</label>
              <select
                value={form.contact_type}
                onChange={(e) => setForm({ ...form, contact_type: e.target.value })}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                required
              >
                <option value="customer">Customer</option>
                <option value="supplier">Supplier</option>
                <option value="both">Both</option>
                <option value="employee">Employee</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Name *</label>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                required
                placeholder="Acme Corp"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Code</label>
              <input
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                placeholder="ACME"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Currency</label>
              <input
                value={form.currency}
                onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                maxLength={3}
                placeholder="USD"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                placeholder="billing@acme.com"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Phone</label>
              <input
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                placeholder="+1 555 0100"
              />
            </div>
            <div className="col-span-2 flex gap-2">
              <button
                type="submit"
                disabled={saving}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
              >
                {saving ? "Saving…" : "Create Contact"}
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

      {/* Table */}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : error ? (
        <p className="text-sm text-red-600">{error}</p>
      ) : contacts.length === 0 ? (
        <div className="rounded-xl border bg-card p-12 text-center">
          <p className="text-muted-foreground">No contacts yet. Create your first contact above.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Name</th>
                <th className="px-4 py-3 text-left font-medium">Type</th>
                <th className="px-4 py-3 text-left font-medium">Code</th>
                <th className="px-4 py-3 text-left font-medium">Email</th>
                <th className="px-4 py-3 text-left font-medium">Currency</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {contacts.map((c) => (
                <tr key={c.id} className={`hover:bg-muted/20 ${c.is_archived ? "opacity-50" : ""}`}>
                  <td className="px-4 py-3 font-medium">
                    <Link href={`/contacts/${c.id}`} className="hover:underline">
                      {c.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_COLORS[c.contact_type] ?? "bg-muted"}`}>
                      {TYPE_LABELS[c.contact_type] ?? c.contact_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{c.code ?? "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">{c.email ?? "—"}</td>
                  <td className="px-4 py-3">{c.currency}</td>
                  <td className="px-4 py-3">
                    {c.is_archived ? (
                      <StatusBadge status="archived" />
                    ) : (
                      <StatusBadge status="active" />
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {!c.is_archived && (
                      <button
                        onClick={() => handleArchive(c.id, c.name)}
                        className="text-xs text-muted-foreground hover:text-red-600"
                      >
                        Archive
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
