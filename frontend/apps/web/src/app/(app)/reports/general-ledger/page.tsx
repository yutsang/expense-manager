"use client";

import { useEffect, useState } from "react";
import { accountsApi, reportsApi, type Account, type GLReport } from "@/lib/api";
import { PageHeader } from "@/components/page-header";

function fmt(s: string) {
  const n = parseFloat(s);
  if (isNaN(n)) return s;
  return n.toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtSigned(s: string) {
  const n = parseFloat(s);
  if (isNaN(n)) return s;
  const display = Math.abs(n).toLocaleString("en-AU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n < 0) return `(${display})`;
  return display;
}

export default function GeneralLedgerPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState("");
  const today = new Date().toISOString().slice(0, 10);
  const firstOfMonth = today.slice(0, 8) + "01";
  const [fromDate, setFromDate] = useState(firstOfMonth);
  const [toDate, setToDate] = useState(today);
  const [report, setReport] = useState<GLReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    accountsApi.list().then((r) => {
      setAccounts(r.items);
      if (r.items.length > 0) setAccountId(r.items[0]!.id);
    });
  }, []);

  async function run() {
    if (!accountId) { alert("Select an account"); return; }
    setLoading(true);
    setError(null);
    try {
      const r = await reportsApi.generalLedger(accountId, fromDate, toDate);
      setReport(r);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load report");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PageHeader
        title="General Ledger"
        subtitle="Detailed transaction history for a single account with running balance"
      />
    <div className="mx-auto max-w-7xl px-6 py-6">

      {/* Controls */}
      <div className="mb-6 flex flex-wrap items-end gap-3">
        <div>
          <label className="mb-1 block text-xs font-medium">Account</label>
          <select
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            className="rounded border px-3 py-1.5 text-sm"
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.code} — {a.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium">From</label>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="rounded border px-3 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium">To</label>
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
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
          <div className="mb-4 flex items-baseline gap-4">
            <h2 className="text-lg font-semibold">
              {report.account_code} — {report.account_name}
            </h2>
            <span className="text-sm text-muted-foreground">
              {report.from_date} → {report.to_date}
            </span>
          </div>

          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b bg-muted/40 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Journal</th>
                  <th className="px-4 py-3">Description</th>
                  <th className="px-4 py-3 text-right">Debit</th>
                  <th className="px-4 py-3 text-right">Credit</th>
                  <th className="px-4 py-3 text-right">Balance</th>
                </tr>
              </thead>
              <tbody>
                {/* Opening balance row */}
                <tr className="bg-muted/20 text-sm italic text-muted-foreground">
                  <td className="px-4 py-2">{report.from_date}</td>
                  <td className="px-4 py-2" />
                  <td className="px-4 py-2">Opening balance</td>
                  <td className="px-4 py-2" />
                  <td className="px-4 py-2" />
                  <td className="px-4 py-2 text-right font-mono">
                    {fmtSigned(report.opening_balance)}
                  </td>
                </tr>

                {report.lines.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-center text-sm text-muted-foreground">
                      No transactions in this period.
                    </td>
                  </tr>
                ) : (
                  report.lines.map((ln, i) => (
                    <tr key={i} className="border-t hover:bg-muted/30">
                      <td className="px-4 py-2 text-sm">{ln.date}</td>
                      <td className="px-4 py-2 font-mono text-sm text-muted-foreground">
                        {ln.journal_number}
                      </td>
                      <td className="px-4 py-2 text-sm max-w-xs truncate">{ln.description}</td>
                      <td className="px-4 py-2 text-right font-mono text-sm">
                        {parseFloat(ln.debit) > 0 ? fmt(ln.debit) : ""}
                      </td>
                      <td className="px-4 py-2 text-right font-mono text-sm">
                        {parseFloat(ln.credit) > 0 ? fmt(ln.credit) : ""}
                      </td>
                      <td className={`px-4 py-2 text-right font-mono text-sm font-medium ${
                        parseFloat(ln.running_balance) < 0 ? "text-red-600" : ""
                      }`}>
                        {fmtSigned(ln.running_balance)}
                      </td>
                    </tr>
                  ))
                )}

                {/* Closing balance row */}
                <tr className="border-t-2 bg-muted/20 font-semibold text-sm">
                  <td colSpan={5} className="px-4 py-2">Closing balance</td>
                  <td className={`px-4 py-2 text-right font-mono ${
                    parseFloat(report.closing_balance) < 0 ? "text-red-600" : ""
                  }`}>
                    {fmtSigned(report.closing_balance)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}

      {!report && !loading && (
        <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
          Select an account and date range, then click Run Report.
        </div>
      )}
    </div>
    </>
  );
}
