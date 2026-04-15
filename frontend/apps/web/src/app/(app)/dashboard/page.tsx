"use client";

import { useEffect, useState } from "react";
import { reportsApi, journalsApi, DashboardData, JournalEntry } from "@/lib/api";

const aud = new Intl.NumberFormat("en-AU", {
  style: "currency",
  currency: "AUD",
  minimumFractionDigits: 2,
});

function formatMoney(val: string): string {
  return aud.format(parseFloat(val));
}

function formatDate(val: string): string {
  return new Date(val).toLocaleDateString("en-AU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function SkeletonBox({ className = "" }: { className?: string }) {
  return (
    <div className={`animate-pulse bg-gray-200 rounded ${className}`} />
  );
}

interface KpiCardProps {
  label: string;
  value: string;
  colorClass?: string;
}

function KpiCard({ label, value, colorClass = "text-gray-900" }: KpiCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <p className="text-sm text-gray-500 font-medium">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${colorClass}`}>{value}</p>
    </div>
  );
}

function KpiCardSkeleton() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
      <SkeletonBox className="h-4 w-32 mb-3" />
      <SkeletonBox className="h-7 w-40" />
    </div>
  );
}

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [journals, setJournals] = useState<JournalEntry[] | null>(null);
  const [dashError, setDashError] = useState<string | null>(null);
  const [journalsError, setJournalsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [journalsLoading, setJournalsLoading] = useState(true);

  useEffect(() => {
    reportsApi
      .dashboard()
      .then(setDashboard)
      .catch((err: Error) => setDashError(err.message))
      .finally(() => setLoading(false));

    journalsApi
      .list({ limit: 5 })
      .then((res) => setJournals(res.items))
      .catch((err: Error) => setJournalsError(err.message))
      .finally(() => setJournalsLoading(false));
  }, []);

  const netProfit =
    dashboard
      ? parseFloat(dashboard.revenue_mtd) - parseFloat(dashboard.expenses_mtd)
      : 0;

  return (
    <main className="p-6 max-w-7xl mx-auto space-y-8">
      <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>

      {/* KPI Cards */}
      {dashError ? (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">
          Failed to load dashboard data: {dashError}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {loading ? (
            <>
              <KpiCardSkeleton />
              <KpiCardSkeleton />
              <KpiCardSkeleton />
              <KpiCardSkeleton />
              <KpiCardSkeleton />
              <KpiCardSkeleton />
            </>
          ) : dashboard ? (
            <>
              <KpiCard
                label="Cash Balance"
                value={formatMoney(dashboard.cash_balance)}
                colorClass={parseFloat(dashboard.cash_balance) >= 0 ? "text-green-700" : "text-red-700"}
              />
              <KpiCard
                label="Accounts Receivable"
                value={formatMoney(dashboard.accounts_receivable)}
              />
              <KpiCard
                label="Accounts Payable"
                value={formatMoney(dashboard.accounts_payable)}
              />
              <KpiCard
                label="Revenue MTD"
                value={formatMoney(dashboard.revenue_mtd)}
              />
              <KpiCard
                label="Expenses MTD"
                value={formatMoney(dashboard.expenses_mtd)}
              />
              <KpiCard
                label="Net Profit MTD"
                value={formatMoney(String(netProfit))}
                colorClass={netProfit >= 0 ? "text-green-700" : "text-red-700"}
              />
            </>
          ) : null}
        </div>
      )}

      {/* Needs Attention */}
      {!dashError && (
        <section>
          <h2 className="text-lg font-semibold text-gray-800 mb-3">Needs attention</h2>
          <div className="flex flex-wrap gap-3">
            {loading ? (
              <>
                <SkeletonBox className="h-10 w-52 rounded-lg" />
                <SkeletonBox className="h-10 w-56 rounded-lg" />
              </>
            ) : dashboard ? (
              <>
                <div className="flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-4 py-2.5 shadow-sm">
                  <span className="text-sm text-gray-700">Invoices overdue</span>
                  <span
                    className={`inline-flex items-center justify-center min-w-[1.5rem] px-2 py-0.5 text-xs font-bold rounded-full ${
                      dashboard.invoices_overdue > 0
                        ? "bg-red-100 text-red-700"
                        : "bg-gray-100 text-gray-500"
                    }`}
                  >
                    {dashboard.invoices_overdue}
                  </span>
                </div>
                <div className="flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-4 py-2.5 shadow-sm">
                  <span className="text-sm text-gray-700">Bills awaiting approval</span>
                  <span
                    className={`inline-flex items-center justify-center min-w-[1.5rem] px-2 py-0.5 text-xs font-bold rounded-full ${
                      dashboard.bills_awaiting_approval > 0
                        ? "bg-yellow-100 text-yellow-700"
                        : "bg-gray-100 text-gray-500"
                    }`}
                  >
                    {dashboard.bills_awaiting_approval}
                  </span>
                </div>
              </>
            ) : null}
          </div>
        </section>
      )}

      {/* Recent Journal Entries */}
      <section>
        <h2 className="text-lg font-semibold text-gray-800 mb-3">Recent journal entries</h2>
        {journalsError ? (
          <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">
            Failed to load journals: {journalsError}
          </div>
        ) : journalsLoading ? (
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="p-4 space-y-3">
              {[...Array(5)].map((_, i) => (
                <SkeletonBox key={i} className="h-5 w-full" />
              ))}
            </div>
          </div>
        ) : journals && journals.length > 0 ? (
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">Number</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">Date</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">Description</th>
                  <th className="text-right px-4 py-3 text-gray-500 font-medium">Total Debit</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {journals.map((je) => (
                  <tr key={je.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 font-mono text-gray-700">{je.number}</td>
                    <td className="px-4 py-3 text-gray-600">{formatDate(je.date)}</td>
                    <td className="px-4 py-3 text-gray-700 max-w-xs truncate">{je.description}</td>
                    <td className="px-4 py-3 text-right text-gray-700">{formatMoney(je.total_debit)}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                          je.status === "posted"
                            ? "bg-green-100 text-green-700"
                            : je.status === "draft"
                            ? "bg-gray-100 text-gray-600"
                            : je.status === "void"
                            ? "bg-red-100 text-red-700"
                            : "bg-blue-100 text-blue-700"
                        }`}
                      >
                        {je.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-8 text-center text-gray-400 text-sm">
            No journal entries yet.
          </div>
        )}
      </section>
    </main>
  );
}
