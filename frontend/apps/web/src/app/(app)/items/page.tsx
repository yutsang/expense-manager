"use client";

import { showToast } from "@/lib/toast";
import { useEffect, useState } from "react";
import { type Item, type TaxCode, itemsApi, taxCodesApi } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { CsvImportExport } from "@/components/csv-import-export";

const CURRENCIES = ["USD", "EUR", "GBP", "AUD", "CAD", "SGD", "HKD", "JPY", "CNY", "NZD"];

const TYPE_COLORS: Record<string, string> = {
  service: "bg-blue-100 text-blue-700",
  product: "bg-green-100 text-green-700",
};

const BLANK_FORM = {
  code: "",
  name: "",
  item_type: "service",
  sales_unit_price: "",
  currency: "USD",
  tax_code_id: "",
  description: "",
};

type FormState = typeof BLANK_FORM;

export default function ItemsPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [taxCodes, setTaxCodes] = useState<TaxCode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [filterType, setFilterType] = useState<string>("");

  // Modal state
  const [modalMode, setModalMode] = useState<"add" | "edit" | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(BLANK_FORM);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      setLoading(true);
      const res = await itemsApi.list({
        ...(filterType ? { item_type: filterType } : {}),
        include_archived: showArchived,
      });
      setItems(res.items);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const loadTaxCodes = async () => {
    try {
      const res = await taxCodesApi.list({ active_only: true });
      setTaxCodes(res.items);
    } catch {
      // non-fatal — tax codes may not be set up yet
    }
  };

  useEffect(() => {
    void load();
  }, [filterType, showArchived]);

  useEffect(() => {
    void loadTaxCodes();
  }, []);

  const openAdd = () => {
    setForm(BLANK_FORM);
    setEditingId(null);
    setModalMode("add");
  };

  const openEdit = (item: Item) => {
    setForm({
      code: item.code,
      name: item.name,
      item_type: item.item_type,
      sales_unit_price: item.sales_unit_price ?? "",
      currency: item.currency,
      tax_code_id: "",
      description: item.description ?? "",
    });
    setEditingId(item.id);
    setModalMode("edit");
  };

  const closeModal = () => {
    setModalMode(null);
    setEditingId(null);
    setForm(BLANK_FORM);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      if (modalMode === "add") {
        await itemsApi.create({
          code: form.code,
          name: form.name,
          item_type: form.item_type,
          sales_unit_price: form.sales_unit_price || null,
          currency: form.currency,
          description: form.description || null,
        });
      } else if (modalMode === "edit" && editingId) {
        await itemsApi.update(editingId, {
          name: form.name,
          sales_unit_price: form.sales_unit_price || null,
          currency: form.currency,
          description: form.description || null,
        });
      }
      closeModal();
      await load();
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleArchive = async (id: string, name: string) => {
    if (!confirm(`Archive "${name}"? It will no longer appear in new transactions.`)) return;
    try {
      await itemsApi.archive(id);
      await load();
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    }
  };

  const headerActions = (
    <>
      <CsvImportExport
        entityType="items"
        templateUrl="/v1/items/csv-template"
        importUrl="/v1/items/import"
        onImportComplete={() => void load()}
      />
      <button
        onClick={openAdd}
        className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
      >
        + Add Item
      </button>
    </>
  );

  return (
    <>
      <PageHeader
        title="Items / Products"
        subtitle="Product and service catalog used in invoices and bills"
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
            <option value="service">Services</option>
            <option value="product">Products</option>
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

        {/* Table */}
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : items.length === 0 ? (
          <div className="rounded-xl border bg-card p-12 text-center">
            <p className="text-muted-foreground">No items yet. Add your first item above.</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Code</th>
                  <th className="px-4 py-3 text-left font-medium">Name</th>
                  <th className="px-4 py-3 text-left font-medium">Type</th>
                  <th className="px-4 py-3 text-left font-medium">Unit Price</th>
                  <th className="px-4 py-3 text-left font-medium">Currency</th>
                  <th className="px-4 py-3 text-left font-medium">Description</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className={`hover:bg-muted/20 ${item.is_archived ? "opacity-50" : ""}`}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                      {item.code}
                    </td>
                    <td className="px-4 py-3 font-medium">{item.name}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_COLORS[item.item_type] ?? "bg-muted"}`}
                      >
                        {item.item_type}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {item.sales_unit_price != null ? item.sales_unit_price : "—"}
                    </td>
                    <td className="px-4 py-3">{item.currency}</td>
                    <td className="px-4 py-3 max-w-xs truncate text-muted-foreground">
                      {item.description ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      {item.is_archived ? (
                        <StatusBadge status="archived" />
                      ) : (
                        <StatusBadge status="active" />
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        {!item.is_archived && (
                          <>
                            <button
                              onClick={() => openEdit(item)}
                              className="text-xs text-indigo-600 hover:text-indigo-800"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => { void handleArchive(item.id, item.name); }}
                              className="text-xs text-muted-foreground hover:text-red-600"
                            >
                              Archive
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add / Edit Modal */}
      {modalMode !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-lg rounded-xl border bg-card p-6 shadow-xl mx-4">
            <h2 className="mb-4 text-base font-semibold">
              {modalMode === "add" ? "Add Item" : "Edit Item"}
            </h2>
            <form onSubmit={(e) => { void handleSubmit(e); }} className="grid grid-cols-2 gap-4">
              {/* Code — only on add */}
              {modalMode === "add" && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Code *
                  </label>
                  <input
                    value={form.code}
                    onChange={(e) => setForm({ ...form, code: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    required
                    placeholder="CONSULT-HR"
                    maxLength={64}
                  />
                </div>
              )}

              {/* Name */}
              <div className={modalMode === "add" ? "" : "col-span-2"}>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Name *
                </label>
                <input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  required
                  placeholder="HR Consulting"
                  maxLength={255}
                />
              </div>

              {/* Type — only on add */}
              {modalMode === "add" && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Type *
                  </label>
                  <select
                    value={form.item_type}
                    onChange={(e) => setForm({ ...form, item_type: e.target.value })}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    required
                  >
                    <option value="service">Service</option>
                    <option value="product">Product</option>
                  </select>
                </div>
              )}

              {/* Unit Price */}
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Unit Price
                </label>
                <input
                  type="number"
                  step="0.0001"
                  min="0"
                  value={form.sales_unit_price}
                  onChange={(e) => setForm({ ...form, sales_unit_price: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  placeholder="0.00"
                />
              </div>

              {/* Currency */}
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Currency
                </label>
                <select
                  value={form.currency}
                  onChange={(e) => setForm({ ...form, currency: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                >
                  {CURRENCIES.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>

              {/* Tax Code */}
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Tax Code
                </label>
                <select
                  value={form.tax_code_id}
                  onChange={(e) => setForm({ ...form, tax_code_id: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                >
                  <option value="">— None —</option>
                  {taxCodes.map((tc) => (
                    <option key={tc.id} value={tc.id}>
                      {tc.code} — {tc.name} ({tc.rate}%)
                    </option>
                  ))}
                </select>
              </div>

              {/* Description */}
              <div className="col-span-2">
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Description
                </label>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  className="w-full rounded-lg border px-3 py-2 text-sm"
                  rows={3}
                  placeholder="Optional description…"
                />
              </div>

              {/* Actions */}
              <div className="col-span-2 flex gap-2 pt-1">
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                >
                  {saving ? "Saving…" : modalMode === "add" ? "Create Item" : "Save Changes"}
                </button>
                <button
                  type="button"
                  onClick={closeModal}
                  className="rounded-lg border px-4 py-2 text-sm hover:bg-muted"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
