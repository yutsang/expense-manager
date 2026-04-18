"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { getCashFlow, type CashFlowReport } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { ExportDropdown } from "@/components/export-dropdown";

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

export default function CashFlowPage() {
  const today = new Date().toISOString().slice(0, 10);
  const firstOfMonth = today.slice(0, 7) + "-01";

  const [fromDate, setFromDate] = useState(firstOfMonth);
  const [toDate, setToDate] = useState(today);

  const { data: report, isLoading, error } = useQuery({
    queryKey: ["cash-flow", fromDate, toDate],
    queryFn: () => getCashFlow(fromDate, toDate),
  });

  const exportColumns = [
    { key: "section", header: "Section" },
    { key: "label", header: "Label" },
    { key: "amount", header: "Amount" },
  ];

  const exportData = useMemo(() => {
    if (!report) return [];
    return [
      ...report.operating_activities.map((l) => ({ section: "Operating Activities", ...l })),
      ...report.investing_activities.map((l) => ({ section: "Investing Activities", ...l })),
      ...report.financing_activities.map((l) => ({ section: "Financing Activities", ...l })),
      { section: "Summary", label: "Net Change in Cash", amount: report.net_change },
      { section: "Summary", label: "Beginning Cash", amount: report.opening_cash },
      { section: "Summary", label: "Ending Cash", amount: report.closing_cash },
    ];
  }, [report]);

  return (
    <>
      <PageHeader
        title="Cash Flow Statement"
        subtitle="Indirect method — operating, investing, financing"
        actions={
          report ? (
            <ExportDropdown
              data={exportData}
              filename={`cash-flow-${fromDate}-to-${toDate}`}
              columns={exportColumns}
            />
          ) : undefined
        }
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
