"use client";

import { useEffect, useState, useCallback } from "react";
import { taxCodesApi, type TaxCode } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { CsvImportExport } from "@/components/csv-import-export";
import { Plus, X, Check, Percent } from "lucide-react";

const TAX_TYPES = ["output", "input", "exempt", "zero"] as const;
type TaxType = typeof TAX_TYPES[number];

interface TaxCodeForm {
  code: string;
  name: string;
  rate: string;
  tax_type: TaxType;
}

const EMPTY_FORM: TaxCodeForm = { code: "", name: "", rate: "", tax_type: "output" };

// ── Helpers ───────────────────────────────────────────────────────────────────

function taxTypeBadge(type: string) {
  const map: Record<string, string> = {
    output:  "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
    input:   "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
    exempt:  "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
    zero:    "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  };
  const cls = map[type] ?? "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize ${cls}`}>
      {type}
    </span>
  );
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function Toast({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 3000);
    return () => clearTimeout(t);
  }, [onDismiss]);
  return (
    <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-3 text-sm text-white shadow-lg dark:bg-gray-100 dark:text-gray-900">
      <Check className="h-4 w-4 shrink-0 text-green-400 dark:text-green-600" />
      {message}
    </div>
  );
}

// ── Modal ─────────────────────────────────────────────────────────────────────

interface ModalProps {
  title: string;
  onClose: () => void;
  form: TaxCodeForm;
  onChange: (f: TaxCodeForm) => void;
  onSubmit: (e: React.FormEvent) => void;
  submitting: boolean;
  submitLabel: string;
  error: string | null;
}

