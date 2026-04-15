"use client";

import { useState } from "react";
import { type AgingReport, reportsApi } from "@/lib/api";
import { PageHeader } from "@/components/page-header";

function fmt(amount: string) {
  return new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD" }).format(
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

export default function ARAgingPage() {
  const today = new Date().toISOString().slice(0, 10);
  const [asOf, setAsOf] = useState(today);
  const [report, setReport] = useState<AgingReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    try {
      setLoading(true);
      setError(null);
      setReport(await reportsApi.arAging(asOf));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <PageHeader title="AR Aging" subtitle="Outstanding receivables by age as of a date" />
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
          {/* Bucket summary */}
          <div className="grid grid-cols-5 gap-3">
            {(["current", "1-30", "31-60", "61-90", "90+"] as const).map((b) => {
              const key = b === "1-30" ? "bucket_1_30"
                : b === "31-60" ? "bucket_31_60"
                : b === "61-90" ? "bucket_61_90"
                : b === "90+" ? "bucket_90_plus"
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

          <div className="rounded-xl border bg-green-50 border-green-200 p-3 text-right">
            <span className="text-sm text-muted-foreground mr-3">Total Outstanding</span>
            <span className="text-xl font-bold text-green-800">{fmt(report.grand_total)}</span>
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
                    <th className="px-4 py-2 text-left font-medium text-muted-foreground">Contact</th>
                    <th className="px-4 py-2 text-left font-medium text-muted-foreground">Invoice #</th>
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
                        No outstanding receivables as of this date
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
            Generated {new Date(report.generated_at).toLocaleString("en-AU")}
          </p>
        </div>
      )}
    </div>
    </>
  );
}
