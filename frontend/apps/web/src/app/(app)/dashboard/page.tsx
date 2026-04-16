"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Clock,
  Plus,
  FileText,
  Receipt,
  ArrowRight,
  BookMarked,
  ShieldAlert,
  CheckCircle2,
  ShieldCheck,
  Database,
} from "lucide-react";
import { reportsApi, journalsApi, getAnomalies, kycApi, accountsApi, type DashboardData, type JournalEntry, type Anomaly, type KycDashboardAlerts } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";

function fmt(val: string, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(parseFloat(val));
}

function fmtDate(val: string): string {
  return new Date(val).toLocaleDateString("en-US", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-muted ${className}`} />;
}

// ── KPI Card ──────────────────────────────────────────────────────────────────

interface KpiProps {
  label: string;
  value: string;
  trend?: "up" | "down" | "neutral";
  trendLabel?: string;
  href?: string;
  accent?: boolean;
}

function KpiCard({ label, value, trend, trendLabel, href, accent }: KpiProps) {
  const trendColor =
    trend === "up" ? "text-green-600" : trend === "down" ? "text-destructive" : "text-muted-foreground";
  const TrendIcon = trend === "up" ? TrendingUp : trend === "down" ? TrendingDown : null;

  const content = (
    <div
      className={`group rounded-xl border bg-card p-5 shadow-sm hover:shadow-md transition-shadow ${
        accent ? "border-l-4 border-l-primary" : ""
      }`}
    >
      <p className="text-sm font-medium text-muted-foreground">{label}</p>
      <p className={`mt-2 text-2xl font-semibold tabular-nums tracking-tight ${trendColor}`}>{value}</p>
      {trendLabel && TrendIcon && (
        <div className={`mt-2 flex items-center gap-1 text-xs font-medium ${trendColor}`}>
          <TrendIcon className="h-3 w-3" />
          {trendLabel}
        </div>
      )}
    </div>
  );

  return href ? <Link href={href}>{content}</Link> : content;
}

function KpiCardSkeleton() {
  return (
    <div className="rounded-xl border bg-card p-5 shadow-sm">
      <Skeleton className="h-4 w-32 mb-3" />
      <Skeleton className="h-7 w-36" />
    </div>
  );
}

// ── Attention Badge ────────────────────────────────────────────────────────────

function AttentionCard({
  label,
  count,
  href,
  urgency,
}: {
  label: string;
  count: number;
  href: string;
  urgency: "high" | "medium" | "low";
}) {
  const colors = {
    high: "border-l-4 border-l-destructive border-destructive/20 bg-destructive/5 text-destructive",
    medium: "border-l-4 border-l-yellow-500 border-yellow-200 bg-yellow-50 text-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-400",
    low: "border-l-4 border-l-border border-border bg-muted/40 text-muted-foreground",
  };
  const badgeColors = {
    high: "bg-destructive text-destructive-foreground",
    medium: "bg-yellow-500 text-white",
    low: "bg-muted-foreground/20 text-muted-foreground",
  };

  return (
    <Link
      href={href}
      className={`flex items-center gap-3 rounded-lg border px-4 py-3 text-sm font-medium transition-opacity hover:opacity-80 ${colors[urgency]}`}
    >
      {urgency === "high" ? (
        <AlertTriangle className="h-4 w-4 shrink-0" />
      ) : (
        <Clock className="h-4 w-4 shrink-0" />
      )}
      <span className="flex-1">{label}</span>
      <span className={`inline-flex min-w-[1.5rem] items-center justify-center rounded-full px-1.5 py-0.5 text-xs font-bold ${badgeColors[urgency]}`}>
        {count}
      </span>
      <ArrowRight className="h-3.5 w-3.5 shrink-0 opacity-60" />
    </Link>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

// ── Anomaly badge ─────────────────────────────────────────────────────────────

function AnomalySeverityBadge({ severity }: { severity: Anomaly["severity"] }) {
  const cls =
    severity === "high"
      ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
      : severity === "medium"
      ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
      : "bg-muted text-muted-foreground";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {severity.charAt(0).toUpperCase() + severity.slice(1)}
    </span>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [journals, setJournals] = useState<JournalEntry[] | null>(null);
  const [dashError, setDashError] = useState<string | null>(null);
  const [journalsError, setJournalsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [journalsLoading, setJournalsLoading] = useState(true);
  const [kycAlerts, setKycAlerts] = useState<KycDashboardAlerts | null>(null);
  const [seedLoading, setSeedLoading] = useState(false);

  const { data: anomalies, isLoading: anomaliesLoading, error: anomaliesError } = useQuery({
    queryKey: ["anomalies"],
    queryFn: getAnomalies,
  });

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

    kycApi.dashboardAlerts().then(setKycAlerts).catch(() => null);
  }, []);

  async function handleSeedDemo() {
    setSeedLoading(true);
    try {
      await accountsApi.seedDemo();
      window.location.reload();
    } catch {
      setSeedLoading(false);
    }
  }

  const netProfit =
    dashboard
      ? parseFloat(dashboard.revenue_mtd) - parseFloat(dashboard.expenses_mtd)
      : 0;

  type AttentionItem = { label: string; count: number; href: string; urgency: "high" | "medium" | "low" };
  const needsAttention: AttentionItem[] = [];
  if (!dashError && dashboard) {
    if (dashboard.invoices_overdue > 0) {
      needsAttention.push({
        label: `${dashboard.invoices_overdue} overdue invoice${dashboard.invoices_overdue > 1 ? "s" : ""}`,
        count: dashboard.invoices_overdue,
        href: "/invoices",
        urgency: "high",
      });
    }
    if (dashboard.bills_awaiting_approval > 0) {
      needsAttention.push({
        label: `${dashboard.bills_awaiting_approval} bill${dashboard.bills_awaiting_approval > 1 ? "s" : ""} awaiting approval`,
        count: dashboard.bills_awaiting_approval,
        href: "/bills",
        urgency: "medium",
      });
    }
  }

  const quickActions = (
    <>
      <button
        onClick={() => { void handleSeedDemo(); }}
        disabled={seedLoading}
        className="flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-60"
      >
        {seedLoading ? (
          <span className="h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin" />
        ) : (
          <Database className="h-4 w-4" />
        )}
        Load Demo Data
      </button>
      <Link
        href="/invoices"
        className="flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
      >
        <FileText className="h-4 w-4" />
        New Invoice
      </Link>
      <Link
        href="/bills"
        className="flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
      >
        <Receipt className="h-4 w-4" />
        New Bill
      </Link>
      <Link
        href="/journals"
        className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        <Plus className="h-4 w-4" />
        Journal
      </Link>
    </>
  );

  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle={new Date().toLocaleDateString("en-US", { month: "long", year: "numeric" })}
        actions={quickActions}
      />

      <div className="mx-auto max-w-7xl px-6 py-6 space-y-8">
        {/* KPI grid */}
        {dashError ? (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            Failed to load dashboard data: {dashError}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {loading ? (
              Array.from({ length: 6 }).map((_, i) => <KpiCardSkeleton key={i} />)
            ) : dashboard ? (
              <>
                <KpiCard
                  label="Cash Balance"
                  value={fmt(dashboard.cash_balance)}
                  trend={parseFloat(dashboard.cash_balance) >= 0 ? "up" : "down"}
                  href="/accounts"
                  accent={parseFloat(dashboard.cash_balance) >= 0}
                />
                <KpiCard
                  label="Accounts Receivable"
                  value={fmt(dashboard.accounts_receivable)}
                  trend="neutral"
                  href="/invoices"
                />
                <KpiCard
                  label="Accounts Payable"
                  value={fmt(dashboard.accounts_payable)}
                  trend="neutral"
                  href="/bills"
                />
                <KpiCard
                  label="Revenue MTD"
                  value={fmt(dashboard.revenue_mtd)}
                  trend="up"
                  href="/reports/pl"
                  accent
                />
                <KpiCard
                  label="Expenses MTD"
                  value={fmt(dashboard.expenses_mtd)}
                  trend="neutral"
                  href="/reports/pl"
                />
                <KpiCard
                  label="Net Profit MTD"
                  value={fmt(String(netProfit))}
                  trend={netProfit >= 0 ? "up" : "down"}
                  trendLabel={netProfit >= 0 ? "Profitable" : "Operating at a loss"}
                  href="/reports/pl"
                  accent={netProfit >= 0}
                />
              </>
            ) : null}
          </div>
        )}

        <hr className="border-border" />

        {/* Needs attention */}
        {!loading && needsAttention.length > 0 && (
          <section>
            <h2 className="mb-3 text-base font-semibold">Needs attention</h2>
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
              {needsAttention.map((item) => (
                <AttentionCard key={item.href} {...item} />
              ))}
            </div>
          </section>
        )}

        {/* KYC Compliance Alerts */}
        {kycAlerts !== null && (
          <section>
            <div className="mb-3 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-base font-semibold">Compliance Alerts</h2>
            </div>
            {kycAlerts.id_expired === 0 &&
            kycAlerts.id_expiring_soon === 0 &&
            kycAlerts.poa_stale === 0 &&
            kycAlerts.pending_kyc === 0 &&
            kycAlerts.flagged === 0 ? (
              <div className="flex items-center gap-2 rounded-xl border bg-green-50 px-4 py-3 text-sm font-medium text-green-700 dark:bg-green-900/20 dark:text-green-400">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                All KYC records current
              </div>
            ) : (
              <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
                {kycAlerts.id_expired > 0 && (
                  <AttentionCard
                    label={`${kycAlerts.id_expired} contact${kycAlerts.id_expired > 1 ? "s" : ""} with expired ID`}
                    count={kycAlerts.id_expired}
                    href="/contacts/kyc"
                    urgency="high"
                  />
                )}
                {kycAlerts.id_expiring_soon > 0 && (
                  <AttentionCard
                    label={`${kycAlerts.id_expiring_soon} contact${kycAlerts.id_expiring_soon > 1 ? "s" : ""} ID expiring within 60 days`}
                    count={kycAlerts.id_expiring_soon}
                    href="/contacts/kyc"
                    urgency="medium"
                  />
                )}
                {kycAlerts.poa_stale > 0 && (
                  <AttentionCard
                    label={`${kycAlerts.poa_stale} contact${kycAlerts.poa_stale > 1 ? "s" : ""} with stale proof of address`}
                    count={kycAlerts.poa_stale}
                    href="/contacts/kyc"
                    urgency="medium"
                  />
                )}
                {kycAlerts.pending_kyc > 0 && (
                  <AttentionCard
                    label={`${kycAlerts.pending_kyc} contact${kycAlerts.pending_kyc > 1 ? "s" : ""} pending KYC review`}
                    count={kycAlerts.pending_kyc}
                    href="/contacts/kyc"
                    urgency="medium"
                  />
                )}
                {kycAlerts.flagged > 0 && (
                  <AttentionCard
                    label={`${kycAlerts.flagged} contact${kycAlerts.flagged > 1 ? "s" : ""} flagged`}
                    count={kycAlerts.flagged}
                    href="/contacts/kyc"
                    urgency="high"
                  />
                )}
              </div>
            )}
          </section>
        )}

        {/* Recent journals */}
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-base font-semibold">Recent journal entries</h2>
            <Link
              href="/journals"
              className="flex items-center gap-1 text-sm text-primary hover:underline"
            >
              View all <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>

          {journalsError ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              Failed to load journals: {journalsError}
            </div>
          ) : journalsLoading ? (
            <div className="rounded-xl border bg-card shadow-sm p-4 space-y-3">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-5 w-full" />)}
            </div>
          ) : journals && journals.length > 0 ? (
            <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/40">
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Number</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Date</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Description</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Total Debit</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {journals.map((je) => (
                    <tr key={je.id} className="hover:bg-muted/20 transition-colors">
                      <td className="px-4 py-3 font-mono text-xs font-medium text-foreground">{je.number}</td>
                      <td className="px-4 py-3 text-muted-foreground">{fmtDate(je.date)}</td>
                      <td className="px-4 py-3 max-w-xs truncate text-foreground">{je.description}</td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums text-foreground">{fmt(je.total_debit)}</td>
                      <td className="px-4 py-3"><StatusBadge status={je.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-xl border bg-card shadow-sm p-10 text-center">
              <BookMarked className="mx-auto mb-3 h-8 w-8 text-muted-foreground/40" />
              <p className="text-sm font-medium text-muted-foreground">No journal entries yet</p>
              <Link
                href="/journals"
                className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                <Plus className="h-3.5 w-3.5" /> Post your first entry
              </Link>
            </div>
          )}
        </section>

        {/* Anomalies */}
        <section>
          <div className="mb-3 flex items-center gap-2">
            <ShieldAlert className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-base font-semibold">Anomalies</h2>
          </div>

          {anomaliesLoading ? (
            <div className="rounded-xl border bg-card shadow-sm p-4 space-y-3">
              {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-5 w-full" />)}
            </div>
          ) : anomaliesError ? (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
              Failed to load anomalies: {anomaliesError instanceof Error ? anomaliesError.message : String(anomaliesError)}
            </div>
          ) : anomalies && anomalies.length > 0 ? (
            <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/40">
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Severity</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Journal</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Description</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Detail</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {anomalies.map((a) => (
                    <tr key={a.journal_id} className="hover:bg-muted/20 transition-colors">
                      <td className="px-4 py-3">
                        <AnomalySeverityBadge severity={a.severity} />
                      </td>
                      <td className="px-4 py-3 font-mono text-xs font-medium">{a.journal_number}</td>
                      <td className="px-4 py-3 max-w-xs truncate text-foreground">{a.description}</td>
                      <td className="px-4 py-3 max-w-xs truncate text-muted-foreground text-xs">{a.detail}</td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums">{a.amount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex items-center gap-2 rounded-xl border bg-green-50 px-4 py-3 text-sm font-medium text-green-700 dark:bg-green-900/20 dark:text-green-400">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              No anomalies detected
            </div>
          )}
        </section>
      </div>
    </>
  );
}
