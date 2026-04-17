"use client";

import { showToast } from "@/lib/toast";
import { useEffect, useState } from "react";
import { periodsApi, type Period } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";

const TRANSITIONS: Record<string, { label: string; nextStatus: string }[]> = {
  open: [{ label: "Soft Close", nextStatus: "soft_closed" }],
  soft_closed: [
    { label: "Hard Close", nextStatus: "hard_closed" },
    { label: "Reopen", nextStatus: "open" },
  ],
  hard_closed: [{ label: "Mark Audited", nextStatus: "audited" }],
  audited: [],
};

export default function PeriodsPage() {
  const [periods, setPeriods] = useState<Period[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await periodsApi.list();
      setPeriods(res.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load periods");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleTransition(period: Period, nextStatus: string, label: string) {
    if (!window.confirm(`${label} period "${period.name}"? This action will change the period status to "${nextStatus}".`)) return;
    try {
      await periodsApi.transition(period.id, nextStatus);
      await load();
    } catch (e: unknown) {
      showToast("error", "Transition failed", e instanceof Error ? e.message : undefined);
    }
  }

  return (
    <>
      <PageHeader
        title="Accounting Periods"
        subtitle="Manage period status and closing"
      />
      <div className="mx-auto max-w-5xl px-6 py-6">
        {error && (
          <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-16 text-muted-foreground">
            Loading periods…
          </div>
        ) : periods.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-sm text-muted-foreground">
            No periods found. Periods are created automatically during year-end setup.
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b bg-muted/40 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-3">Period</th>
                  <th className="px-4 py-3">Start</th>
                  <th className="px-4 py-3">End</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {periods.map((period) => {
                  const actions = TRANSITIONS[period.status] ?? [];
                  return (
                    <tr key={period.id} className="hover:bg-muted/20">
                      <td className="px-4 py-3 font-medium text-sm">{period.name}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{period.start_date}</td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">{period.end_date}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={period.status} />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {actions.map((action) => (
                            <button
                              key={action.nextStatus}
                              onClick={() => void handleTransition(period, action.nextStatus, action.label)}
                              className="rounded-md border px-3 py-1 text-xs font-medium hover:bg-muted transition-colors"
                            >
                              {action.label}
                            </button>
                          ))}
                          {actions.length === 0 && (
                            <span className="text-xs text-muted-foreground">No actions</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
