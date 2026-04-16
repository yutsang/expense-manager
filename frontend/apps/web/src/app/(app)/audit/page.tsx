"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { periodsApi, type Period } from "@/lib/api";
import { getTenantIdOrRedirect } from "@/lib/get-tenant-id";
import { PageHeader } from "@/components/page-header";

// ── Period status badge ───────────────────────────────────────────────────────

const PERIOD_STATUS_CLASSES: Record<string, string> = {
  open:         "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  soft_closed:  "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-500",
  hard_closed:  "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  audited:      "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
};

function PeriodStatusBadge({ status }: { status: string }) {
  const cls = PERIOD_STATUS_CLASSES[status] ?? "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status.replace("_", " ")}
    </span>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return (
    <div className="rounded-xl border bg-card p-5 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-2 text-3xl font-semibold tabular-nums text-foreground">{value}</p>
      {note && <p className="mt-1 text-xs text-muted-foreground">{note}</p>}
    </div>
  );
}

// ── Quick link card ───────────────────────────────────────────────────────────

function QuickLink({ href, title, description }: { href: string; title: string; description: string }) {
  return (
    <Link
      href={href}
      className="flex items-start gap-4 rounded-xl border bg-card p-5 shadow-sm transition-colors hover:bg-muted/40"
    >
      <div>
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
      </div>
    </Link>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AuditCentrePage() {
  const router = useRouter();
  const [periods, setPeriods] = useState<Period[]>([]);
  const [periodsLoading, setPeriodsLoading] = useState(true);
  const [selectedPeriodId, setSelectedPeriodId] = useState<string>("");
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);

  useEffect(() => {
    setPeriodsLoading(true);
    periodsApi
      .list()
      .then((res) => {
        setPeriods(res.items);
      })
      .catch(() => {
        // Non-fatal — page still usable
      })
      .finally(() => {
        setPeriodsLoading(false);
      });
  }, []);

  const selectedPeriod = periods.find((p) => p.id === selectedPeriodId) ?? null;

  async function handleGeneratePackage() {
    if (!selectedPeriodId) return;
    setGenerating(true);
    setGenerateError(null);
    try {
      const token =
        typeof window !== "undefined" ? localStorage.getItem("aegis_token") : null;
      let tenantId: string;
      try {
        tenantId = getTenantIdOrRedirect(router);
      } catch {
        setGenerating(false);
        return;
      }

      const res = await fetch("/v1/audit/evidence-package", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Tenant-ID": tenantId,
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        credentials: "include",
        body: JSON.stringify({ period_id: selectedPeriodId }),
      });

      if (!res.ok) {
        let detail = res.statusText;
        try {
          const err = (await res.json()) as { detail?: string };
          detail = err.detail ?? detail;
        } catch {
          // ignore
        }
        throw new Error(detail);
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const periodName = selectedPeriod?.name ?? selectedPeriodId;
      a.download = `evidence-package-${periodName.replace(/\s+/g, "-")}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setGenerateError(String(e instanceof Error ? e.message : e));
    } finally {
      setGenerating(false);
    }
  }

  const noPeriodSelected = !selectedPeriodId;

  return (
    <>
      <PageHeader
        title="Audit Centre"
        subtitle="Evidence and records for external audit"
      />

      <div className="mx-auto max-w-5xl px-6 py-8 space-y-10">

        {/* Period selector */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Accounting Period
          </h2>
          <div className="flex items-center gap-4">
            <select
              value={selectedPeriodId}
              onChange={(e) => setSelectedPeriodId(e.target.value)}
              disabled={periodsLoading}
              className="rounded-lg border px-3 py-2 text-sm bg-background min-w-[260px]"
            >
              <option value="">
                {periodsLoading ? "Loading periods…" : "Select a period"}
              </option>
              {periods.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            {selectedPeriod && (
              <PeriodStatusBadge status={selectedPeriod.status} />
            )}
          </div>
        </section>

        {/* At-a-glance stats */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Period Summary
          </h2>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard
              label="Journal Entries"
              value={noPeriodSelected ? "—" : 0}
              note={noPeriodSelected ? "Select a period" : undefined}
            />
            <StatCard
              label="Total Transactions Value"
              value={noPeriodSelected ? "—" : 0}
              note={noPeriodSelected ? "Select a period" : undefined}
            />
            <StatCard
              label="Flagged KYC Contacts"
              value={noPeriodSelected ? "—" : 0}
              note={noPeriodSelected ? "Select a period" : undefined}
            />
            <StatCard
              label="Unresolved Sanctions Flags"
              value={noPeriodSelected ? "—" : 0}
              note={noPeriodSelected ? "Select a period" : undefined}
            />
          </div>
        </section>

        {/* Evidence package */}
        <section>
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Download Evidence Package
          </h2>
          <p className="mb-4 text-sm text-muted-foreground">
            Export all journal entries, source documents, and audit trail for the selected period as a ZIP file.
          </p>
          {generateError && (
            <div className="mb-4 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {generateError}
            </div>
          )}
          <button
            onClick={() => { void handleGeneratePackage(); }}
            disabled={noPeriodSelected || generating}
            className="rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {generating ? "Generating…" : "Generate & Download"}
          </button>
          {noPeriodSelected && (
            <p className="mt-2 text-xs text-muted-foreground">
              Select a period above to enable download.
            </p>
          )}
        </section>

        {/* Quick links */}
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Quick Links
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <QuickLink
              href="/audit/timeline"
              title="Audit Trail"
              description="Full immutable event log with before/after diffs"
            />
            <QuickLink
              href="/audit/chain"
              title="Chain Verification"
              description="Verify the cryptographic hash chain is unbroken"
            />
            <QuickLink
              href="/audit/sampling"
              title="Statistical Sampling"
              description="Random sample selection for spot-check audits"
            />
          </div>
        </section>

      </div>
    </>
  );
}
