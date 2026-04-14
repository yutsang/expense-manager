"use client";

import { useState } from "react";
import { reportsApi, type TrialBalanceReport } from "@/lib/api";

function fmt(s: string) {
  const n = parseFloat(s);
  return isNaN(n) ? s : n.toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const TYPE_GROUP_ORDER = ["asset", "liability", "equity", "revenue", "expense"];

export default function TrialBalancePage() {
  const [asOf, setAsOf] = useState(new Date().toISOString().slice(0, 10));
  const [report, setReport] = useState<TrialBalanceReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const r = await reportsApi.trialBalance(asOf);
      setReport(r);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load report");
    } finally {
      setLoading(false);
    }
  }

  // Group rows by account type
  const grouped = report
    ? TYPE_GROUP_ORDER.map((type) => ({
        type,
        rows: report.rows.filter((r) => r.type === type),
      })).filter((g) => g.rows.length > 0)
    : [];

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">Trial Balance</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Summarised debit/credit totals for all accounts as of a date.
        </p>
      </div>

      {/* Controls */}
      <div className="mb-6 flex items-end gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium">As of date</label>
          <input
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            className="rounded border px-3 py-1.5 text-sm"
          />
        </div>
        <button
          onClick={run}
          disabled={loading}
          className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground disabled:opacity-50 hover:bg-primary/90"
        >
          {loading ? "Running…" : "Run Report"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {report && (
        <>
          <div className="mb-4 flex items-center gap-4 text-sm">
            <span className="text-muted-foreground">
              Generated {new Date(report.generated_at).toLocaleString()}
            </span>
            <span
              className={`font-medium ${
                report.is_balanced ? "text-green-600" : "text-red-600"
              }`}
            >
              {report.is_balanced ? "✓ Balanced" : "✗ Unbalanced"}
            </span>
          </div>

          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b bg-muted/40 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-3">Code</th>
                  <th className="px-4 py-3">Account</th>
                  <th className="px-4 py-3 text-right">Debit</th>
                  <th className="px-4 py-3 text-right">Credit</th>
                  <th className="px-4 py-3 text-right">Balance</th>
                </tr>
              </thead>
              <tbody>
                {grouped.map(({ type, rows }) => (
                  <>
                    <tr key={type} className="bg-muted/20">
                      <td
                        colSpan={5}
                        className="px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                      >
                        {type}
                      </td>
                    </tr>
                    {rows.map((row) => (
                      <tr key={row.account_id} className="border-t hover:bg-muted/30">
                        <td className="px-4 py-2 font-mono text-sm text-muted-foreground">
                          {row.code}
                        </td>
                        <td className="px-4 py-2 text-sm">{row.name}</td>
                        <td className="px-4 py-2 text-right font-mono text-sm">
                          {fmt(row.total_debit)}
                        </td>
                        <td className="px-4 py-2 text-right font-mono text-sm">
                          {fmt(row.total_credit)}
                        </td>
                        <td className={`px-4 py-2 text-right font-mono text-sm font-medium ${
                          parseFloat(row.balance) < 0 ? "text-red-600" : ""
                        }`}>
                          {fmt(row.balance)}
                        </td>
                      </tr>
                    ))}
                  </>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 bg-muted/40 font-semibold">
                  <td colSpan={2} className="px-4 py-3 text-sm">
                    Total
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-sm">
                    {fmt(report.total_debit)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-sm">
                    {fmt(report.total_credit)}
                  </td>
                  <td />
                </tr>
              </tfoot>
            </table>
          </div>
        </>
      )}

      {!report && !loading && (
        <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
          Select a date and click Run Report.
        </div>
      )}
    </div>
  );
}
