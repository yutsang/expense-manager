"use client";

import { useEffect, useState } from "react";
import { journalsApi, periodsApi, accountsApi, type JournalEntry, type Period, type Account } from "@/lib/api";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-yellow-100 text-yellow-800",
  posted: "bg-green-100 text-green-800",
  void: "bg-gray-100 text-gray-600 line-through",
};

function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLORS[status] ?? "bg-gray-100 text-gray-800";
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}

type LineInput = {
  account_id: string;
  debit: string;
  credit: string;
  description: string;
  currency: string;
};

function formatAmount(s: string) {
  const n = parseFloat(s);
  return isNaN(n) ? s : n.toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function totalDebit(lines: LineInput[]) {
  return lines.reduce((sum, l) => sum + (parseFloat(l.debit) || 0), 0);
}
function totalCredit(lines: LineInput[]) {
  return lines.reduce((sum, l) => sum + (parseFloat(l.credit) || 0), 0);
}

export default function JournalsPage() {
  const [journals, setJournals] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [periods, setPeriods] = useState<Period[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);

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
    if (pRes.items.length > 0) setFormPeriodId(pRes.items[0].id);
  }

  useEffect(() => {
    load();
  }, []);

  function updateLine(i: number, field: keyof LineInput, value: string) {
    setFormLines((prev) => {
      const next = [...prev];
      next[i] = { ...next[i], [field]: value };
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
    if (!formPeriodId) { alert("Select a period"); return; }
    const dr = totalDebit(formLines);
    const cr = totalCredit(formLines);
    if (Math.abs(dr - cr) > 0.0001) {
      alert(`Entry is unbalanced — debit ${dr.toFixed(2)} ≠ credit ${cr.toFixed(2)}`);
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
          description: l.description || undefined,
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
      alert(e instanceof Error ? e.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  async function handlePost(id: string) {
    try {
      await journalsApi.post(id);
      await load();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Post failed");
    }
  }

  async function handleVoid(id: string, number: string) {
    const reason = prompt(`Reason for voiding ${number}:`);
    if (reason === null) return;
    try {
      await journalsApi.void(id, reason);
      await load();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Void failed");
    }
  }

  const dr = totalDebit(formLines);
  const cr = totalCredit(formLines);
  const isBalanced = Math.abs(dr - cr) < 0.0001;

  return (
    <div className="p-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Journal Entries</h1>
          <p className="mt-1 text-sm text-muted-foreground">{journals.length} entries</p>
        </div>
        <button
          onClick={() => { setShowCreate(true); loadSupport(); }}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          New Entry
        </button>
      </div>

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
                  <td className="px-3 py-2 text-right">{dr.toFixed(2)}</td>
                  <td className="px-3 py-2 text-right">{cr.toFixed(2)}</td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Balance indicator */}
          <div className={`mb-3 text-xs font-medium ${isBalanced ? "text-green-600" : "text-red-500"}`}>
            {isBalanced ? "✓ Balanced" : `✗ Out of balance by ${Math.abs(dr - cr).toFixed(2)}`}
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
                  <td colSpan={7} className="px-4 py-8 text-center text-sm text-muted-foreground">
                    No journal entries yet.
                  </td>
                </tr>
              ) : (
                journals.map((je) => (
                  <tr key={je.id} className="hover:bg-muted/30">
                    <td className="px-4 py-2 font-mono text-sm">{je.number}</td>
                    <td className="px-4 py-2 text-sm">{je.date.slice(0, 10)}</td>
                    <td className="px-4 py-2 text-sm max-w-xs truncate">{je.description}</td>
                    <td className="px-4 py-2">
                      <StatusBadge status={je.status} />
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-sm">
                      {formatAmount(je.total_debit)}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-sm">
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
  );
}
