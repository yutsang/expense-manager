"use client";

import { useState } from "react";
import { type CashFlowReport, reportsApi } from "@/lib/api";

function fmt(amount: string) {
  const n = parseFloat(amount);
  const abs = Math.abs(n);
  const str = new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD" }).format(abs);
  return n < 0 ? `(${str})` : str;
}

function fmtColor(amount: string) {
  return parseFloat(amount) >= 0 ? "text-green-700" : "text-red-700";
}

function ActivitySection({
  title,
  lines,
}: {
  title: string;
  lines: { label: string; amount: string; is_subtotal: boolean }[];
}) {
  return (
    <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
      <div className="border-b bg-muted/20 px-4 py-3">
        <h2 className="font-semibold">{title}</h2>
      </div>
      <table className="w-full text-sm">
        <tbody className="divide-y">
          {lines.map((line, i) => (
            <tr
              key={i}
              className={line.is_subtotal ? "bg-muted/30 font-semibold" : "hover:bg-muted/10"}
            >
              <td
                className={`px-4 py-2.5 ${line.is_subtotal ? "pl-4" : "pl-8 text-muted-foreground"}`}
              >
                {line.label}
              </td>
              <td
                className={`px-4 py-2.5 text-right font-mono ${
                  line.is_subtotal ? fmtColor(line.amount) : ""
                }`}
              >
                {fmt(line.amount)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function CashFlowPage() {
  const today = new Date().toISOString().slice(0, 10);
  const firstOfMonth = today.slice(0, 7) + "-01";
  const [fromDate, setFromDate] = useState(firstOfMonth);
  const [toDate, setToDate] = useState(today);
  const [report, setReport] = useState<CashFlowReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    try {
      setLoading(true);
      setError(null);
      setReport(await reportsApi.cashFlow(fromDate, toDate));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Cash Flow Statement</h1>
        <p className="text-sm text-muted-foreground">Indirect method — operating, investing, financing</p>
      </div>

      <div className="flex items-end gap-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">From</label>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="rounded-lg border px-3 py-2 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">To</label>
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
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
          {/* Summary banner */}
          <div className="grid grid-cols-4 gap-4">
            {[
              { label: "Opening Cash", value: report.opening_cash, color: "text-gray-700" },
              { label: "Net Change", value: report.net_change, color: fmtColor(report.net_change) },
              { label: "Closing Cash", value: report.closing_cash, color: fmtColor(report.closing_cash) },
              {
                label: "Operating / Investing / Financing",
                value: `${fmt(report.net_operating)} / ${fmt(report.net_investing)} / ${fmt(report.net_financing)}`,
                color: "text-muted-foreground",
                small: true,
              },
            ].map((card) => (
              <div key={card.label} className="rounded-xl border bg-card p-4 shadow-sm text-center">
                <p className="text-xs text-muted-foreground uppercase tracking-widest mb-1">
                  {card.label}
                </p>
                <p className={`font-bold ${card.small ? "text-sm mt-2" : "text-xl"} ${card.color}`}>
                  {card.value}
                </p>
              </div>
            ))}
          </div>

          <ActivitySection title="Operating Activities" lines={report.operating_activities} />
          <ActivitySection title="Investing Activities" lines={report.investing_activities} />
          <ActivitySection title="Financing Activities" lines={report.financing_activities} />

          {/* Net change reconciliation */}
          <div className="rounded-xl border bg-muted/20 p-4">
            <table className="w-full text-sm">
              <tbody>
                <tr>
                  <td className="py-1 text-muted-foreground">Opening cash balance</td>
                  <td className="py-1 text-right font-mono">{fmt(report.opening_cash)}</td>
                </tr>
                <tr>
                  <td className="py-1 text-muted-foreground">Net change in cash</td>
                  <td className={`py-1 text-right font-mono ${fmtColor(report.net_change)}`}>
                    {fmt(report.net_change)}
                  </td>
                </tr>
                <tr className="border-t font-semibold">
                  <td className="py-2">Closing cash balance</td>
                  <td className={`py-2 text-right font-mono text-lg ${fmtColor(report.closing_cash)}`}>
                    {fmt(report.closing_cash)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <p className="text-xs text-muted-foreground text-right">
            Generated {new Date(report.generated_at).toLocaleString("en-AU")} · Indirect method
          </p>
        </div>
      )}
    </div>
  );
}
