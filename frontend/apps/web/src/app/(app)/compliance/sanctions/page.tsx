"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { RefreshCw, Search, ShieldAlert, ShieldCheck, Globe, User, Building2 } from "lucide-react";
import {
  sanctionsApi,
  type SanctionsEntry,
  type SanctionsSnapshot,
} from "@/lib/api";
import { PageHeader } from "@/components/page-header";

// ── Helpers ───────────────────────────────────────────────────────────────────

const SOURCE_LABELS: Record<string, { label: string; short: string; color: string }> = {
  ofac_consolidated: {
    label: "OFAC Consolidated List",
    short: "OFAC",
    color: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
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
};

function SourceBadge({ source }: { source: string }) {
  const def = SOURCE_LABELS[source] ?? { short: source, color: "bg-muted text-muted-foreground" };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${def.color}`}>
      {def.short}
    </span>
  );
}

function EntityIcon({ type }: { type: string }) {
  if (type === "individual") return <User className="h-3.5 w-3.5 text-muted-foreground" />;
  if (type === "country") return <Globe className="h-3.5 w-3.5 text-muted-foreground" />;
  return <Building2 className="h-3.5 w-3.5 text-muted-foreground" />;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3_600_000);
  if (h < 24) return h < 1 ? "just now" : `${h}h ago`;
  const d = Math.floor(h / 24);
  return d === 1 ? "yesterday" : `${d} days ago`;
}

// ── Snapshot cards ─────────────────────────────────────────────────────────────

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

// ── Main page ─────────────────────────────────────────────────────────────────

const PAGE_SIZE = 50;

export default function SanctionsListsPage() {
  const [snapshots, setSnapshots] = useState<SanctionsSnapshot[]>([]);
  const [entries, setEntries] = useState<SanctionsEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Load snapshots once
  useEffect(() => {
    sanctionsApi.snapshots().then(setSnapshots).catch(() => null);
  }, []);

  // Load entries whenever filter/page changes
  useEffect(() => {
    setLoading(true);
    setError(null);
    sanctionsApi
      .entries({
        ...(query ? { q: query } : {}),
        ...(sourceFilter ? { source: sourceFilter } : {}),
        limit: PAGE_SIZE,
        offset,
      })
      .then((res) => {
        setEntries(res.items);
        setTotal(res.total);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [query, sourceFilter, offset]);

  function handleSearch(val: string) {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setQuery(val);
      setOffset(0);
    }, 300);
  }

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await sanctionsApi.refresh();
      // reload snapshots after a short delay (refresh is async)
      setTimeout(() => {
        sanctionsApi.snapshots().then(setSnapshots).catch(() => null);
        setRefreshing(false);
      }, 2000);
    } catch {
      setRefreshing(false);
    }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

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
      <PageHeader title="Sanctions Lists" subtitle="OFAC and FATF reference data used for contact screening" actions={actions} />

      {/* Snapshot status cards */}
      {snapshots.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-3">
          {snapshots.map((s) => (
            <SnapshotCard key={s.id} snap={s} />
          ))}
        </div>
      )}

      {snapshots.length === 0 && !loading && (
        <div className="rounded-xl border border-dashed p-8 text-center">
          <ShieldAlert className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
          <p className="text-sm font-medium text-foreground">No sanctions lists loaded yet</p>
          <p className="text-xs text-muted-foreground mt-1">
            Click <strong>Refresh Lists</strong> to fetch OFAC and FATF data.
          </p>
        </div>
      )}

      {/* Search + filter bar */}
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Search by name or reference ID…"
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full rounded-lg border bg-background pl-9 pr-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <select
          value={sourceFilter}
          onChange={(e) => { setSourceFilter(e.target.value); setOffset(0); }}
          className="rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All lists</option>
          <option value="ofac_consolidated">OFAC Consolidated</option>
          <option value="fatf_blacklist">FATF Black List</option>
          <option value="fatf_greylist">FATF Grey List</option>
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Results count */}
      {!loading && (
        <p className="text-xs text-muted-foreground">
          {total.toLocaleString()} {total === 1 ? "entry" : "entries"} found
          {query ? ` matching "${query}"` : ""}
        </p>
      )}

      {/* Table */}
      <div className="rounded-xl border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">Name</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide hidden md:table-cell">Aliases</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide hidden lg:table-cell">Countries</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide hidden lg:table-cell">Programs</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">List</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {loading && (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-sm text-muted-foreground">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && entries.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-12 text-center text-sm text-muted-foreground">
                  {query ? "No entries match your search." : "No entries loaded. Refresh the lists first."}
                </td>
              </tr>
            )}
            {!loading && entries.map((entry) => (
              <tr key={entry.id} className="hover:bg-muted/30 transition-colors cursor-pointer">
                <td className="px-4 py-3">
                  <Link href={`/compliance/sanctions/${entry.id}`} className="flex items-center gap-2">
                    <EntityIcon type={entry.entity_type} />
                    <div>
                      <p className="font-medium text-foreground leading-tight hover:underline">{entry.primary_name}</p>
                      <p className="text-xs text-muted-foreground truncate max-w-[280px]" title={entry.ref_id}>
                        {entry.ref_id} · {entry.entity_type.replace("_", " ")}
                      </p>
                    </div>
                  </Link>
                </td>
                <td className="px-4 py-3 hidden md:table-cell">
                  {entry.aliases.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {entry.aliases.slice(0, 3).map((a, i) => (
                        <span key={i} className="inline-block rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground max-w-[160px] truncate" title={a.name}>
                          {a.name}
                        </span>
                      ))}
                      {entry.aliases.length > 3 && (
                        <span className="inline-block rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                          +{entry.aliases.length - 3}
                        </span>
                      )}
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </td>
                <td className="px-4 py-3 hidden lg:table-cell">
                  {entry.countries.length > 0 ? (
                    <span className="text-xs text-muted-foreground">{entry.countries.slice(0, 3).join(", ")}{entry.countries.length > 3 ? ` +${entry.countries.length - 3}` : ""}</span>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </td>
                <td className="px-4 py-3 hidden lg:table-cell">
                  {entry.programs.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {entry.programs.slice(0, 2).map((p, i) => (
                        <span key={i} className="inline-block rounded bg-blue-50 dark:bg-blue-900/20 px-1.5 py-0.5 text-xs text-blue-700 dark:text-blue-400">
                          {p}
                        </span>
                      ))}
                      {entry.programs.length > 2 && (
                        <span className="text-xs text-muted-foreground">+{entry.programs.length - 2}</span>
                      )}
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <SourceBadge source={entry.source} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <p className="text-muted-foreground">
            Page {currentPage} of {totalPages}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0}
              className="rounded-lg border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <button
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total}
              className="rounded-lg border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
