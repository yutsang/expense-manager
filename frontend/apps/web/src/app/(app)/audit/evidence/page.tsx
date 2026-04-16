"use client";

import { useState } from "react";
import { Package, FileText, Shield, Hash } from "lucide-react";
import { auditApi } from "@/lib/api";
import { PageHeader } from "@/components/page-header";

export default function EvidencePackagePage() {
  const today = new Date().toISOString().slice(0, 10);
  const firstOfYear = `${new Date().getFullYear()}-01-01`;

  const [fromDate, setFromDate] = useState(firstOfYear);
  const [toDate, setToDate] = useState(today);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  async function handleGenerate() {
    if (!fromDate || !toDate) {
      setError("Please select both a from date and a to date.");
      return;
    }
    setLoading(true);
    setError(null);
    setSuccess(false);
    try {
      const res = await auditApi.downloadEvidencePackage(fromDate, toDate);
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = await res.json() as { detail?: string };
          detail = body.detail ?? detail;
        } catch {
          // ignore
        }
        throw new Error(detail);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `evidence-${fromDate}-${toDate}.zip`;
      a.click();
      URL.revokeObjectURL(url);
      setSuccess(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Evidence Package Builder"
        subtitle="Generate a tamper-evident evidence archive for auditors"
      />

      <div className="mx-auto max-w-3xl px-6 py-6 space-y-6">
        {/* Form card */}
        <div className="rounded-xl border bg-card shadow-sm p-6 space-y-5">
          <h2 className="text-sm font-semibold">Date Range</h2>
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">From</label>
              <input
                type="date"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
                className="rounded-lg border px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">To</label>
              <input
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                className="rounded-lg border px-3 py-2 text-sm"
              />
            </div>
            <button
              onClick={() => { void handleGenerate(); }}
              disabled={loading}
              className="rounded-lg bg-primary px-6 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60 flex items-center gap-1.5"
            >
              {loading ? (
                <>
                  <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
                  Generating…
                </>
              ) : (
                <>
                  <Package className="h-4 w-4" />
                  Generate &amp; Download
                </>
              )}
            </button>
          </div>

          {error && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {error}
            </div>
          )}
          {success && (
            <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
              Evidence package downloaded successfully.
            </div>
          )}
        </div>

        {/* Info card */}
        <div className="rounded-xl border bg-muted/30 p-6 space-y-4">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <Shield className="h-4 w-4 text-muted-foreground" />
            What is included in the package?
          </h2>
          <ul className="space-y-3">
            <li className="flex items-start gap-3">
              <FileText className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">journals.csv</p>
                <p className="text-xs text-muted-foreground">All posted journal entries and their lines for the selected period.</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <Shield className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">audit_events.csv</p>
                <p className="text-xs text-muted-foreground">Complete audit log for the period, including all creates, updates, deletes, and system actions.</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <Hash className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">chain_verification.json</p>
                <p className="text-xs text-muted-foreground">Hash chain verification result confirming the audit log has not been tampered with.</p>
              </div>
            </li>
            <li className="flex items-start gap-3">
              <FileText className="h-4 w-4 mt-0.5 shrink-0 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium">manifest.json</p>
                <p className="text-xs text-muted-foreground">SHA-256 hashes of every file in the archive, signed with the tenant&apos;s audit key for integrity verification.</p>
              </div>
            </li>
          </ul>
        </div>
      </div>
    </>
  );
}
