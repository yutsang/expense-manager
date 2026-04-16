"use client";

import { useEffect, useState } from "react";
import { ShieldCheck, ShieldAlert, Edit2, X, Check, ChevronDown, RefreshCw, Scan, ScanLine } from "lucide-react";
import { kycApi, sanctionsApi, type KycListItem, type KycUpdate, type SanctionsScreeningResult } from "@/lib/api";
import { PageHeader } from "@/components/page-header";

// ── Badge helpers ─────────────────────────────────────────────────────────────

function KycStatusBadge({ status }: { status: string }) {
  const cls =
    status === "approved"
      ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
      : status === "pending"
      ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
      : status === "expired" || status === "flagged"
      ? "bg-red-100 text-red-600 dark:bg-red-900/20 dark:text-red-400"
      : "bg-muted text-muted-foreground";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function SanctionsBadge({ status }: { status: string }) {
  const cls =
    status === "clear"
      ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
      : status === "flagged"
      ? "bg-red-100 text-red-600 dark:bg-red-900/20 dark:text-red-400"
      : status === "under_review"
      ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
      : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400";
  const label =
    status === "not_checked"
      ? "Not Checked"
      : status === "under_review"
      ? "Under Review"
      : status.charAt(0).toUpperCase() + status.slice(1);
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}

function ScreeningMatchBadge({ result }: { result: SanctionsScreeningResult | null | undefined }) {
  if (!result) {
    return <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400">Not screened</span>;
  }
  if (result.match_status === "confirmed_match") {
    return (
      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">
        <ShieldAlert className="mr-1 h-3 w-3" /> Flagged ({result.match_score})
      </span>
    );
  }
  if (result.match_status === "potential_match") {
    return (
      <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
        Review ({result.match_score})
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
      Clear
    </span>
  );
}

function relativeTime(isoStr: string): string {
  const diff = Date.now() - new Date(isoStr).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ── Date rendering with color cues ────────────────────────────────────────────

function ExpiryCell({ dateStr }: { dateStr: string | null }) {
  if (!dateStr) return <span className="text-muted-foreground text-xs">—</span>;
  const d = new Date(dateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.floor((d.getTime() - today.getTime()) / 86400000);

  let cls = "text-foreground";
  if (diff < 0) cls = "text-red-600 dark:text-red-400 font-medium";
  else if (diff < 30) cls = "text-red-500 dark:text-red-400";
  else if (diff < 90) cls = "text-yellow-600 dark:text-yellow-400";

  return <span className={`text-xs ${cls}`}>{dateStr}</span>;
}

function PoaCell({ dateStr }: { dateStr: string | null }) {
  if (!dateStr) return <span className="text-muted-foreground text-xs">—</span>;
  const d = new Date(dateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const ageYears = (today.getTime() - d.getTime()) / (86400000 * 365);

  let cls = "text-foreground";
  if (ageYears > 3) cls = "text-red-600 dark:text-red-400 font-medium";
  else if (ageYears > 2.5) cls = "text-yellow-600 dark:text-yellow-400";

  return <span className={`text-xs ${cls}`}>{dateStr}</span>;
}

// ── Edit slide-over ───────────────────────────────────────────────────────────

interface EditPanelProps {
  item: KycListItem;
  onClose: () => void;
  onSaved: (updated: KycListItem) => void;
}

function EditPanel({ item, onClose, onSaved }: EditPanelProps) {
  const [form, setForm] = useState<KycUpdate>({
    id_type: item.id_type ?? undefined,
    id_number: item.id_number ?? undefined,
    id_expiry_date: item.id_expiry_date ?? undefined,
    poa_type: item.poa_type ?? undefined,
    poa_date: item.poa_date ?? undefined,
    sanctions_status: item.sanctions_status,
    kyc_status: item.kyc_status,
    kyc_approved_by: item.kyc_approved_by ?? undefined,
    last_review_date: item.last_review_date ?? undefined,
    next_review_date: item.next_review_date ?? undefined,
    notes: item.notes ?? undefined,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set(key: keyof KycUpdate, value: string) {
    setForm((f) => ({ ...f, [key]: value || undefined }));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await kycApi.update(item.contact_id, form);
      onSaved({ ...item, ...form });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="fixed inset-0 bg-black/30" onClick={onClose} />
      <div className="relative w-full max-w-md bg-white dark:bg-gray-900 shadow-2xl flex flex-col h-full overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b dark:border-gray-800 sticky top-0 bg-white dark:bg-gray-900 z-10">
          <div>
            <h2 className="font-semibold text-sm">{item.contact_name}</h2>
            <p className="text-xs text-muted-foreground">KYC / Sanctions Record</p>
          </div>
          <button onClick={onClose} className="rounded p-1 hover:bg-muted transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {error && (
          <div className="mx-5 mt-4 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-900/20 dark:border-red-700 dark:text-red-400">
            {error}
          </div>
        )}

        <div className="flex-1 px-5 py-4 space-y-5">
          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">Identity Document</legend>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">ID Type</label>
                <select
                  value={form.id_type ?? ""}
                  onChange={(e) => set("id_type", e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring dark:bg-gray-800 dark:border-gray-700"
                >
                  <option value="">— Select —</option>
                  <option value="passport">Passport</option>
                  <option value="national_id">National ID</option>
                  <option value="drivers_license">Driver&apos;s License</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">ID Number</label>
                <input
                  type="text"
                  value={form.id_number ?? ""}
                  onChange={(e) => set("id_number", e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring dark:bg-gray-800 dark:border-gray-700"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">ID Expiry Date</label>
                <input
                  type="date"
                  value={form.id_expiry_date ?? ""}
                  onChange={(e) => set("id_expiry_date", e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring dark:bg-gray-800 dark:border-gray-700"
                />
              </div>
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">Proof of Address</legend>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">POA Type</label>
                <select
                  value={form.poa_type ?? ""}
                  onChange={(e) => set("poa_type", e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring dark:bg-gray-800 dark:border-gray-700"
                >
                  <option value="">— Select —</option>
                  <option value="utility_bill">Utility Bill</option>
                  <option value="bank_statement">Bank Statement</option>
                  <option value="tax_document">Tax Document</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">POA Date</label>
                <input
                  type="date"
                  value={form.poa_date ?? ""}
                  onChange={(e) => set("poa_date", e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring dark:bg-gray-800 dark:border-gray-700"
                />
              </div>
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">Compliance Status</legend>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">KYC Status</label>
                <select
                  value={form.kyc_status ?? "pending"}
                  onChange={(e) => set("kyc_status", e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring dark:bg-gray-800 dark:border-gray-700"
                >
                  <option value="pending">Pending</option>
                  <option value="approved">Approved</option>
                  <option value="expired">Expired</option>
                  <option value="flagged">Flagged</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Sanctions Status</label>
                <select
                  value={form.sanctions_status ?? "not_checked"}
                  onChange={(e) => set("sanctions_status", e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring dark:bg-gray-800 dark:border-gray-700"
                >
                  <option value="not_checked">Not Checked</option>
                  <option value="clear">Clear</option>
                  <option value="flagged">Flagged</option>
                  <option value="under_review">Under Review</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Approved By</label>
                <input
                  type="text"
                  value={form.kyc_approved_by ?? ""}
                  onChange={(e) => set("kyc_approved_by", e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring dark:bg-gray-800 dark:border-gray-700"
                />
              </div>
            </div>
          </fieldset>

          <fieldset>
            <legend className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">Review Schedule</legend>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Last Review Date</label>
                <input
                  type="date"
                  value={form.last_review_date ?? ""}
                  onChange={(e) => set("last_review_date", e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring dark:bg-gray-800 dark:border-gray-700"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">Next Review Date</label>
                <input
                  type="date"
                  value={form.next_review_date ?? ""}
                  onChange={(e) => set("next_review_date", e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring dark:bg-gray-800 dark:border-gray-700"
                />
              </div>
            </div>
          </fieldset>

          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">Notes</label>
            <textarea
              rows={3}
              value={form.notes ?? ""}
              onChange={(e) => set("notes", e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring resize-none dark:bg-gray-800 dark:border-gray-700"
            />
          </div>
        </div>

        <div className="sticky bottom-0 px-5 py-4 border-t bg-white dark:bg-gray-900 dark:border-gray-800 flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 rounded-lg border border-input px-4 py-2 text-sm font-medium text-foreground hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => { void handleSave(); }}
            disabled={saving}
            className="flex-1 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
          >
            {saving ? (
              <span className="h-4 w-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
            ) : (
              <Check className="h-4 w-4" />
            )}
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function KycPage() {
  const [items, setItems] = useState<KycListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<KycListItem | null>(null);
  const [filterKyc, setFilterKyc] = useState<string>("");
  const [filterSanctions, setFilterSanctions] = useState<string>("");
  const [screeningResults, setScreeningResults] = useState<Map<string, SanctionsScreeningResult>>(new Map());
  const [refreshing, setRefreshing] = useState(false);
  const [screeningId, setScreeningId] = useState<string | null>(null);
  const [screeningAll, setScreeningAll] = useState(false);
  const [screenAllProgress, setScreenAllProgress] = useState(0);

  useEffect(() => {
    kycApi
      .list()
      .then((rows) => {
        setItems(rows);
        // Load existing screen results for each contact
        rows.forEach((row) => {
          sanctionsApi
            .getScreenResult(row.contact_id)
            .then((result) => {
              if (result) {
                setScreeningResults((prev) => new Map(prev).set(row.contact_id, result));
              }
            })
            .catch(() => {/* silently ignore — result not yet available */});
        });
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  function handleSaved(updated: KycListItem) {
    setItems((prev) =>
      prev.map((it) => (it.contact_id === updated.contact_id ? updated : it))
    );
    setEditing(null);
  }

  async function handleRefreshLists() {
    setRefreshing(true);
    try {
      await sanctionsApi.refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }

  async function handleScreen(contactId: string) {
    setScreeningId(contactId);
    try {
      const result = await sanctionsApi.screenContact(contactId);
      setScreeningResults((prev) => new Map(prev).set(contactId, result));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Screening failed");
    } finally {
      setScreeningId(null);
    }
  }

  async function handleScreenAll() {
    setScreeningAll(true);
    setScreenAllProgress(0);
    const contacts = items.map((it) => it.contact_id);
    let done = 0;
    for (const contactId of contacts) {
      try {
        const result = await sanctionsApi.screenContact(contactId);
        setScreeningResults((prev) => new Map(prev).set(contactId, result));
      } catch {
        // continue
      }
      done++;
      setScreenAllProgress(Math.round((done / contacts.length) * 100));
    }
    setScreeningAll(false);
  }

  function handleDismissMatch(contactId: string) {
    // Mark as clear manually by updating KYC sanctions_status to "clear"
    kycApi.update(contactId, { sanctions_status: "clear" }).then((updated) => {
      setItems((prev) => prev.map((it) =>
        it.contact_id === contactId ? { ...it, sanctions_status: "clear" } : it
      ));
      // Remove from screening results map to show "not screened" until next screen
      setScreeningResults((prev) => {
        const next = new Map(prev);
        const existing = next.get(contactId);
        if (existing) next.set(contactId, { ...existing, match_status: "clear", match_score: 0 });
        return next;
      });
    }).catch(() => null);
  }

  const filtered = items.filter((it) => {
    if (filterKyc && it.kyc_status !== filterKyc) return false;
    if (filterSanctions && it.sanctions_status !== filterSanctions) return false;
    return true;
  });

  return (
    <>
      <PageHeader
        title="KYC / Sanctions"
        subtitle="Know Your Customer compliance and sanctions screening"
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => { void handleScreenAll(); }}
              disabled={screeningAll || screeningId !== null}
              className="inline-flex items-center gap-1.5 rounded-lg border border-input px-3 py-1.5 text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-60"
            >
              <ScanLine className="h-4 w-4" />
              {screeningAll ? `Screening… ${screenAllProgress}%` : "Screen All"}
            </button>
            <button
              onClick={() => { void handleRefreshLists(); }}
              disabled={refreshing}
              className="inline-flex items-center gap-1.5 rounded-lg border border-input px-3 py-1.5 text-sm font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-60"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
              Refresh Lists
            </button>
          </div>
        }
      />

      <div className="mx-auto max-w-7xl px-6 py-6 space-y-4">
        {/* Filter bar */}
        <div className="flex flex-wrap gap-3">
          <div className="relative">
            <select
              value={filterKyc}
              onChange={(e) => setFilterKyc(e.target.value)}
              className="appearance-none rounded-lg border border-input bg-background pl-3 pr-8 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring dark:bg-gray-800 dark:border-gray-700"
            >
              <option value="">All KYC Status</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="expired">Expired</option>
              <option value="flagged">Flagged</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-muted-foreground" />
          </div>
          <div className="relative">
            <select
              value={filterSanctions}
              onChange={(e) => setFilterSanctions(e.target.value)}
              className="appearance-none rounded-lg border border-input bg-background pl-3 pr-8 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring dark:bg-gray-800 dark:border-gray-700"
            >
              <option value="">All Sanctions Status</option>
              <option value="not_checked">Not Checked</option>
              <option value="clear">Clear</option>
              <option value="flagged">Flagged</option>
              <option value="under_review">Under Review</option>
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-2 h-4 w-4 text-muted-foreground" />
          </div>
          {(filterKyc || filterSanctions) && (
            <button
              onClick={() => { setFilterKyc(""); setFilterSanctions(""); }}
              className="rounded-lg border border-input px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted transition-colors"
            >
              Clear filters
            </button>
          )}
        </div>

        {error && (
          <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-900/20 dark:border-red-700 dark:text-red-400">
            {error}
          </div>
        )}

        {loading ? (
          <div className="rounded-xl border bg-card shadow-sm p-6 space-y-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-5 animate-pulse rounded bg-muted" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-xl border bg-card shadow-sm p-12 text-center">
            <ShieldCheck className="mx-auto mb-3 h-10 w-10 text-muted-foreground/30" />
            <p className="text-sm font-medium text-muted-foreground">
              {items.length === 0 ? "No contacts yet" : "No contacts match the selected filters"}
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/40">
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Contact</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Type</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">KYC Status</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Sanctions</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Screen Result</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Screened</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">ID Type</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">ID Expiry</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">POA Date</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Last Review</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {filtered.map((item) => (
                    <tr key={item.contact_id} className="hover:bg-muted/20 transition-colors">
                      <td className="px-4 py-3 font-medium text-foreground">{item.contact_name}</td>
                      <td className="px-4 py-3 text-muted-foreground capitalize text-xs">{item.contact_type}</td>
                      <td className="px-4 py-3"><KycStatusBadge status={item.kyc_status} /></td>
                      <td className="px-4 py-3"><SanctionsBadge status={item.sanctions_status} /></td>
                      <td className="px-4 py-3">
                        <ScreeningMatchBadge result={screeningResults.get(item.contact_id)} />
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {screeningResults.get(item.contact_id)
                          ? relativeTime(screeningResults.get(item.contact_id)!.screened_at)
                          : <span className="text-muted-foreground/50">—</span>}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {item.id_type
                          ? item.id_type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
                          : <span className="text-muted-foreground/50">—</span>}
                      </td>
                      <td className="px-4 py-3"><ExpiryCell dateStr={item.id_expiry_date} /></td>
                      <td className="px-4 py-3"><PoaCell dateStr={item.poa_date} /></td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {item.last_review_date ?? <span className="text-muted-foreground/50">—</span>}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {/* Dismiss button — shown when match needs review */}
                          {(() => {
                            const sr = screeningResults.get(item.contact_id);
                            return sr && (sr.match_status === "potential_match" || sr.match_status === "confirmed_match") ? (
                              <button
                                onClick={() => handleDismissMatch(item.contact_id)}
                                title="Mark as false positive / clear"
                                className="inline-flex items-center gap-1 rounded-md border border-input px-2.5 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-amber-900/20 transition-colors"
                              >
                                <X className="h-3 w-3" />
                                Dismiss
                              </button>
                            ) : null;
                          })()}
                          <button
                            onClick={() => { void handleScreen(item.contact_id); }}
                            disabled={screeningId === item.contact_id || screeningAll}
                            className="inline-flex items-center gap-1 rounded-md border border-input px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors disabled:opacity-60"
                          >
                            {screeningId === item.contact_id ? (
                              <span className="h-3 w-3 rounded-full border-2 border-current border-t-transparent animate-spin" />
                            ) : (
                              <Scan className="h-3 w-3" />
                            )}
                            Screen
                          </button>
                          <button
                            onClick={() => setEditing(item)}
                            className="inline-flex items-center gap-1 rounded-md border border-input px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-muted transition-colors"
                          >
                            <Edit2 className="h-3 w-3" />
                            Edit
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {editing && (
        <EditPanel
          item={editing}
          onClose={() => setEditing(null)}
          onSaved={handleSaved}
        />
      )}
    </>
  );
}
