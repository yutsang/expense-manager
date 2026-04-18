"use client";

import { showToast } from "@/lib/toast";
import { useEffect, useState } from "react";
import { journalsApi, periodsApi, accountsApi, type JournalEntry, type Period, type Account } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { CsvImportExport } from "@/components/csv-import-export";
import { safeFmt, safeSum } from "@/lib/money-safe";

type LineInput = {
  account_id: string;
  debit: string;
  credit: string;
  description: string;
  currency: string;
};

function formatAmount(s: string) {
  return safeFmt(s, "AUD");
}

function totalDebit(lines: LineInput[]): string {
  return safeSum(lines.map((l) => l.debit));
}
function totalCredit(lines: LineInput[]): string {
  return safeSum(lines.map((l) => l.credit));
}

export default function JournalsPage() {
  const [journals, setJournals] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [periods, setPeriods] = useState<Period[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkProcessing, setBulkProcessing] = useState(false);

  // Create form state
  const [formDate, setFormDate] = useState(new Date().toISOString().slice(0, 10));
  const [formPeriodId, setFormPeriodId] = useState("");
  const [formDesc, setFormDesc] = useState("");
  const [formLines, setFormLines] = useState<LineInput[]>([
    { account_id: "", debit: "", credit: "", description: "", currency: "USD" },
    { account_id: "", debit: "", credit: "", description: "", currency: "USD" },
  ]);
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await journalsApi.list({ limit: 50 });
      setJournals(res.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load journals");
    } finally {
      setLoading(false);
    }
  }

  async function loadSupport() {
    const [pRes, aRes] = await Promise.all([
      periodsApi.list(),
      accountsApi.list(),
    ]);
    setPeriods(pRes.items.filter((p) => p.status === "open"));
    setAccounts(aRes.items);
    if (pRes.items.length > 0) setFormPeriodId(pRes.items[0]!.id);
  }

  useEffect(() => {
    load();
  }, []);

  function updateLine(i: number, field: keyof LineInput, value: string) {
    setFormLines((prev) => {
      const next = [...prev];
      const p = next[i] as LineInput;
      next[i] = { account_id: p.account_id, debit: p.debit, credit: p.credit, description: p.description, currency: p.currency, [field]: value };
      return next;
    });
  }

  function addLine() {
    setFormLines((prev) => [
      ...prev,
      { account_id: "", debit: "", credit: "", description: "", currency: "USD" },
    ]);
  }

  function removeLine(i: number) {
    setFormLines((prev) => prev.filter((_, idx) => idx !== i));
  }

  async function handleCreate() {
    if (!formPeriodId) { showToast("warning", "Select a period"); return; }
    const drStr = totalDebit(formLines);
    const crStr = totalCredit(formLines);
    if (drStr !== crStr) {
      showToast("error", "Entry is unbalanced", `Debit ${drStr} does not equal credit ${crStr}`);
      return;
    }
    setCreating(true);
    try {
      await journalsApi.create({
        date: formDate,
        period_id: formPeriodId,
        description: formDesc,
        lines: formLines.map((l) => ({
          account_id: l.account_id,
          debit: l.debit || "0",
          credit: l.credit || "0",
          description: l.description || null,
          currency: l.currency,
          fx_rate: "1",
        })),
      });
      setShowCreate(false);
      setFormDesc("");
      setFormLines([
        { account_id: "", debit: "", credit: "", description: "", currency: "USD" },
        { account_id: "", debit: "", credit: "", description: "", currency: "USD" },
      ]);
      await load();
    } catch (e: unknown) {
      showToast("error", "Create failed", e instanceof Error ? e.message : undefined);
    } finally {
      setCreating(false);
    }
  }

  async function handlePost(id: string) {
    try {
      await journalsApi.post(id);
      await load();
    } catch (e: unknown) {
      showToast("error", "Post failed", e instanceof Error ? e.message : undefined);
    }
  }

  async function handleVoid(id: string, number: string) {
    const reason = prompt(`Reason for voiding ${number}:`);
    if (reason === null) return;
    try {
      await journalsApi.void(id, reason);
      await load();
    } catch (e: unknown) {
      showToast("error", "Void failed", e instanceof Error ? e.message : undefined);
    }
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedIds.size === journals.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(journals.map((j) => j.id)));
    }
  }

  const selectedJournals = journals.filter((j) => selectedIds.has(j.id));
  const allSelectedDraft = selectedJournals.length > 0 && selectedJournals.every((j) => j.status === "draft");
  const allSelectedPosted = selectedJournals.length > 0 && selectedJournals.every((j) => j.status === "posted");

  async function handleBulkPost() {
    if (!allSelectedDraft) return;
    setBulkProcessing(true);
    const ids = Array.from(selectedIds);
    const results = await Promise.allSettled(ids.map((id) => journalsApi.post(id)));
    const succeeded = results.filter((r) => r.status === "fulfilled").length;
    const failed = results.filter((r) => r.status === "rejected").length;
    if (failed > 0) {
      showToast("warning", `${succeeded} posted, ${failed} failed`);
    } else {
      showToast("success", `${succeeded} journal(s) posted`);
    }
    setSelectedIds(new Set());
    setBulkProcessing(false);
    await load();
  }

  async function handleBulkVoid() {
    if (!allSelectedPosted) return;
    const reason = prompt("Reason for voiding selected entries:");
    if (reason === null) return;
    setBulkProcessing(true);
    const ids = Array.from(selectedIds);
    const results = await Promise.allSettled(ids.map((id) => journalsApi.void(id, reason)));
    const succeeded = results.filter((r) => r.status === "fulfilled").length;
    const failed = results.filter((r) => r.status === "rejected").length;
    if (failed > 0) {
      showToast("warning", `${succeeded} voided, ${failed} failed`);
    } else {
      showToast("success", `${succeeded} journal(s) voided`);
    }
    setSelectedIds(new Set());
    setBulkProcessing(false);
    await load();
  }

  const dr = totalDebit(formLines);
  const cr = totalCredit(formLines);
  const isBalanced = dr === cr;

  const headerActions = (
    <>
      <CsvImportExport
        entityType="journals"
        templateUrl="/v1/journals/csv-template"
        importUrl="/v1/journals/import"
        onImportComplete={() => void load()}
      />
      <button
        onClick={() => { setShowCreate(true); void loadSupport(); }}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
      >
        New Entry
      </button>
    </>
  );

  return (
    <>
      <PageHeader
        title="Journal Entries"
        subtitle={`${journals.length} entries`}
        actions={headerActions}
      />
    <div className="mx-auto max-w-7xl px-6 py-6">

      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {/* Create form */}
      {showCreate && (
        <div className="mb-6 rounded-lg border bg-card p-4 shadow-sm">
          <h2 className="mb-4 text-base font-semibold">New Journal Entry</h2>
          <div className="mb-3 grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium">Date</label>
              <input
                type="date"
                value={formDate}
                onChange={(e) => setFormDate(e.target.value)}
                className="w-full rounded border px-2 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">Period</label>
              <select
                value={formPeriodId}
                onChange={(e) => setFormPeriodId(e.target.value)}
                className="w-full rounded border px-2 py-1.5 text-sm"
              >
                {periods.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium">Description</label>
              <input
                value={formDesc}
                onChange={(e) => setFormDesc(e.target.value)}
                placeholder="Entry description"
                className="w-full rounded border px-2 py-1.5 text-sm"
              />
            </div>
          </div>

          {/* Lines grid */}
          <div className="mb-3 overflow-hidden rounded border">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b bg-muted/40 text-xs font-medium text-muted-foreground">
                  <th className="px-3 py-2">Account</th>
                  <th className="px-3 py-2">Description</th>
                  <th className="w-28 px-3 py-2 text-right">Debit</th>
                  <th className="w-28 px-3 py-2 text-right">Credit</th>
                  <th className="w-8 px-3 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {formLines.map((line, i) => (
                  <tr key={i}>
                    <td className="px-2 py-1">
                      <select
                        value={line.account_id}
                        onChange={(e) => updateLine(i, "account_id", e.target.value)}
                        className="w-full rounded border px-1.5 py-1 text-sm"
                      >
                        <option value="">Select account…</option>
                        {accounts.map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.code} — {a.name}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-2 py-1">
                      <input
                        value={line.description}
                        onChange={(e) => updateLine(i, "description", e.target.value)}
                        placeholder="Optional"
                        className="w-full rounded border px-1.5 py-1 text-sm"
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={line.debit}
                        onChange={(e) => updateLine(i, "debit", e.target.value)}
                        className="w-full rounded border px-1.5 py-1 text-right text-sm"
                        disabled={!!line.credit && parseFloat(line.credit) > 0}
                      />
                    </td>
                    <td className="px-2 py-1">
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={line.credit}
                        onChange={(e) => updateLine(i, "credit", e.target.value)}
                        className="w-full rounded border px-1.5 py-1 text-right text-sm"
                        disabled={!!line.debit && parseFloat(line.debit) > 0}
                      />
                    </td>
                    <td className="px-2 py-1 text-center">
                      {formLines.length > 2 && (
                        <button
                          onClick={() => removeLine(i)}
                          className="text-xs text-red-400 hover:text-red-600"
                        >
                          ✕
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t bg-muted/20 text-sm font-medium">
                  <td colSpan={2} className="px-3 py-2 text-muted-foreground">
                    Totals
                  </td>
                  <td className="px-3 py-2 text-right">{dr}</td>
                  <td className="px-3 py-2 text-right">{cr}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Balance indicator */}
          <div className={`mb-3 text-xs font-medium ${isBalanced ? "text-green-600" : "text-red-500"}`}>
            {isBalanced ? "✓ Balanced" : "✗ Out of balance"}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={addLine}
              className="text-sm text-blue-600 hover:underline"
            >
              + Add line
            </button>
            <div className="flex-1" />
            <button
              onClick={() => setShowCreate(false)}
              className="rounded border px-3 py-1.5 text-sm hover:bg-muted"
            >
              Cancel
            </button>
            <button
              onClick={handleCreate}
              disabled={creating || !isBalanced}
              className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50 hover:bg-primary/90"
            >
              {creating ? "Saving…" : "Save Draft"}
            </button>
          </div>
        </div>
      )}

      {/* Journal list */}
      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          Loading journals…
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b bg-muted/40 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <th className="w-10 px-4 py-3">
                  <input
                    type="checkbox"
                    checked={journals.length > 0 && selectedIds.size === journals.length}
                    onChange={toggleSelectAll}
                    disabled={bulkProcessing || journals.length === 0}
                    className="h-4 w-4 rounded border-gray-300"
                  />
                </th>
                <th className="px-4 py-3">Number</th>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">Description</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Debit</th>
                <th className="px-4 py-3 text-right">Credit</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {journals.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-sm text-muted-foreground">
                    No journal entries yet.
                  </td>
                </tr>
              ) : (
                journals.map((je) => (
                  <tr key={je.id} className={`hover:bg-muted/30 ${selectedIds.has(je.id) ? "bg-primary/5" : ""}`}>
                    <td className="px-4 py-2">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(je.id)}
                        onChange={() => toggleSelect(je.id)}
                        disabled={bulkProcessing}
                        className="h-4 w-4 rounded border-gray-300"
                      />
                    </td>
                    <td className="px-4 py-2 font-mono text-sm">{je.number}</td>
                    <td className="px-4 py-2 text-sm">{je.date.slice(0, 10)}</td>
                    <td className="px-4 py-2 text-sm max-w-xs truncate">{je.description}</td>
                    <td className="px-4 py-2">
                      <StatusBadge status={je.status} />
                    </td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums text-sm">
                      {formatAmount(je.total_debit)}
                    </td>
                    <td className="px-4 py-2 text-right font-mono tabular-nums text-sm">
                      {formatAmount(je.total_credit)}
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex gap-2">
                        {je.status === "draft" && (
                          <button
                            onClick={() => handlePost(je.id)}
                            className="text-xs text-green-600 hover:underline"
                          >
                            Post
                          </button>
                        )}
                        {je.status === "posted" && (
                          <button
                            onClick={() => handleVoid(je.id, je.number)}
                            className="text-xs text-red-500 hover:underline"
                          >
                            Void
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>

      {/* Floating bulk action bar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-lg bg-gray-900 px-6 py-3 shadow-xl">
          <div className="flex items-center gap-4 text-sm text-white">
            <span className="font-medium">{selectedIds.size} selected</span>
            <div className="h-4 w-px bg-gray-600" />
            {allSelectedDraft && (
              <button
                onClick={() => { void handleBulkPost(); }}
                disabled={bulkProcessing}
                className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700 disabled:opacity-50"
              >
                {bulkProcessing ? "Processing..." : "Post Selected"}
              </button>
            )}
            {allSelectedPosted && (
              <button
                onClick={() => { void handleBulkVoid(); }}
                disabled={bulkProcessing}
                className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {bulkProcessing ? "Processing..." : "Void Selected"}
              </button>
            )}
            <button
              onClick={() => setSelectedIds(new Set())}
              disabled={bulkProcessing}
              className="text-xs text-gray-400 hover:text-white disabled:opacity-50"
            >
              Clear
            </button>
          </div>
        </div>
      )}
    </>
  );
}
