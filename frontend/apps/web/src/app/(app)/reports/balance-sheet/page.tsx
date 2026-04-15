"use client";

import { useState } from "react";
import { type BalanceSheetReport, reportsApi } from "@/lib/api";
import { PageHeader } from "@/components/page-header";

function fmt(amount: string) {
  return new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD" }).format(
    parseFloat(amount)
  );
}

function Section({
  title,
  lines,
  total,
  colorClass,
}: {
  title: string;
  lines: { account_id: string; code: string; name: string; balance: string }[];
  total: string;
  colorClass: string;
}) {
  return (
    <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
      <div className={`border-b px-4 py-3 ${colorClass}`}>
        <h2 className="font-semibold">{title}</h2>
      </div>
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/30">
          <tr>
            <th className="px-4 py-2 text-left font-medium text-muted-foreground">Code</th>
            <th className="px-4 py-2 text-left font-medium text-muted-foreground">Account</th>
            <th className="px-4 py-2 text-right font-medium text-muted-foreground">Balance</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {lines.length === 0 ? (
            <tr>
              <td colSpan={3} className="px-4 py-4 text-center text-muted-foreground text-xs">
                No balances recorded
              </td>
            </tr>
          ) : (
            lines.map((r) => (
              <tr key={r.account_id} className="hover:bg-muted/20">
                <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">{r.code}</td>
                <td className="px-4 py-2.5">{r.name}</td>
                <td className="px-4 py-2.5 text-right font-mono">{fmt(r.balance)}</td>
              </tr>
            ))
          )}
        </tbody>
        <tfoot className="border-t bg-muted/20">
          <tr>
            <td colSpan={2} className="px-4 py-2.5 font-semibold">
              Total {title}
            </td>
            <td className="px-4 py-2.5 text-right font-bold font-mono">{fmt(total)}</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

export default function BalanceSheetPage() {
  const today = new Date().toISOString().slice(0, 10);
  const [asOf, setAsOf] = useState(today);
  const [report, setReport] = useState<BalanceSheetReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    try {
      setLoading(true);
      setError(null);
      setReport(await reportsApi.balanceSheet(asOf));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageHeader title="Balance Sheet" subtitle="Assets, liabilities and equity as of a date" />
    <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">

      <div className="flex items-end gap-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">As of</label>
          <input
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            className="rounded-lg border px-3 py-2 text-sm"
          />
        </div>
        <button
          onClick={run}
          disabled={loading}
          className="rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
        >
          {loading ? "Running…" : "Run Report"}
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {report && (
        <div className="space-y-6">
          {/* Balance check banner */}
          <div
            className={`rounded-xl border p-4 flex items-center justify-between ${
              report.is_balanced
                ? "border-green-200 bg-green-50"
                : "border-red-200 bg-red-50"
            }`}
          >
            <span className="text-sm font-medium">
              {report.is_balanced ? "Balanced — Assets = Liabilities + Equity" : "Out of balance — check your journals"}
            </span>
            <div className="flex gap-8 text-right">
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-widest">Assets</p>
                <p className="text-lg font-bold text-green-700">{fmt(report.assets.total)}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-widest">Liabilities + Equity</p>
                <p className="text-lg font-bold text-blue-700">{fmt(report.total_liabilities_and_equity)}</p>
              </div>
            </div>
          </div>

          <Section
            title="Assets"
            lines={report.assets.lines}
            total={report.assets.total}
            colorClass="bg-green-50 text-green-800"
          />
          <Section
            title="Liabilities"
            lines={report.liabilities.lines}
            total={report.liabilities.total}
            colorClass="bg-red-50 text-red-800"
          />
          <Section
            title="Equity"
            lines={report.equity.lines}
            total={report.equity.total}
            colorClass="bg-blue-50 text-blue-800"
          />

          <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-right">
            <span className="text-sm font-medium text-muted-foreground mr-4">
              Total Liabilities + Equity
            </span>
            <span className="text-xl font-bold text-blue-700">
              {fmt(report.total_liabilities_and_equity)}
            </span>
          </div>

          <p className="text-xs text-muted-foreground text-right">
            Generated {new Date(report.generated_at).toLocaleString("en-AU")} · Accrual basis
          </p>
        </div>
      )}
    </div>
    </>
  );
}
