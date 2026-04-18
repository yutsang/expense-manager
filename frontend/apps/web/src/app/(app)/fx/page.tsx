"use client";

import { useEffect, useState, useCallback } from "react";
import { fxApi, type FxRate, type FxRateUpsert } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { CsvImportExport } from "@/components/csv-import-export";
import { Plus, X, Check, TrendingUp, Info } from "lucide-react";

const CURRENCIES = ["USD", "EUR", "GBP", "AUD", "HKD", "SGD", "JPY", "CNY", "CAD", "NZD"] as const;

interface AddRateForm {
  from_currency: string;
  to_currency: string;
  rate: string;
  rate_date: string;
  source: string;
}

const today = new Date().toISOString().split("T")[0] ?? "";

const EMPTY_FORM: AddRateForm = {
  from_currency: "USD",
  to_currency: "AUD",
  rate: "",
  rate_date: today,
  source: "manual",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function sourceBadge(source: string) {
  const isManual = source === "manual";
  const cls = isManual
    ? "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
    : "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {source}
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

// ── Add Rate Modal ────────────────────────────────────────────────────────────

interface AddRateModalProps {
  form: AddRateForm;
  onChange: (f: AddRateForm) => void;
  onSubmit: (e: React.FormEvent) => void;
  onClose: () => void;
  submitting: boolean;
  error: string | null;
}

function AddRateModal({ form, onChange, onSubmit, onClose, submitting, error }: AddRateModalProps) {
  const inputCls =
    "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100";
  const labelCls = "block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-xl dark:border-gray-700 dark:bg-gray-900">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Add FX Rate</h2>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>From Currency</label>
              <select
                value={form.from_currency}
                onChange={(e) => onChange({ ...form, from_currency: e.target.value })}
                className={inputCls}
              >
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelCls}>To Currency</label>
              <select
                value={form.to_currency}
                onChange={(e) => onChange({ ...form, to_currency: e.target.value })}
                className={inputCls}
              >
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Rate</label>
              <input
                required
                type="number"
                min="0.000001"
                step="any"
                value={form.rate}
                onChange={(e) => onChange({ ...form, rate: e.target.value })}
                placeholder="1.5300"
                className={inputCls}
              />
            </div>
            <div>
              <label className={labelCls}>Rate Date</label>
              <input
                required
                type="date"
                value={form.rate_date}
                onChange={(e) => onChange({ ...form, rate_date: e.target.value })}
                className={inputCls}
              />
            </div>
          </div>

          <div>
            <label className={labelCls}>Source</label>
            <input
              value={form.source}
              onChange={(e) => onChange({ ...form, source: e.target.value })}
              placeholder="manual"
              className={inputCls}
            />
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
              Save Rate
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Currency Group ────────────────────────────────────────────────────────────

function CurrencyGroup({ baseCurrency, rates }: { baseCurrency: string; rates: FxRate[] }) {
  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-center gap-2 border-b border-gray-200 bg-gray-50 px-4 py-2.5 dark:border-gray-800 dark:bg-gray-800/50">
        <div className="flex h-6 w-10 items-center justify-center rounded bg-indigo-100 text-xs font-bold text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-400">
          {baseCurrency}
        </div>
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          {baseCurrency} base rates
        </span>
        <span className="ml-auto text-xs text-gray-400 dark:text-gray-500">{rates.length} pair{rates.length !== 1 ? "s" : ""}</span>
      </div>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-gray-100 dark:border-gray-800">
            <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">From</th>
            <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">To</th>
            <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Rate</th>
            <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Date</th>
            <th className="px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50 dark:divide-gray-800/60">
          {rates.map((r) => (
            <tr key={r.id} className="transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/40">
              <td className="px-4 py-3">
                <span className="inline-flex items-center justify-center rounded bg-gray-100 px-1.5 py-0.5 text-xs font-semibold text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                  {r.from_currency}
                </span>
              </td>
              <td className="px-4 py-3">
                <span className="inline-flex items-center justify-center rounded bg-gray-100 px-1.5 py-0.5 text-xs font-semibold text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                  {r.to_currency}
                </span>
              </td>
              <td className="px-4 py-3 text-right font-mono tabular-nums text-gray-900 dark:text-gray-100">
                {parseFloat(r.rate).toFixed(4)}
              </td>
              <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                {formatDate(r.rate_date)}
              </td>
              <td className="px-4 py-3">{sourceBadge(r.source)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function FxRatesPage() {
  const [rates, setRates] = useState<FxRate[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState<AddRateForm>(EMPTY_FORM);
  const [addError, setAddError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const [showLiveTooltip, setShowLiveTooltip] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const dismissToast = useCallback(() => setToast(null), []);

  async function load() {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await fxApi.list();
      setRates(data);
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : "Failed to load FX rates");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setAddError(null);
    setAdding(true);
    try {
      const body: FxRateUpsert = {
        from_currency: addForm.from_currency,
        to_currency: addForm.to_currency,
        rate: addForm.rate,
        rate_date: addForm.rate_date,
        source: addForm.source || "manual",
      };
      await fxApi.upsert(body);
      setShowAdd(false);
      setAddForm(EMPTY_FORM);
      setToast(`${addForm.from_currency} → ${addForm.to_currency} rate saved`);
      await load();
    } catch (err: unknown) {
      setAddError(err instanceof Error ? err.message : "Failed to save rate");
    } finally {
      setAdding(false);
    }
  }

  // Group rates by from_currency
  const groups = rates.reduce<Record<string, FxRate[]>>((acc, r) => {
    const key = r.from_currency;
    if (!acc[key]) acc[key] = [];
    acc[key]!.push(r);
    return acc;
  }, {});

  const sortedBases = Object.keys(groups).sort();

  const actions = (
    <div className="flex items-center gap-2">
      <CsvImportExport
        entityType="fx"
        templateUrl="/v1/fx/csv-template"
        importUrl="/v1/fx/import"
        onImportComplete={() => void load()}
      />
      {/* Fetch live rates — placeholder */}
      <div className="relative">
        <button
          onMouseEnter={() => setShowLiveTooltip(true)}
          onMouseLeave={() => setShowLiveTooltip(false)}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-500 cursor-not-allowed opacity-60 dark:border-gray-700 dark:text-gray-400"
          disabled
        >
          <Info className="h-4 w-4" />
          Fetch live rates
        </button>
        {showLiveTooltip && (
          <div className="absolute right-0 top-full mt-1.5 z-10 w-56 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs text-gray-600 shadow-md dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
            Connect an FX provider to enable
          </div>
        )}
      </div>

      <button
        onClick={() => {
          setShowAdd(true);
          setAddForm(EMPTY_FORM);
          setAddError(null);
        }}
        className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
      >
        <Plus className="h-4 w-4" />
        Add Rate
      </button>
    </div>
  );

  return (
    <>
      <PageHeader
        title="FX Rates"
        subtitle="Manage foreign exchange rates used for multi-currency transactions"
        actions={actions}
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
              Loading FX rates…
            </div>
          </div>
        ) : sortedBases.length === 0 ? (
          <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900 p-12 text-center">
            <TrendingUp className="mx-auto mb-3 h-8 w-8 text-gray-300 dark:text-gray-600" />
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">No FX rates yet</p>
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              Add your first exchange rate to support multi-currency transactions.
            </p>
            <button
              onClick={() => setShowAdd(true)}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 transition-colors"
            >
              <Plus className="h-3.5 w-3.5" /> Add Rate
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {sortedBases.map((base) => (
              <CurrencyGroup
                key={base}
                baseCurrency={base}
                rates={groups[base]!}
              />
            ))}
          </div>
        )}
      </div>

      {showAdd && (
        <AddRateModal
          form={addForm}
          onChange={setAddForm}
          onSubmit={(e) => void handleAdd(e)}
          onClose={() => setShowAdd(false)}
          submitting={adding}
          error={addError}
        />
      )}

      {toast && <Toast message={toast} onDismiss={dismissToast} />}
    </>
  );
}
