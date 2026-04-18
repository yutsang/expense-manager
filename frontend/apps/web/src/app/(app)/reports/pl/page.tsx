"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { type PLReport, type PLLine, reportsApi } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { ExportDropdown } from "@/components/export-dropdown";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

function fmt(amount: string) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    parseFloat(amount)
  );
}

function PLChart({ report }: { report: PLReport }) {
  const chartData = [
    ...report.revenue_lines.slice(0, 4).map((r) => ({
      name: r.name.slice(0, 15),
      Revenue: parseFloat(r.balance),
      Expenses: 0,
    })),
    ...report.expense_lines.slice(0, 4).map((r) => ({
      name: r.name.slice(0, 15),
      Revenue: 0,
      Expenses: parseFloat(r.balance),
    })),
  ];

  if (chartData.length === 0) return null;

  return (
    <div className="rounded-xl border bg-card shadow-sm p-4">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
        Revenue vs Expenses — Top Accounts
      </h3>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={chartData} margin={{ top: 0, right: 16, left: 0, bottom: 40 }}>
          <XAxis
            dataKey="name"
            tick={{ fontSize: 11 }}
            angle={-30}
            textAnchor="end"
            interval={0}
          />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
          <Tooltip formatter={(v) => fmt(String(v ?? 0))} />
          <Legend />
          <Bar dataKey="Revenue" fill="#6366f1" radius={[3, 3, 0, 0]} />
          <Bar dataKey="Expenses" fill="#f43f5e" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

type CompareOption = "none" | "prior_month" | "same_month_last_year";

function computeComparisonDates(
  from: string,
  to: string,
  mode: CompareOption
): { from: string; to: string } | null {
  if (mode === "none") return null;
  const fromD = new Date(from + "T00:00:00");
  const toD = new Date(to + "T00:00:00");
  if (mode === "prior_month") {
    const pFrom = new Date(fromD);
    pFrom.setMonth(pFrom.getMonth() - 1);
    const pTo = new Date(toD);
    pTo.setMonth(pTo.getMonth() - 1);
    return { from: pFrom.toISOString().slice(0, 10), to: pTo.toISOString().slice(0, 10) };
  }
  // same_month_last_year
  const pFrom = new Date(fromD);
  pFrom.setFullYear(pFrom.getFullYear() - 1);
  const pTo = new Date(toD);
  pTo.setFullYear(pTo.getFullYear() - 1);
  return { from: pFrom.toISOString().slice(0, 10), to: pTo.toISOString().slice(0, 10) };
}

function fmtVariance(current: string, prior: string): { dollar: string; pct: string; isPositive: boolean } {
  const c = parseFloat(current);
  const p = parseFloat(prior);
  const diff = c - p;
  const pct = Math.abs(p) > 0.001 ? (diff / Math.abs(p)) * 100 : 0;
  return {
    dollar: new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(diff),
    pct: Math.abs(p) > 0.001 ? `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%` : "N/A",
    isPositive: diff >= 0,
  };
}

function findPriorBalance(lines: PLLine[], accountId: string): string {
  const match = lines.find((l) => l.account_id === accountId);
  return match ? match.balance : "0";
}

export default function PLPage() {
  const today = new Date().toISOString().slice(0, 10);
  const firstOfMonth = today.slice(0, 7) + "-01";

  const [fromDate, setFromDate] = useState(firstOfMonth);
  const [toDate, setToDate] = useState(today);
  const [queryDates, setQueryDates] = useState({ from: firstOfMonth, to: today });
  const [compareMode, setCompareMode] = useState<CompareOption>("none");

  const { data: report, isLoading, error, refetch } = useQuery<PLReport>({
    queryKey: ["pl", queryDates.from, queryDates.to],
    queryFn: () => reportsApi.pl(queryDates.from, queryDates.to),
  });

  const compDates = computeComparisonDates(queryDates.from, queryDates.to, compareMode);

  const { data: priorReport } = useQuery<PLReport>({
    queryKey: ["pl-compare", compDates?.from, compDates?.to],
    queryFn: () => reportsApi.pl(compDates!.from, compDates!.to),
    enabled: compDates !== null,
  });

  const comparing = compareMode !== "none" && priorReport != null;
  const colSpan = comparing ? 6 : 3;

  const exportColumns = [
    { key: "section", header: "Section" },
    { key: "code", header: "Code" },
    { key: "name", header: "Account" },
    { key: "balance", header: "Amount" },
  ];

  const exportData = useMemo(() => {
    if (!report) return [];
    return [
      ...report.revenue_lines.map((r) => ({ section: "Revenue", ...r })),
      { section: "Revenue", code: "", name: "Total Revenue", balance: report.total_revenue },
      ...report.expense_lines.map((r) => ({ section: "Expense", ...r })),
      { section: "Expense", code: "", name: "Total Expenses", balance: report.total_expenses },
      { section: "Net", code: "", name: "Net Profit", balance: report.net_profit },
    ];
  }, [report]);

  const run = () => {
    setQueryDates({ from: fromDate, to: toDate });
    void refetch();
  };

  return (
    <>
      <PageHeader
        title="Profit & Loss"
        subtitle="Income statement for a date range"
        actions={
          report ? (
            <ExportDropdown
              data={exportData}
              filename={`profit-and-loss-${queryDates.from}-to-${queryDates.to}`}
              columns={exportColumns}
            />
          ) : undefined
        }
      />
      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">

        {/* Controls */}
        <div className="flex items-end gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">From</label>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm bg-background"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">To</label>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm bg-background"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Compare to</label>
            <select
              value={compareMode}
              onChange={(e) => setCompareMode(e.target.value as CompareOption)}
              className="rounded-lg border px-3 py-2 text-sm bg-background"
            >
              <option value="none">None</option>
              <option value="prior_month">Prior Month</option>
              <option value="same_month_last_year">Same Month Last Year</option>
            </select>
          </div>
          <button
            onClick={run}
            disabled={isLoading}
            className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-60 transition-colors"
          >
            {isLoading ? "Running…" : "Run Report"}
          </button>
        </div>

        {error && <p className="text-sm text-red-600">{String(error)}</p>}

        {isLoading && (
          <div className="flex items-center justify-center py-16">
            <p className="text-sm text-muted-foreground animate-pulse">Loading report…</p>
          </div>
        )}

        {report && !isLoading && (
          <div className="space-y-6">
            {/* Chart */}
            <PLChart report={report} />

            {/* Summary banner */}
            <div
              className={`rounded-xl border p-6 ${
                report.is_profitable
                  ? "border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950/30"
                  : "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/30"
              }`}
            >
              <div className="grid grid-cols-3 gap-6 text-center">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-gray-500 dark:text-gray-400">
                    Total Revenue
                  </p>
                  <p className="mt-1 text-2xl font-bold text-green-700 dark:text-green-400">
                    {fmt(report.total_revenue)}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-gray-500 dark:text-gray-400">
                    Total Expenses
                  </p>
                  <p className="mt-1 text-2xl font-bold text-red-600 dark:text-red-400">
                    {fmt(report.total_expenses)}
                  </p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-widest text-gray-500 dark:text-gray-400">
                    Net Profit
                  </p>
                  <p
                    className={`mt-1 text-2xl font-bold ${
                      report.is_profitable
                        ? "text-green-700 dark:text-green-400"
                        : "text-red-600 dark:text-red-400"
                    }`}
                  >
                    {fmt(report.net_profit)}
                  </p>
                </div>
              </div>
            </div>

            {/* Revenue */}
            <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
              <div className="border-b bg-green-50 dark:bg-green-950/30 px-4 py-3">
                <h2 className="font-semibold text-green-800 dark:text-green-400">Revenue</h2>
              </div>
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/30">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium text-muted-foreground">Code</th>
                    <th className="px-4 py-2 text-left font-medium text-muted-foreground">Account</th>
                    <th className="px-4 py-2 text-right font-medium text-muted-foreground">Amount</th>
                    {comparing && (
                      <>
                        <th className="px-4 py-2 text-right font-medium text-muted-foreground">Prior Period</th>
                        <th className="px-4 py-2 text-right font-medium text-muted-foreground">Variance ($)</th>
                        <th className="px-4 py-2 text-right font-medium text-muted-foreground">Variance (%)</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {report.revenue_lines.length === 0 ? (
                    <tr>
                      <td colSpan={colSpan} className="px-4 py-4 text-center text-muted-foreground text-xs">
                        No revenue recorded in this period
                      </td>
                    </tr>
                  ) : (
                    report.revenue_lines.map((r) => {
                      const prior = comparing ? findPriorBalance(priorReport!.revenue_lines, r.account_id) : "0";
                      const v = comparing ? fmtVariance(r.balance, prior) : null;
                      return (
                        <tr key={r.account_id} className="hover:bg-muted/20">
                          <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">{r.code}</td>
                          <td className="px-4 py-2.5">
                            <Link
                              href={`/reports/general-ledger?account_id=${r.account_id}&from=${queryDates.from}&to=${queryDates.to}`}
                              className="text-indigo-600 hover:text-indigo-800 hover:underline dark:text-indigo-400 dark:hover:text-indigo-300"
                            >
                              {r.name}
                            </Link>
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono">{fmt(r.balance)}</td>
                          {comparing && v && (
                            <>
                              <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{fmt(prior)}</td>
                              <td className={`px-4 py-2.5 text-right font-mono ${v.isPositive ? "text-green-600" : "text-red-600"}`}>{v.dollar}</td>
                              <td className={`px-4 py-2.5 text-right font-mono ${v.isPositive ? "text-green-600" : "text-red-600"}`}>{v.pct}</td>
                            </>
                          )}
                        </tr>
                      );
                    })
                  )}
                </tbody>
                <tfoot className="border-t bg-green-50 dark:bg-green-950/30">
                  <tr>
                    <td colSpan={2} className="px-4 py-2.5 font-semibold text-green-800 dark:text-green-400">
                      Total Revenue
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold font-mono text-green-800 dark:text-green-400">
                      {fmt(report.total_revenue)}
                    </td>
                    {comparing && (() => {
                      const v = fmtVariance(report.total_revenue, priorReport!.total_revenue);
                      return (
                        <>
                          <td className="px-4 py-2.5 text-right font-bold font-mono text-muted-foreground">{fmt(priorReport!.total_revenue)}</td>
                          <td className={`px-4 py-2.5 text-right font-bold font-mono ${v.isPositive ? "text-green-600" : "text-red-600"}`}>{v.dollar}</td>
                          <td className={`px-4 py-2.5 text-right font-bold font-mono ${v.isPositive ? "text-green-600" : "text-red-600"}`}>{v.pct}</td>
                        </>
                      );
                    })()}
                  </tr>
                </tfoot>
              </table>
            </div>

            {/* Expenses */}
            <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
              <div className="border-b bg-red-50 dark:bg-red-950/30 px-4 py-3">
                <h2 className="font-semibold text-red-800 dark:text-red-400">Expenses</h2>
              </div>
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/30">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium text-muted-foreground">Code</th>
                    <th className="px-4 py-2 text-left font-medium text-muted-foreground">Account</th>
                    <th className="px-4 py-2 text-right font-medium text-muted-foreground">Amount</th>
                    {comparing && (
                      <>
                        <th className="px-4 py-2 text-right font-medium text-muted-foreground">Prior Period</th>
                        <th className="px-4 py-2 text-right font-medium text-muted-foreground">Variance ($)</th>
                        <th className="px-4 py-2 text-right font-medium text-muted-foreground">Variance (%)</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {report.expense_lines.length === 0 ? (
                    <tr>
                      <td colSpan={colSpan} className="px-4 py-4 text-center text-muted-foreground text-xs">
                        No expenses recorded in this period
                      </td>
                    </tr>
                  ) : (
                    report.expense_lines.map((r) => {
                      const prior = comparing ? findPriorBalance(priorReport!.expense_lines, r.account_id) : "0";
                      const v = comparing ? fmtVariance(r.balance, prior) : null;
                      return (
                        <tr key={r.account_id} className="hover:bg-muted/20">
                          <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">{r.code}</td>
                          <td className="px-4 py-2.5">
                            <Link
                              href={`/reports/general-ledger?account_id=${r.account_id}&from=${queryDates.from}&to=${queryDates.to}`}
                              className="text-indigo-600 hover:text-indigo-800 hover:underline dark:text-indigo-400 dark:hover:text-indigo-300"
                            >
                              {r.name}
                            </Link>
                          </td>
                          <td className="px-4 py-2.5 text-right font-mono">{fmt(r.balance)}</td>
                          {comparing && v && (
                            <>
                              <td className="px-4 py-2.5 text-right font-mono text-muted-foreground">{fmt(prior)}</td>
                              <td className={`px-4 py-2.5 text-right font-mono ${v.isPositive ? "text-green-600" : "text-red-600"}`}>{v.dollar}</td>
                              <td className={`px-4 py-2.5 text-right font-mono ${v.isPositive ? "text-green-600" : "text-red-600"}`}>{v.pct}</td>
                            </>
                          )}
                        </tr>
                      );
                    })
                  )}
                </tbody>
                <tfoot className="border-t bg-red-50 dark:bg-red-950/30">
                  <tr>
                    <td colSpan={2} className="px-4 py-2.5 font-semibold text-red-800 dark:text-red-400">
                      Total Expenses
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold font-mono text-red-800 dark:text-red-400">
                      {fmt(report.total_expenses)}
                    </td>
                    {comparing && (() => {
                      const v = fmtVariance(report.total_expenses, priorReport!.total_expenses);
                      return (
                        <>
                          <td className="px-4 py-2.5 text-right font-bold font-mono text-muted-foreground">{fmt(priorReport!.total_expenses)}</td>
                          <td className={`px-4 py-2.5 text-right font-bold font-mono ${v.isPositive ? "text-green-600" : "text-red-600"}`}>{v.dollar}</td>
                          <td className={`px-4 py-2.5 text-right font-bold font-mono ${v.isPositive ? "text-green-600" : "text-red-600"}`}>{v.pct}</td>
                        </>
                      );
                    })()}
                  </tr>
                </tfoot>
              </table>
            </div>

            {/* Net */}
            <div
              className={`rounded-xl border p-4 ${
                report.is_profitable
                  ? "border-green-300 bg-green-50 dark:border-green-800 dark:bg-green-950/30"
                  : "border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/30"
              }`}
            >
              <div className="flex items-center justify-end gap-6">
                <span className="text-sm font-medium text-muted-foreground">Net Profit / (Loss)</span>
                <span
                  className={`text-xl font-bold ${
                    report.is_profitable
                      ? "text-green-700 dark:text-green-400"
                      : "text-red-700 dark:text-red-400"
                  }`}
                >
                  {report.is_profitable ? "" : "("}
                  {fmt(report.net_profit)}
                  {report.is_profitable ? "" : ")"}
                </span>
                {comparing && (() => {
                  const v = fmtVariance(report.net_profit, priorReport!.net_profit);
                  return (
                    <>
                      <span className="text-sm font-mono text-muted-foreground">Prior: {fmt(priorReport!.net_profit)}</span>
                      <span className={`text-sm font-mono font-semibold ${v.isPositive ? "text-green-600" : "text-red-600"}`}>
                        {v.dollar} ({v.pct})
                      </span>
                    </>
                  );
                })()}
              </div>
            </div>

            <p className="text-xs text-muted-foreground text-right">
              Generated {new Date(report.generated_at).toLocaleString("en-US")} · Accrual basis
            </p>
          </div>
        )}
      </div>
    </>
  );
}
