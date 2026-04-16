"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { getCashFlow, type CashFlowReport } from "@/lib/api";
import { PageHeader } from "@/components/page-header";

function fmtAmount(amount: string) {
  const n = parseFloat(amount);
  const abs = Math.abs(n);
  const str = new Intl.NumberFormat("en-AU", { style: "currency", currency: "AUD" }).format(abs);
  return n < 0 ? `(${str})` : str;
}

function amountColor(amount: string) {
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
                  line.is_subtotal ? amountColor(line.amount) : ""
                }`}
              >
                {fmtAmount(line.amount)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function exportCsv(report: CashFlowReport) {
  const rows: string[][] = [["Section", "Label", "Amount"]];

  for (const line of report.operating_activities) {
    rows.push(["Operating Activities", line.label, line.amount]);
  }
  for (const line of report.investing_activities) {
    rows.push(["Investing Activities", line.label, line.amount]);
  }
  for (const line of report.financing_activities) {
    rows.push(["Financing Activities", line.label, line.amount]);
  }
  rows.push(["Summary", "Net Change in Cash", report.net_change]);
  rows.push(["Summary", "Beginning Cash", report.opening_cash]);
  rows.push(["Summary", "Ending Cash", report.closing_cash]);

  const csv = rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `cash-flow-${report.from_date}-to-${report.to_date}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function CashFlowPage() {
  const today = new Date().toISOString().slice(0, 10);
  const firstOfMonth = today.slice(0, 7) + "-01";

  const [fromDate, setFromDate] = useState(firstOfMonth);
  const [toDate, setToDate] = useState(today);

  const { data: report, isLoading, error } = useQuery({
    queryKey: ["cash-flow", fromDate, toDate],
    queryFn: () => getCashFlow(fromDate, toDate),
  });

  const exportButton = report ? (
    <button
      onClick={() => exportCsv(report)}
      className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
    >
      <Download className="h-4 w-4" />
      Export CSV
    </button>
  ) : undefined;

  return (
    <>
      <PageHeader
        title="Cash Flow Statement"
        subtitle="Indirect method — operating, investing, financing"
        actions={exportButton}
      />
      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">
        {/* Date range picker — refetches automatically when dates change */}
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
          {isLoading && (
            <p className="text-sm text-muted-foreground pb-2">Loading…</p>
          )}
        </div>

        {error && (
          <p className="text-sm text-red-600">{String(error)}</p>
        )}

        {report && (
          <div className="space-y-6">
            {/* Summary banner */}
            <div className="grid grid-cols-4 gap-4">
              {[
                { label: "Opening Cash", value: report.opening_cash, color: "text-gray-700" },
                { label: "Net Change", value: report.net_change, color: amountColor(report.net_change) },
                { label: "Closing Cash", value: report.closing_cash, color: amountColor(report.closing_cash) },
                {
                  label: "Operating / Investing / Financing",
                  value: `${fmtAmount(report.net_operating)} / ${fmtAmount(report.net_investing)} / ${fmtAmount(report.net_financing)}`,
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

            {/* Net change footer */}
            <div className="rounded-xl border bg-muted/20 p-4">
              <table className="w-full text-sm">
                <tbody>
                  <tr>
                    <td className="py-1 text-muted-foreground">Net Change in Cash</td>
                    <td className={`py-1 text-right font-mono ${amountColor(report.net_change)}`}>
                      {fmtAmount(report.net_change)}
                    </td>
                  </tr>
                  <tr>
                    <td className="py-1 text-muted-foreground">Beginning Cash</td>
                    <td className="py-1 text-right font-mono">{fmtAmount(report.opening_cash)}</td>
                  </tr>
                  <tr className="border-t font-semibold">
                    <td className="py-2">Ending Cash</td>
                    <td className={`py-2 text-right font-mono text-lg ${amountColor(report.closing_cash)}`}>
                      {fmtAmount(report.closing_cash)}
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

        {!report && !isLoading && !error && (
          <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
            Adjust the date range to generate the report.
          </div>
        )}
      </div>
    </>
  );
}