function TaxCodeModal({ title, onClose, form, onChange, onSubmit, submitting, submitLabel, error }: ModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-xl dark:border-gray-700 dark:bg-gray-900">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">{title}</h2>
          <button onClick={onClose} className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Code</label>
              <input
                required
                value={form.code}
                onChange={(e) => onChange({ ...form, code: e.target.value })}
                placeholder="GST"
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Rate %</label>
              <input
                required
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={form.rate}
                onChange={(e) => onChange({ ...form, rate: e.target.value })}
                placeholder="10"
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name</label>
            <input
              required
              value={form.name}
              onChange={(e) => onChange({ ...form, name: e.target.value })}
              placeholder="Goods & Services Tax"
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Type</label>
            <select
              value={form.tax_type}
              onChange={(e) => onChange({ ...form, tax_type: e.target.value as TaxType })}
              className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
            >
              {TAX_TYPES.map((t) => (
                <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Output = sales tax collected. Input = tax paid on purchases. Exempt/Zero = no tax.
            </p>
          </div>

          {error && (
            <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60 transition-colors"
            >
              {submitting && (
                <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
              )}
              {submitLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function TaxCodesPage() {
  const [taxCodes, setTaxCodes] = useState<TaxCode[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Create modal
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<TaxCodeForm>(EMPTY_FORM);
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  // Edit modal
  const [editTarget, setEditTarget] = useState<TaxCode | null>(null);
  const [editForm, setEditForm] = useState<TaxCodeForm>(EMPTY_FORM);
  const [editError, setEditError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  // Toast
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  async function load() {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await taxCodesApi.list({ active_only: false });
      setTaxCodes(res.items);
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : "Failed to load tax codes");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreateError(null);
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
      setToast("Tax code created");
      await load();
    } catch (err: unknown) {
      setCreateError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  function openEdit(tc: TaxCode) {
    setEditTarget(tc);
    setEditForm({ code: tc.code, name: tc.name, rate: tc.rate, tax_type: tc.tax_type as TaxType });
    setEditError(null);
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editTarget) return;
    setEditError(null);
    setEditing(true);
    try {
      await taxCodesApi.update(editTarget.id, editForm);
      setEditTarget(null);
      setToast("Tax code updated");
      await load();
    } catch (err: unknown) {
      setEditError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setEditing(false);
    }
  }

  async function handleToggleActive(tc: TaxCode) {
    try {
      await taxCodesApi.update(tc.id, { is_active: !tc.is_active });
      setToast(tc.is_active ? "Tax code archived" : "Tax code restored");
      await load();
    } catch (err: unknown) {
      setLoadError(err instanceof Error ? err.message : "Update failed");
    }
  }

  const addButton = (
    <>
      <CsvImportExport
        entityType="tax-codes"
        templateUrl="/v1/tax-codes/csv-template"
        importUrl="/v1/tax-codes/import"
        onImportComplete={() => void load()}
      />
      <button
        onClick={() => { setShowCreate(true); setCreateForm(EMPTY_FORM); setCreateError(null); }}
        className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
      >
        <Plus className="h-4 w-4" />
        Add Tax Code
      </button>
    </>
  );

  return (
    <>
      <PageHeader
        title="Tax Codes"
        subtitle="Manage VAT/GST/sales tax rates applied to invoices and bills"
        actions={addButton}
      />

      <div className="mx-auto max-w-5xl px-6 py-6 space-y-6">
        {loadError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
            {loadError}
          </div>
        )}

        {loading ? (
          <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
            <div className="flex items-center justify-center py-16 text-sm text-gray-400">
              <span className="h-5 w-5 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin mr-2" />
              Loading tax codes…
            </div>
          </div>
        ) : taxCodes.length === 0 ? (
          <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900 p-12 text-center">
            <Percent className="mx-auto mb-3 h-8 w-8 text-gray-300 dark:text-gray-600" />
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">No tax codes yet</p>
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Add your first tax code to apply rates to invoices and bills.
            </p>
            <button
              onClick={() => setShowCreate(true)}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 transition-colors"
            >
              <Plus className="h-3.5 w-3.5" /> Add Tax Code
            </button>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-800/50">
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Code</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Name</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Rate</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Type</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Status</th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {taxCodes.map((tc) => (
                  <tr
                    key={tc.id}
                    className={`transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50 ${tc.is_active ? "" : "opacity-50"}`}
                  >
                    <td className="px-4 py-3 font-mono text-xs font-medium text-gray-900 dark:text-gray-100">
                      {tc.code}
                    </td>
                    <td className="px-4 py-3 text-gray-700 dark:text-gray-300">{tc.name}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums text-gray-700 dark:text-gray-300">
                      {tc.rate}%
                    </td>
                    <td className="px-4 py-3">{taxTypeBadge(tc.tax_type)}</td>
                    <td className="px-4 py-3">
                      {tc.is_active ? (
                        <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                          Archived
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => openEdit(tc)}
                          className="text-xs font-medium text-indigo-600 hover:text-indigo-800 dark:text-indigo-400 dark:hover:text-indigo-300 transition-colors"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => void handleToggleActive(tc)}
                          className={`text-xs font-medium transition-colors ${
                            tc.is_active
                              ? "text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300"
                              : "text-green-600 hover:text-green-800 dark:text-green-400 dark:hover:text-green-300"
                          }`}
                        >
                          {tc.is_active ? "Archive" : "Restore"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {showCreate && (
        <TaxCodeModal
          title="Add Tax Code"
          onClose={() => setShowCreate(false)}
          form={createForm}
          onChange={setCreateForm}
          onSubmit={(e) => void handleCreate(e)}
          submitting={creating}
          submitLabel="Create"
          error={createError}
        />
      )}

      {editTarget && (
        <TaxCodeModal
          title={`Edit ${editTarget.code}`}
          onClose={() => setEditTarget(null)}
          form={editForm}
          onChange={setEditForm}
          onSubmit={(e) => void handleEdit(e)}
          submitting={editing}
          submitLabel="Save changes"
          error={editError}
        />
      )}

      {toast && <Toast message={toast} onDismiss={dismissToast} />}
    </>
  );
}
