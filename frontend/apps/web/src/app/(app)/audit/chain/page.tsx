"use client";

import { useEffect, useState } from "react";
import { CheckCircle, XCircle, CheckSquare } from "lucide-react";
import { auditApi, type ChainVerification } from "@/lib/api";
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

export default function ChainVerificationPage() {
  const [latest, setLatest] = useState<ChainVerification | null>(null);
  const [history, setHistory] = useState<ChainVerification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await auditApi.getChainVerification();
      setLatest(res.latest);
      setHistory(res.history);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function triggerVerification() {
    setVerifying(true);
    setVerifyError(null);
    try {
      await auditApi.triggerVerification();
      await load();
    } catch (e) {
      setVerifyError(String(e));
    } finally {
      setVerifying(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const actions = (
    <button
      onClick={() => { void triggerVerification(); }}
      disabled={verifying || loading}
      className="rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60 flex items-center gap-1.5"
    >
      <CheckSquare className="h-4 w-4" />
      {verifying ? "Verifying…" : "Verify Now"}
    </button>
  );

  return (
    <>
      <PageHeader title="Hash Chain Verification" subtitle="Tamper-evidence check on the audit trail" actions={actions} />

      <div className="mx-auto max-w-5xl px-6 py-6 space-y-6">
        {error && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        )}
        {verifyError && (
          <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
            Verification error: {verifyError}
          </div>
        )}

        {/* Status card */}
        {loading ? (
          <div className="rounded-xl border bg-card shadow-sm p-8 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">Loading chain status…</p>
          </div>
        ) : latest ? (
          <div
            className={`rounded-xl border p-8 shadow-sm flex flex-col items-center text-center gap-4 ${
              latest.is_valid
                ? "border-green-200 bg-green-50"
                : "border-red-200 bg-red-50"
            }`}
          >
            {latest.is_valid ? (
              <CheckCircle className="h-14 w-14 text-green-600" />
            ) : (
              <XCircle className="h-14 w-14 text-red-600" />
            )}
            <div>
              <p
                className={`text-2xl font-bold ${
                  latest.is_valid ? "text-green-800" : "text-red-800"
                }`}
              >
                {latest.is_valid ? "Chain Intact" : "Chain Break Detected"}
              </p>
              {!latest.is_valid && latest.break_at_event_id && (
                <p className="mt-1 text-sm text-red-700">
                  Break at event:{" "}
                  <span className="font-mono">{latest.break_at_event_id}</span>
                </p>
              )}
              {!latest.is_valid && latest.error_message && (
                <p className="mt-1 text-sm text-red-700">{latest.error_message}</p>
              )}
            </div>
            <div className="flex gap-8 text-sm">
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-1">
                  Chain Length
                </p>
                <p className="text-xl font-semibold tabular-nums">
                  {latest.chain_length.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground mb-1">
                  Last Verified
                </p>
                <p className="text-base font-medium">{fmtDate(latest.verified_at)}</p>
              </div>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border bg-card shadow-sm p-8 text-center">
            <p className="text-sm text-muted-foreground">No verification has been run yet.</p>
            <p className="mt-2 text-xs text-muted-foreground">Click "Verify Now" to run the first check.</p>
          </div>
        )}

        {/* History table */}
        <section>
          <h2 className="text-base font-semibold mb-3">Verification History</h2>
          <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/40">
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Verified At</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Chain Length</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Error</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {history.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-6 text-center text-sm text-muted-foreground">
                      No history yet.
                    </td>
                  </tr>
                ) : (
                  history.map((v) => (
                    <tr key={v.id} className="hover:bg-muted/20 transition-colors">
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground whitespace-nowrap">
                        {fmtDate(v.verified_at)}
                      </td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums">
                        {v.chain_length.toLocaleString()}
                      </td>
                      <td className="px-4 py-3">
                        {v.is_valid ? (
                          <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                            Valid
                          </span>
                        ) : (
                          <span className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-red-100 text-red-600 dark:bg-red-900/20 dark:text-red-400">
                            Invalid
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground max-w-xs truncate">
                        {v.error_message ?? "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  );
}
