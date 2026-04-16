"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { type AgingReport, reportsApi } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

function fmt(amount: string) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    parseFloat(amount)
  );
}

const BUCKET_LABELS: Record<string, string> = {
  current: "Current",
  "1-30": "1–30 days",
  "31-60": "31–60 days",
  "61-90": "61–90 days",
  "90+": "90+ days",
};

const BUCKET_COLORS: Record<string, string> = {
  current: "text-green-700",
  "1-30": "text-yellow-700",
  "31-60": "text-orange-600",
  "61-90": "text-red-600",
  "90+": "text-red-800 font-bold",
};

function AgingChart({ report }: { report: AgingReport }) {
  const chartData = [
    { name: "Current", amount: parseFloat(report.current_total) },
    { name: "1–30", amount: parseFloat(report.bucket_1_30) },
    { name: "31–60", amount: parseFloat(report.bucket_31_60) },
    { name: "61–90", amount: parseFloat(report.bucket_61_90) },
    { name: "90+", amount: parseFloat(report.bucket_90_plus) },
  ];

  return (
    <div className="rounded-xl border bg-card shadow-sm p-4">
      <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4">
        Payables by Aging Bucket
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart
          data={chartData}
          layout="vertical"
          margin={{ top: 0, right: 24, left: 16, bottom: 0 }}
        >
          <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={55} />
          <Tooltip formatter={(v) => fmt(String(v ?? 0))} />
          <Bar dataKey="amount" fill="#f43f5e" radius={[0, 3, 3, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function APAgingPage() {
  const today = new Date().toISOString().slice(0, 10);
  const [asOf, setAsOf] = useState(today);
  const [queryDate, setQueryDate] = useState(today);

  const { data: report, isLoading, error, refetch } = useQuery<AgingReport>({
    queryKey: ["ap-aging", queryDate],
    queryFn: () => reportsApi.apAging(queryDate),
  });

  const run = () => {
    setQueryDate(asOf);
    void refetch();
  };

  return (
    <>
      <PageHeader title="AP Aging" subtitle="Outstanding payables by age as of a date" />
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
            {/* Chart */}
            <AgingChart report={report} />

            {/* Bucket summary */}
            <div className="grid grid-cols-5 gap-3">
              {(["current", "1-30", "31-60", "61-90", "90+"] as const).map((b) => {
                const key =
                  b === "1-30"
                    ? "bucket_1_30"
                    : b === "31-60"
                    ? "bucket_31_60"
                    : b === "61-90"
                    ? "bucket_61_90"
                    : b === "90+"
                    ? "bucket_90_plus"
                    : "current_total";
                return (
                  <div key={b} className="rounded-xl border bg-card p-4 text-center shadow-sm">
                    <p className="text-xs text-muted-foreground uppercase tracking-widest mb-1">
                      {BUCKET_LABELS[b]}
                    </p>
                    <p className={`text-lg font-bold ${BUCKET_COLORS[b]}`}>
                      {fmt(report[key as keyof AgingReport] as string)}
                    </p>
                  </div>
                );
              })}
            </div>

            <div className="rounded-xl border bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800 p-3 text-right">
              <span className="text-sm text-muted-foreground mr-3">Total Outstanding</span>
              <span className="text-xl font-bold text-red-800 dark:text-red-400">
                {fmt(report.grand_total)}
              </span>
            </div>

            {/* Detail table */}
            <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
              <div className="border-b bg-muted/20 px-4 py-3">
                <h2 className="font-semibold">Detail</h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b bg-muted/30">
                    <tr>
                      <th className="px-4 py-2 text-left font-medium text-muted-foreground">Supplier</th>
                      <th className="px-4 py-2 text-left font-medium text-muted-foreground">Bill #</th>
                      <th className="px-4 py-2 text-left font-medium text-muted-foreground">Issue Date</th>
                      <th className="px-4 py-2 text-left font-medium text-muted-foreground">Due Date</th>
                      <th className="px-4 py-2 text-right font-medium text-muted-foreground">Total</th>
                      <th className="px-4 py-2 text-right font-medium text-muted-foreground">Amount Due</th>
                      <th className="px-4 py-2 text-center font-medium text-muted-foreground">Age</th>
                      <th className="px-4 py-2 text-center font-medium text-muted-foreground">Bucket</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {report.rows.length === 0 ? (
                      <tr>
                        <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground text-xs">
                          No outstanding payables as of this date
                        </td>
                      </tr>
                    ) : (
                      report.rows.map((r) => (
                        <tr key={r.invoice_number} className="hover:bg-muted/20">
                          <td className="px-4 py-2.5">{r.contact_name}</td>
                          <td className="px-4 py-2.5 font-mono text-xs">{r.invoice_number}</td>
                          <td className="px-4 py-2.5 text-muted-foreground">{r.issue_date}</td>
                          <td className="px-4 py-2.5 text-muted-foreground">{r.due_date ?? "—"}</td>
                          <td className="px-4 py-2.5 text-right font-mono">{fmt(r.total)}</td>
                          <td className="px-4 py-2.5 text-right font-mono font-semibold">{fmt(r.amount_due)}</td>
                          <td className="px-4 py-2.5 text-center text-xs text-muted-foreground">
                            {r.days_overdue > 0 ? `${r.days_overdue}d` : "—"}
                          </td>
                          <td className="px-4 py-2.5 text-center">
                            <span className={`text-xs font-semibold ${BUCKET_COLORS[r.bucket]}`}>
                              {BUCKET_LABELS[r.bucket]}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <p className="text-xs text-muted-foreground text-right">
              Generated {new Date(report.generated_at).toLocaleString("en-US")}
            </p>
          </div>
        )}
      </div>
    </>
  );
}
