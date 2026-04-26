"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Building2,
  Globe,
  ShieldAlert,
  ShieldCheck,
  User,
} from "lucide-react";
import { sanctionsApi, type SanctionsEntry } from "@/lib/api";

const SOURCE_LABELS: Record<string, { label: string; short: string; color: string }> = {
  ofac_consolidated: {
    label: "OFAC Consolidated List",
    short: "OFAC",
    color: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  un_consolidated: {
    label: "UN Consolidated Sanctions List",
    short: "UN",
    color: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  },
  uk_ofsi: {
    label: "UK OFSI Consolidated",
    short: "UK OFSI",
    color: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400",
  },
  eu_consolidated: {
    label: "EU Consolidated Sanctions",
    short: "EU",
    color: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  },
  fatf_blacklist: {
    label: "FATF High-Risk Jurisdictions (Black List)",
    short: "FATF Black",
    color: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  fatf_greylist: {
    label: "FATF Jurisdictions under Monitoring (Grey List)",
    short: "FATF Grey",
    color: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  },
  opensanctions_default: {
    label: "OpenSanctions (aggregated)",
    short: "OpenSanctions",
    color: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  },
  opensanctions_pep: {
    label: "OpenSanctions PEPs",
    short: "PEPs",
    color: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  },
};

function EntityIcon({ type, className = "h-5 w-5" }: { type: string; className?: string }) {
  if (type === "individual") return <User className={`${className} text-muted-foreground`} />;
  if (type === "country") return <Globe className={`${className} text-muted-foreground`} />;
  return <Building2 className={`${className} text-muted-foreground`} />;
}

export default function SanctionsEntryDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [entry, setEntry] = useState<SanctionsEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    sanctionsApi
      .entry(id)
      .then(setEntry)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  const sourceDef = entry ? SOURCE_LABELS[entry.source] : undefined;
  const isHighRisk = entry?.source === "fatf_blacklist";

  return (
    <div className="space-y-6">
      <Link
        href="/compliance/sanctions"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to sanctions list
      </Link>

      {loading && (
        <div className="rounded-xl border bg-card p-8 text-center text-sm text-muted-foreground">
          Loading…
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
          {error}
        </div>
      )}

      {entry && (
        <>
          <div className="flex items-start gap-3">
            {isHighRisk ? (
              <ShieldAlert className="h-7 w-7 text-red-500 shrink-0 mt-1" />
            ) : (
              <ShieldCheck className="h-7 w-7 text-blue-500 shrink-0 mt-1" />
            )}
            <div className="min-w-0 flex-1">
              <h1 className="text-2xl font-semibold tracking-tight break-words">
                {entry.primary_name}
              </h1>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                <EntityIcon type={entry.entity_type} className="h-4 w-4" />
                <span className="capitalize">{entry.entity_type.replace("_", " ")}</span>
                <span>·</span>
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${sourceDef?.color ?? "bg-muted text-muted-foreground"}`}
                >
                  {sourceDef?.label ?? entry.source}
                </span>
              </div>
            </div>
          </div>

          {/* Reference ID — long IDs from OpenSanctions can wrap */}
          <div className="rounded-xl border bg-card p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-1">
              Reference ID
            </p>
            <p className="font-mono text-sm break-all">{entry.ref_id}</p>
          </div>

          {/* Aliases */}
          {entry.aliases.length > 0 && (
            <div className="rounded-xl border bg-card p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">
                Known aliases ({entry.aliases.length})
              </p>
              <ul className="space-y-1.5">
                {entry.aliases.map((a, i) => (
                  <li key={i} className="flex items-baseline gap-2">
                    <span className="text-xs text-muted-foreground shrink-0 w-16">{a.type}</span>
                    <span className="text-sm font-medium">{a.name}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Two-column grid for countries + programs */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border bg-card p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                Countries
              </p>
              {entry.countries.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {entry.countries.map((c, i) => (
                    <span
                      key={i}
                      className="inline-block rounded bg-muted px-2 py-0.5 text-xs uppercase tracking-wide"
                    >
                      {c}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">—</p>
              )}
            </div>

            <div className="rounded-xl border bg-card p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                Programs
              </p>
              {entry.programs.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {entry.programs.map((p, i) => (
                    <span
                      key={i}
                      className="inline-block rounded bg-blue-50 dark:bg-blue-900/20 px-2 py-0.5 text-xs text-blue-700 dark:text-blue-400"
                    >
                      {p}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">—</p>
              )}
            </div>
          </div>

          {/* Remarks (free-text) */}
          {entry.remarks && (
            <div className="rounded-xl border bg-card p-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                Remarks
              </p>
              <p className="text-sm whitespace-pre-wrap break-words">{entry.remarks}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
