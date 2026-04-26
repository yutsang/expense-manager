"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  ChevronRight,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { sanctionsApi, type SanctionsSnapshot } from "@/lib/api";
import { PageHeader } from "@/components/page-header";

const SOURCE_LABELS: Record<string, { label: string; color: string }> = {
  ofac_consolidated: {
    label: "OFAC Consolidated List",
    color: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  un_consolidated: {
    label: "UN Consolidated Sanctions List",
    color: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  },
  uk_ofsi: {
    label: "UK OFSI Consolidated",
    color: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400",
  },
  eu_consolidated: {
    label: "EU Consolidated Sanctions",
    color: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  },
  fatf_blacklist: {
    label: "FATF High-Risk Jurisdictions (Black List)",
    color: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  fatf_greylist: {
    label: "FATF Jurisdictions under Monitoring (Grey List)",
    color: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  },
  opensanctions_default: {
    label: "OpenSanctions (aggregated)",
    color: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  },
  opensanctions_pep: {
    label: "OpenSanctions PEPs",
    color: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  },
};

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3_600_000);
  if (h < 24) return h < 1 ? "just now" : `${h}h ago`;
  const d = Math.floor(h / 24);
  return d === 1 ? "yesterday" : `${d} days ago`;
}

function SnapshotCard({ snap }: { snap: SanctionsSnapshot }) {
  const def = SOURCE_LABELS[snap.source];
  const isRisk = snap.source === "fatf_blacklist";
  const isGrey = snap.source === "fatf_greylist";
  const icon = isRisk || isGrey ? (
    <ShieldAlert className={`h-5 w-5 ${isRisk ? "text-red-500" : "text-yellow-500"}`} />
  ) : (
    <ShieldCheck className="h-5 w-5 text-blue-500" />
  );

  return (
    <div className="rounded-xl border bg-card p-4 flex items-start gap-3">
      <div className="mt-0.5">{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold leading-tight">{def?.label ?? snap.source}</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {snap.entry_count.toLocaleString()} entries · updated {relativeTime(snap.fetched_at)}
        </p>
        <p className="text-xs text-muted-foreground font-mono mt-0.5 truncate" title={snap.sha256_hash}>
          sha256: {snap.sha256_hash.slice(0, 16)}…
        </p>
      </div>
      {snap.is_active && (
        <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 shrink-0">
          Active
        </span>
      )}
    </div>
  );
}

export default function SanctionsListsPage() {
  const router = useRouter();
  const [snapshots, setSnapshots] = useState<SanctionsSnapshot[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [quickQuery, setQuickQuery] = useState("");

  useEffect(() => {
    sanctionsApi.snapshots().then(setSnapshots).catch(() => null);
  }, []);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await sanctionsApi.refresh();
      // Refresh runs server-side ~5–7 min; reload snapshot status periodically
      setTimeout(() => {
        sanctionsApi.snapshots().then(setSnapshots).catch(() => null);
        setRefreshing(false);
      }, 4000);
    } catch {
      setRefreshing(false);
    }
  }

  function handleQuickSearch(e: React.FormEvent) {
    e.preventDefault();
    const q = quickQuery.trim();
    router.push(q ? `/compliance/sanctions/browse?q=${encodeURIComponent(q)}` : "/compliance/sanctions/browse");
  }

  const totalEntries = snapshots
    .filter((s) => s.is_active)
    .reduce((sum, s) => sum + s.entry_count, 0);
  const lastFetchedIso = snapshots
    .filter((s) => s.is_active)
    .map((s) => s.fetched_at)
    .sort()
    .at(-1);

  const actions = (
    <button
      onClick={() => { void handleRefresh(); }}
      disabled={refreshing}
      className="flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-60"
    >
      <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
      {refreshing ? "Refreshing…" : "Refresh Lists"}
    </button>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Sanctions Lists"
        subtitle={
          totalEntries > 0
            ? `${totalEntries.toLocaleString()} entries across ${snapshots.filter((s) => s.is_active).length} active lists${lastFetchedIso ? ` · last refreshed ${relativeTime(lastFetchedIso)}` : ""}`
            : "OFAC, UN, UK OFSI, EU, FATF and OpenSanctions reference data used for contact screening"
        }
        actions={actions}
      />

      {/* Quick search → /browse */}
      <form onSubmit={handleQuickSearch} className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Search the lists — e.g. Carrie Lam, Wagner Group…"
            value={quickQuery}
            onChange={(e) => setQuickQuery(e.target.value)}
            className="w-full rounded-lg border bg-background pl-9 pr-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <button
          type="submit"
          className="rounded-lg border bg-foreground text-background px-4 py-2 text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Search
        </button>
      </form>

      <Link
        href="/compliance/sanctions/browse"
        className="flex items-center justify-between rounded-xl border bg-card p-4 hover:bg-muted/30 transition-colors"
      >
        <div>
          <p className="text-sm font-medium">Browse all entries</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Search and paginate the full list across every source.
          </p>
        </div>
        <ChevronRight className="h-4 w-4 text-muted-foreground" />
      </Link>

      {/* Snapshot status cards */}
      {snapshots.length > 0 && (
        <div>
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Active sources
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {snapshots.map((s) => (
              <SnapshotCard key={s.id} snap={s} />
            ))}
          </div>
        </div>
      )}

      {snapshots.length === 0 && (
        <div className="rounded-xl border border-dashed p-8 text-center">
          <ShieldAlert className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
          <p className="text-sm font-medium text-foreground">No sanctions lists loaded yet</p>
          <p className="text-xs text-muted-foreground mt-1">
            Click <strong>Refresh Lists</strong> to fetch the data.
          </p>
        </div>
      )}
    </div>
  );
}
