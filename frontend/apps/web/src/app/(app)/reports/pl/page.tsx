"use client";

import { useState } from "react";
import { type PLReport, reportsApi } from "@/lib/api";
import { PageHeader } from "@/components/page-header";

function fmt(amount: string) {
  return new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD" }).format(
    parseFloat(amount)
  );
}

export default function PLPage() {
  const today = new Date().toISOString().slice(0, 10);
  const firstOfMonth = today.slice(0, 7) + "-01";

  const [fromDate, setFromDate] = useState(firstOfMonth);
  const [toDate, setToDate] = useState(today);
  const [report, setReport] = useState<PLReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    try {
      setLoading(true);
      setError(null);
      setReport(await reportsApi.pl(fromDate, toDate));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageHeader title="Profit & Loss" subtitle="Income statement for a date range" />
    <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">

      {/* Controls */}
      <div className="flex items-end gap-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">From</label>
          <input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)}
            className="rounded-lg border px-3 py-2 text-sm" />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">To</label>
          <input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)}
            className="rounded-lg border px-3 py-2 text-sm" />
        </div>
        <button onClick={run} disabled={loading}
          className="rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60">
          {loading ? "Running…" : "Run Report"}
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {report && (
        <div className="space-y-6">
          {/* Summary banner */}
          <div className={`rounded-xl border p-6 ${report.is_profitable ? "border-green-200 bg-green-50" : "border-red-200 bg-red-50"}`}>
            <div className="grid grid-cols-3 gap-6 text-center">
              <div>
                <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">Total Revenue</p>
                <p className="mt-1 text-2xl font-bold text-green-700">{fmt(report.total_revenue)}</p>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">Total Expenses</p>
                <p className="mt-1 text-2xl font-bold text-red-700">{fmt(report.total_expenses)}</p>
              </div>
              <div>
                <p className="text-xs font-medium uppercase tracking-widest text-muted-foreground">Net Profit</p>
                <p className={`mt-1 text-2xl font-bold ${report.is_profitable ? "text-green-700" : "text-red-700"}`}>
                  {fmt(report.net_profit)}
                </p>
              </div>
            </div>
          </div>

          {/* Revenue */}
          <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
            <div className="border-b bg-green-50 px-4 py-3">
              <h2 className="font-semibold text-green-800">Revenue</h2>
            </div>
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/30">
                <tr>
                  <th className="px-4 py-2 text-left font-medium text-muted-foreground">Code</th>
                  <th className="px-4 py-2 text-left font-medium text-muted-foreground">Account</th>
                  <th className="px-4 py-2 text-right font-medium text-muted-foreground">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {report.revenue_lines.length === 0 ? (
                  <tr><td colSpan={3} className="px-4 py-4 text-center text-muted-foreground text-xs">No revenue recorded in this period</td></tr>
                ) : report.revenue_lines.map((r) => (
                  <tr key={r.account_id} className="hover:bg-muted/20">
                    <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">{r.code}</td>
                    <td className="px-4 py-2.5">{r.name}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{fmt(r.balance)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="border-t bg-green-50">
                <tr>
                  <td colSpan={2} className="px-4 py-2.5 font-semibold text-green-800">Total Revenue</td>
                  <td className="px-4 py-2.5 text-right font-bold font-mono text-green-800">{fmt(report.total_revenue)}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Expenses */}
          <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
            <div className="border-b bg-red-50 px-4 py-3">
              <h2 className="font-semibold text-red-800">Expenses</h2>
            </div>
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/30">
                <tr>
                  <th className="px-4 py-2 text-left font-medium text-muted-foreground">Code</th>
                  <th className="px-4 py-2 text-left font-medium text-muted-foreground">Account</th>
                  <th className="px-4 py-2 text-right font-medium text-muted-foreground">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {report.expense_lines.length === 0 ? (
                  <tr><td colSpan={3} className="px-4 py-4 text-center text-muted-foreground text-xs">No expenses recorded in this period</td></tr>
                ) : report.expense_lines.map((r) => (
                  <tr key={r.account_id} className="hover:bg-muted/20">
                    <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">{r.code}</td>
                    <td className="px-4 py-2.5">{r.name}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{fmt(r.balance)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="border-t bg-red-50">
                <tr>
                  <td colSpan={2} className="px-4 py-2.5 font-semibold text-red-800">Total Expenses</td>
                  <td className="px-4 py-2.5 text-right font-bold font-mono text-red-800">{fmt(report.total_expenses)}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Net */}
          <div className={`rounded-xl border p-4 text-right ${report.is_profitable ? "border-green-300 bg-green-50" : "border-red-300 bg-red-50"}`}>
            <span className="text-sm font-medium text-muted-foreground mr-4">Net Profit / (Loss)</span>
            <span className={`text-xl font-bold ${report.is_profitable ? "text-green-700" : "text-red-700"}`}>
              {report.is_profitable ? "" : "("}{fmt(report.net_profit)}{report.is_profitable ? "" : ")"}
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
