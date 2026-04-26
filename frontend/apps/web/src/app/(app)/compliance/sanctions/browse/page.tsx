"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { ArrowLeft, Search, Globe, User, Building2 } from "lucide-react";
import {
  sanctionsApi,
  type SanctionsEntry,
} from "@/lib/api";

const SOURCE_LABELS: Record<string, { short: string; color: string }> = {
  ofac_consolidated: {
    short: "OFAC",
    color: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  un_consolidated: {
    short: "UN",
    color: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  },
  uk_ofsi: {
    short: "UK OFSI",
    color: "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400",
  },
  eu_consolidated: {
    short: "EU",
    color: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  },
  fatf_blacklist: {
    short: "FATF Black",
    color: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  fatf_greylist: {
    short: "FATF Grey",
    color: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  },
  opensanctions_default: {
    short: "OpenSanctions",
    color: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  },
  opensanctions_pep: {
    short: "PEPs",
    color: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
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

const PAGE_SIZE = 50;

function BrowseInner() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams.get("q") ?? "";
  const initialSource = searchParams.get("source") ?? "";

  const [entries, setEntries] = useState<SanctionsEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState(initialQuery);
  const [sourceFilter, setSourceFilter] = useState(initialSource);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div className="space-y-6">
      <Link
        href="/compliance/sanctions"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to overview
      </Link>

      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Browse sanctions entries</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Multi-token search across name, aliases, countries, programs, and sanctioning authorities.
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            defaultValue={initialQuery}
            placeholder="e.g. Carrie Lam, Kim Jong Un, Wagner Group…"
            onChange={(e) => handleSearch(e.target.value)}
            className="w-full rounded-lg border bg-background pl-9 pr-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
        <select
          value={sourceFilter}
          onChange={(e) => { setSourceFilter(e.target.value); setOffset(0); }}
          className="rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        >
          <option value="">All sources</option>
          <option value="opensanctions_default">OpenSanctions (aggregated)</option>
          <option value="ofac_consolidated">OFAC Consolidated</option>
          <option value="un_consolidated">UN Consolidated</option>
          <option value="uk_ofsi">UK OFSI</option>
          <option value="eu_consolidated">EU Consolidated</option>
          <option value="fatf_blacklist">FATF Black List</option>
          <option value="fatf_greylist">FATF Grey List</option>
        </select>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
          {error}
        </div>
      )}

      {!loading && (
        <p className="text-xs text-muted-foreground">
          {total.toLocaleString()} {total === 1 ? "entry" : "entries"} found
          {query ? ` matching "${query}"` : ""}
        </p>
      )}

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

export default function SanctionsBrowsePage() {
  return (
    <Suspense fallback={<div className="text-sm text-muted-foreground">Loading…</div>}>
      <BrowseInner />
    </Suspense>
  );
}
