"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { type BalanceSheetReport, type BalanceSheetLine, reportsApi } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

function fmt(amount: string) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    parseFloat(amount)
  );
}

const PIE_COLORS = ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#ddd6fe", "#ede9fe"];

function AssetPieChart({ lines }: { lines: BalanceSheetLine[] }) {
  const assetData = lines.slice(0, 6).map((a) => ({
    name: a.name.slice(0, 16),
    value: Math.abs(parseFloat(a.balance)),
  })).filter((d) => d.value > 0);

  if (assetData.length === 0) return null;

  return (
    <div className="rounded-xl border bg-card shadow-sm p-4">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
        Asset Breakdown
      </h3>
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie
            data={assetData}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={95}
            paddingAngle={2}
            dataKey="value"
          >
            {assetData.map((_, index) => (
              <Cell key={`cell-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length] ?? "#6366f1"} />
            ))}
          </Pie>
          <Tooltip formatter={(v) => fmt(String(v ?? 0))} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function Section({
  title,
  lines,
  total,
  colorClass,
}: {
  title: string;
  lines: BalanceSheetLine[];
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
  const [queryDate, setQueryDate] = useState(today);

  const { data: report, isLoading, error, refetch } = useQuery<BalanceSheetReport>({
    queryKey: ["balance-sheet", queryDate],
    queryFn: () => reportsApi.balanceSheet(queryDate),
  });

  const run = () => {
    setQueryDate(asOf);
    void refetch();
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
              className="rounded-lg border px-3 py-2 text-sm bg-background"
            />
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
            {/* Balance check banner */}
            <div
              className={`rounded-xl border p-4 flex items-center justify-between ${
                report.is_balanced
                  ? "border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950/30"
                  : "border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/30"
              }`}
            >
              <span className="text-sm font-medium">
                {report.is_balanced
                  ? "Balanced — Assets = Liabilities + Equity"
                  : "Out of balance — check your journals"}
              </span>
              <div className="flex gap-8 text-right">
                <div>
                  <p className="text-xs text-muted-foreground uppercase tracking-widest">Assets</p>
                  <p className="text-lg font-bold text-green-700 dark:text-green-400">
                    {fmt(report.assets.total)}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground uppercase tracking-widest">
                    Liabilities + Equity
                  </p>
                  <p className="text-lg font-bold text-blue-700 dark:text-blue-400">
                    {fmt(report.total_liabilities_and_equity)}
                  </p>
                </div>
              </div>
            </div>

            {/* Pie chart + assets side by side on wider screens */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <AssetPieChart lines={report.assets.lines} />
              <div className="space-y-6">
                <Section
                  title="Liabilities"
                  lines={report.liabilities.lines}
                  total={report.liabilities.total}
                  colorClass="bg-red-50 text-red-800 dark:bg-red-950/30 dark:text-red-400"
                />
                <Section
                  title="Equity"
                  lines={report.equity.lines}
                  total={report.equity.total}
                  colorClass="bg-blue-50 text-blue-800 dark:bg-blue-950/30 dark:text-blue-400"
                />
              </div>
            </div>

            <Section
              title="Assets"
              lines={report.assets.lines}
              total={report.assets.total}
              colorClass="bg-green-50 text-green-800 dark:bg-green-950/30 dark:text-green-400"
            />

            <div className="rounded-xl border border-blue-200 bg-blue-50 dark:border-blue-900 dark:bg-blue-950/30 p-4 text-right">
              <span className="text-sm font-medium text-muted-foreground mr-4">
                Total Liabilities + Equity
              </span>
              <span className="text-xl font-bold text-blue-700 dark:text-blue-400">
                {fmt(report.total_liabilities_and_equity)}
              </span>
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
