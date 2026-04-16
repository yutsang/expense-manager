"use client";

import { useEffect, useState } from "react";
import { taxCodesApi, type TaxCode } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";

const TAX_TYPES = ["output", "input", "exempt", "zero"] as const;

interface CreateForm {
  code: string;
  name: string;
  rate: string;
  tax_type: string;
}

const EMPTY_FORM: CreateForm = { code: "", name: "", rate: "", tax_type: "output" };

export default function TaxCodesPage() {
  const [taxCodes, setTaxCodes] = useState<TaxCode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<CreateForm>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<TaxCode>>({});

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await taxCodesApi.list({ active_only: false });
      setTaxCodes(res.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load tax codes");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      await taxCodesApi.create({
        code: createForm.code,
        name: createForm.name,
        rate: createForm.rate,
        tax_type: createForm.tax_type,
      });
      setCreateForm(EMPTY_FORM);
      setShowCreate(false);
      await load();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  async function handleUpdate(id: string) {
    try {
      await taxCodesApi.update(id, editForm);
      setEditingId(null);
      setEditForm({});
      await load();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function handleToggleActive(tc: TaxCode) {
    const action = tc.is_active ? "archive" : "unarchive";
    if (!window.confirm(`${action.charAt(0).toUpperCase() + action.slice(1)} tax code "${tc.code}"?`)) return;
    try {
      await taxCodesApi.update(tc.id, { is_active: !tc.is_active });
      await load();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Update failed");
    }
  }

  function startEdit(tc: TaxCode) {
    setEditingId(tc.id);
    setEditForm({ code: tc.code, name: tc.name, rate: tc.rate, tax_type: tc.tax_type });
  }

  return (
    <>
      <PageHeader
        title="Tax Codes"
        subtitle="Manage VAT/GST tax rates"
        actions={
          <button
            onClick={() => setShowCreate((v) => !v)}
            className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
          >
            + New Tax Code
          </button>
        }
      />
      <div className="mx-auto max-w-5xl px-6 py-6 space-y-6">
        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}

        {/* Create form */}
        {showCreate && (
          <div className="rounded-lg border bg-card p-4 shadow-sm">
            <h2 className="mb-4 text-sm font-semibold">New Tax Code</h2>
            <form onSubmit={(e) => void handleCreate(e)} className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Code</label>
                <input
                  required
                  value={createForm.code}
                  onChange={(e) => setCreateForm((f) => ({ ...f, code: e.target.value }))}
                  className="w-full rounded-md border px-3 py-1.5 text-sm"
                  placeholder="GST"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Name</label>
                <input
                  required
                  value={createForm.name}
                  onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                  className="w-full rounded-md border px-3 py-1.5 text-sm"
                  placeholder="Goods & Services Tax"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Rate %</label>
                <input
                  required
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={createForm.rate}
                  onChange={(e) => setCreateForm((f) => ({ ...f, rate: e.target.value }))}
                  className="w-full rounded-md border px-3 py-1.5 text-sm"
                  placeholder="10"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Type</label>
                <select
                  value={createForm.tax_type}
                  onChange={(e) => setCreateForm((f) => ({ ...f, tax_type: e.target.value }))}
                  className="w-full rounded-md border px-3 py-1.5 text-sm"
                >
                  {TAX_TYPES.map((t) => (
                    <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-2 flex gap-2 sm:col-span-4">
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                >
                  {creating ? "Creating…" : "Create"}
                </button>
                <button
                  type="button"
                  onClick={() => { setShowCreate(false); setCreateForm(EMPTY_FORM); }}
                  className="rounded-md border px-4 py-1.5 text-sm font-medium hover:bg-muted"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            Loading tax codes…
          </div>
        ) : taxCodes.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
            No tax codes found. Create one to get started.
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b bg-muted/40 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-3">Code</th>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3 text-right">Rate</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Active</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {taxCodes.map((tc) => {
                  const isEditing = editingId === tc.id;
                  return (
                    <tr key={tc.id} className={`hover:bg-muted/20 ${tc.is_active ? "" : "opacity-50"}`}>
                      <td className="px-4 py-2.5 font-mono text-sm">
                        {isEditing ? (
                          <input
                            value={editForm.code ?? ""}
                            onChange={(e) => setEditForm((f) => ({ ...f, code: e.target.value }))}
                            className="w-24 rounded border px-2 py-1 text-sm font-mono"
                          />
                        ) : tc.code}
                      </td>
                      <td className="px-4 py-2.5 text-sm">
                        {isEditing ? (
                          <input
                            value={editForm.name ?? ""}
                            onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
                            className="w-full rounded border px-2 py-1 text-sm"
                          />
                        ) : tc.name}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono text-sm">
                        {isEditing ? (
                          <input
                            type="number"
                            min="0"
                            max="100"
                            step="0.01"
                            value={editForm.rate ?? ""}
                            onChange={(e) => setEditForm((f) => ({ ...f, rate: e.target.value }))}
                            className="w-20 rounded border px-2 py-1 text-sm text-right"
                          />
                        ) : `${tc.rate}%`}
                      </td>
                      <td className="px-4 py-2.5">
                        {isEditing ? (
                          <select
                            value={editForm.tax_type ?? ""}
                            onChange={(e) => setEditForm((f) => ({ ...f, tax_type: e.target.value }))}
                            className="rounded border px-2 py-1 text-sm"
                          >
                            {TAX_TYPES.map((t) => (
                              <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                            ))}
                          </select>
                        ) : (
                          <StatusBadge status={tc.tax_type} />
                        )}
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusBadge status={tc.is_active ? "active" : "archived"} />
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          {isEditing ? (
                            <>
                              <button
                                onClick={() => void handleUpdate(tc.id)}
                                className="text-xs text-green-600 hover:underline"
                              >
                                Save
                              </button>
                              <button
                                onClick={() => { setEditingId(null); setEditForm({}); }}
                                className="text-xs text-muted-foreground hover:underline"
                              >
                                Cancel
                              </button>
                            </>
                          ) : (
                            <>
                              <button
                                onClick={() => startEdit(tc)}
                                className="text-xs text-blue-600 hover:underline"
                              >
                                Edit
                              </button>
                              <button
                                onClick={() => void handleToggleActive(tc)}
                                className={`text-xs hover:underline ${tc.is_active ? "text-red-500" : "text-green-600"}`}
                              >
                                {tc.is_active ? "Archive" : "Unarchive"}
                              </button>
                            </>
                          )}
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
