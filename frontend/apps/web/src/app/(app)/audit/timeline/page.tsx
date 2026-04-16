"use client";

import { useEffect, useState } from "react";
import { Shield } from "lucide-react";
import { auditApi, type AuditEvent } from "@/lib/api";
import { PageHeader } from "@/components/page-header";

function fmtDate(val: string): string {
  return new Date(val).toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

const ACTOR_TYPE_CLASSES: Record<string, string> = {
  user:        "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  ai:          "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  system:      "bg-gray-100 text-gray-600 dark:bg-gray-800/60 dark:text-gray-400",
  integration: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
};

function ActorBadge({ type }: { type: string }) {
  const cls = ACTOR_TYPE_CLASSES[type] ?? "bg-gray-100 text-gray-600";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {type}
    </span>
  );
}

function JsonDiff({ label, data }: { label: string; data: Record<string, unknown> | null }) {
  if (!data) return <p className="text-xs text-muted-foreground italic">{label}: (none)</p>;
  return (
    <div>
      <p className="text-xs font-semibold text-muted-foreground mb-1">{label}</p>
      <pre className="text-xs bg-muted rounded-md p-2 overflow-x-auto whitespace-pre-wrap break-all">
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}

const ENTITY_TYPE_OPTIONS = [
  "", "journal_entry", "account", "period", "invoice", "bill", "contact",
  "payment", "user", "tenant",
];

const ACTOR_TYPE_OPTIONS = ["", "user", "ai", "system", "integration"];

export default function AuditTimelinePage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verifyMsg, setVerifyMsg] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Filters
  const [filterAction, setFilterAction] = useState("");
  const [filterEntityType, setFilterEntityType] = useState("");
  const [filterActorType, setFilterActorType] = useState("");
  const [filterFrom, setFilterFrom] = useState("");
  const [filterTo, setFilterTo] = useState("");

  function buildParams(cursor?: string): Record<string, string> {
    const p: Record<string, string> = { limit: "50" };
    if (filterAction) p.action = filterAction;
    if (filterEntityType) p.entity_type = filterEntityType;
    if (filterActorType) p.actor_type = filterActorType;
    if (filterFrom) p.from_date = filterFrom;
    if (filterTo) p.to_date = filterTo;
    if (cursor) p.cursor = cursor;
    return p;
  }

  async function load(reset = true) {
    if (reset) setLoading(true);
    setError(null);
    try {
      const res = await auditApi.listEvents(buildParams());
      setEvents(res.items);
      setNextCursor(res.next_cursor);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function loadMore() {
    if (!nextCursor) return;
    setLoadingMore(true);
    try {
      const res = await auditApi.listEvents(buildParams(nextCursor));
      setEvents((prev) => [...prev, ...res.items]);
      setNextCursor(res.next_cursor);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoadingMore(false);
    }
  }

  async function triggerVerification() {
    setVerifying(true);
    setVerifyMsg(null);
    try {
      const result = await auditApi.triggerVerification();
      setVerifyMsg(
        result.is_valid
          ? `Chain verified — ${result.chain_length} events intact.`
          : `Chain BREAK detected at event ${result.break_at_event_id ?? "unknown"}.`
      );
    } catch (e) {
      setVerifyMsg(`Verification failed: ${String(e)}`);
    } finally {
      setVerifying(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const actions = (
    <button
      onClick={() => { void triggerVerification(); }}
      disabled={verifying}
      className="rounded-lg border px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-muted transition-colors disabled:opacity-60 flex items-center gap-1.5"
    >
      <Shield className="h-4 w-4" />
      {verifying ? "Verifying…" : "Trigger Verification"}
    </button>
  );

  return (
    <>
      <PageHeader title="Audit Timeline" subtitle="Immutable record of every action in the system" actions={actions} />

      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">
        {verifyMsg && (
          <div className={`rounded-lg border px-4 py-3 text-sm font-medium ${verifyMsg.includes("BREAK") ? "border-destructive/30 bg-destructive/5 text-destructive" : "border-green-200 bg-green-50 text-green-800"}`}>
            {verifyMsg}
          </div>
        )}

        {/* Filter bar */}
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Action</label>
            <input
              type="text"
              value={filterAction}
              onChange={(e) => setFilterAction(e.target.value)}
              placeholder="e.g. journal.post"
              className="rounded-lg border px-3 py-2 text-sm w-44"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Entity Type</label>
            <select
              value={filterEntityType}
              onChange={(e) => setFilterEntityType(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm"
            >
              {ENTITY_TYPE_OPTIONS.map((o) => (
                <option key={o} value={o}>{o === "" ? "All" : o}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Actor Type</label>
            <select
              value={filterActorType}
              onChange={(e) => setFilterActorType(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm"
            >
              {ACTOR_TYPE_OPTIONS.map((o) => (
                <option key={o} value={o}>{o === "" ? "All" : o}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">From</label>
            <input
              type="date"
              value={filterFrom}
              onChange={(e) => setFilterFrom(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">To</label>
            <input
              type="date"
              value={filterTo}
              onChange={(e) => setFilterTo(e.target.value)}
              className="rounded-lg border px-3 py-2 text-sm"
            />
          </div>
          <button
            onClick={() => { void load(); }}
            disabled={loading}
            className="rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          >
            {loading ? "Loading…" : "Apply"}
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}

        {/* Table */}
        <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/40">
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Occurred At</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Actor Type</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Action</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Entity Type</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Entity ID</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Actor ID</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-muted-foreground">
                    Loading…
                  </td>
                </tr>
              ) : events.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-muted-foreground">
                    No audit events found.
                  </td>
                </tr>
              ) : (
                events.map((evt) => (
                  <>
                    <tr
                      key={evt.id}
                      className="hover:bg-muted/20 transition-colors cursor-pointer"
                      onClick={() => setExpandedId(expandedId === evt.id ? null : evt.id)}
                    >
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground whitespace-nowrap">{fmtDate(evt.occurred_at)}</td>
                      <td className="px-4 py-3"><ActorBadge type={evt.actor_type} /></td>
                      <td className="px-4 py-3 font-mono text-xs text-foreground">{evt.action}</td>
                      <td className="px-4 py-3 text-muted-foreground">{evt.entity_type}</td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground truncate max-w-[10rem]">{evt.entity_id ?? "—"}</td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground truncate max-w-[10rem]">{evt.actor_id ?? "—"}</td>
                    </tr>
                    {expandedId === evt.id && (
                      <tr key={`${evt.id}-expand`} className="bg-muted/10">
                        <td colSpan={6} className="px-6 py-4">
                          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                            <JsonDiff label="Before" data={evt.before_state} />
                            <JsonDiff label="After" data={evt.after_state} />
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))
              )}
            </tbody>
          </table>
        </div>

        {nextCursor && (
          <div className="flex justify-center">
            <button
              onClick={() => { void loadMore(); }}
              disabled={loadingMore}
              className="rounded-lg border px-6 py-2 text-sm font-medium text-muted-foreground hover:bg-muted transition-colors disabled:opacity-60"
            >
              {loadingMore ? "Loading…" : "Load More"}
            </button>
          </div>
        )}
      </div>
    </>
  );
}
