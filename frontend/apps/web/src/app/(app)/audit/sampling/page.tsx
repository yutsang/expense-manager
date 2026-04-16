"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { auditApi, type AuditSample, type JeTestingReport } from "@/lib/api";
import { PageHeader } from "@/components/page-header";

function fmtDate(val: string): string {
  return new Date(val).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

function SampleTable({ items }: { items: AuditSample[] }) {
  if (items.length === 0) {
    return <p className="text-xs text-muted-foreground px-4 py-3">No entries in this category.</p>;
  }
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b bg-muted/40">
          <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Number</th>
          <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Date</th>
          <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">Description</th>
          <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-wide text-muted-foreground">Debit Total</th>
        </tr>
      </thead>
      <tbody className="divide-y">
        {items.map((s) => (
          <tr key={s.id} className="hover:bg-muted/20 transition-colors">
            <td className="px-4 py-2.5 font-mono text-xs font-medium text-foreground">{s.number}</td>
            <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap">{fmtDate(s.date)}</td>
            <td className="px-4 py-2.5 max-w-xs truncate text-foreground">{s.description}</td>
            <td className="px-4 py-2.5 text-right font-mono tabular-nums text-foreground">{s.debit_total}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

interface CollapsibleSectionProps {
  title: string;
  items: AuditSample[];
}

function CollapsibleSection({ title, items }: CollapsibleSectionProps) {
  const [open, setOpen] = useState(false);
  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-muted/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
          <span className="font-medium text-sm">{title}</span>
          <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
            {items.length}
          </span>
        </div>
      </button>
      {open && <SampleTable items={items} />}
    </div>
  );
}

function exportCsv(items: AuditSample[]) {
  const header = "id,number,date,description,debit_total";
  const rows = items.map((s) =>
    [s.id, s.number, s.date, `"${s.description.replace(/"/g, '""')}"`, s.debit_total].join(",")
  );
  const csv = [header, ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `je-sample-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

type TabId = "sampling" | "je-testing";

export default function SamplingPage() {
  const [activeTab, setActiveTab] = useState<TabId>("sampling");

  // Tab 1: Sampling
  const [sampleMethod, setSampleMethod] = useState("random");
  const [sampleSize, setSampleSize] = useState("25");
  const [sampleSeed, setSampleSeed] = useState("42");
  const [sampleFrom, setSampleFrom] = useState("");
  const [sampleTo, setSampleTo] = useState("");
  const [sampleResults, setSampleResults] = useState<AuditSample[] | null>(null);
  const [sampleLoading, setSampleLoading] = useState(false);
  const [sampleError, setSampleError] = useState<string | null>(null);

  // Tab 2: JE Testing
  const [jeFrom, setJeFrom] = useState(() => {
    const d = new Date();
    return `${d.getFullYear()}-01-01`;
  });
  const [jeTo, setJeTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [jeReport, setJeReport] = useState<JeTestingReport | null>(null);
  const [jeLoading, setJeLoading] = useState(false);
  const [jeError, setJeError] = useState<string | null>(null);

  async function runSampling() {
    const size = parseInt(sampleSize, 10);
    const seed = parseInt(sampleSeed, 10);
    if (isNaN(size) || size < 1 || size > 200) {
      setSampleError("Size must be between 1 and 200.");
      return;
    }
    setSampleLoading(true);
    setSampleError(null);
    try {
      const body: {
        method: string;
        size: number;
        seed: number;
        from_date?: string;
        to_date?: string;
      } = { method: sampleMethod, size, seed: isNaN(seed) ? 42 : seed };
      if (sampleFrom) body.from_date = sampleFrom;
      if (sampleTo) body.to_date = sampleTo;
      const results = await auditApi.sample(body);
      setSampleResults(results);
    } catch (e) {
      setSampleError(String(e));
    } finally {
      setSampleLoading(false);
    }
  }

  async function runJeTesting() {
    setJeLoading(true);
    setJeError(null);
    try {
      const report = await auditApi.jeTestingReport(jeFrom, jeTo);
      setJeReport(report);
    } catch (e) {
      setJeError(String(e));
    } finally {
      setJeLoading(false);
    }
  }

  const tabClasses = (id: TabId) =>
    `px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
      activeTab === id
        ? "border-primary text-primary"
        : "border-transparent text-muted-foreground hover:text-foreground hover:border-muted-foreground"
    }`;

  return (
    <>
      <PageHeader title="Sampling & Testing" subtitle="Journal entry sampling and audit testing procedures" />

      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">
        {/* Tabs */}
        <div className="flex border-b gap-0">
          <button className={tabClasses("sampling")} onClick={() => setActiveTab("sampling")}>
            Journal Entry Sampling
          </button>
          <button className={tabClasses("je-testing")} onClick={() => setActiveTab("je-testing")}>
            JE Testing Report
          </button>
        </div>

        {/* Tab 1: Sampling */}
        {activeTab === "sampling" && (
          <div className="space-y-6">
            <div className="rounded-xl border bg-card shadow-sm p-5 space-y-4">
              <h2 className="text-sm font-semibold">Sampling Parameters</h2>
              <div className="flex flex-wrap items-end gap-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Method</label>
                  <select
                    value={sampleMethod}
                    onChange={(e) => setSampleMethod(e.target.value)}
                    className="rounded-lg border px-3 py-2 text-sm"
                  >
                    <option value="random">Random</option>
                    <option value="monetary_unit">Monetary Unit</option>
                    <option value="stratified">Stratified</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Sample Size (1–200)</label>
                  <input
                    type="number"
                    min={1}
                    max={200}
                    value={sampleSize}
                    onChange={(e) => setSampleSize(e.target.value)}
                    className="rounded-lg border px-3 py-2 text-sm w-24"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Seed</label>
                  <input
                    type="number"
                    value={sampleSeed}
                    onChange={(e) => setSampleSeed(e.target.value)}
                    className="rounded-lg border px-3 py-2 text-sm w-24"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">From (optional)</label>
                  <input
                    type="date"
                    value={sampleFrom}
                    onChange={(e) => setSampleFrom(e.target.value)}
                    className="rounded-lg border px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">To (optional)</label>
                  <input
                    type="date"
                    value={sampleTo}
                    onChange={(e) => setSampleTo(e.target.value)}
                    className="rounded-lg border px-3 py-2 text-sm"
                  />
                </div>
                <button
                  onClick={() => { void runSampling(); }}
                  disabled={sampleLoading}
                  className="rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                >
                  {sampleLoading ? "Sampling…" : "Draw Sample"}
                </button>
              </div>
              {sampleError && (
                <p className="text-sm text-destructive">{sampleError}</p>
              )}
            </div>

            {sampleResults !== null && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-muted-foreground">
                    {sampleResults.length} entries sampled
                  </p>
                  <button
                    onClick={() => exportCsv(sampleResults)}
                    className="rounded-lg border px-4 py-2 text-sm font-medium text-muted-foreground hover:bg-muted transition-colors"
                  >
                    Export CSV
                  </button>
                </div>
                <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
                  <SampleTable items={sampleResults} />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: JE Testing */}
        {activeTab === "je-testing" && (
          <div className="space-y-6">
            <div className="rounded-xl border bg-card shadow-sm p-5">
              <h2 className="text-sm font-semibold mb-4">Report Date Range</h2>
              <div className="flex flex-wrap items-end gap-4">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">From</label>
                  <input
                    type="date"
                    value={jeFrom}
                    onChange={(e) => setJeFrom(e.target.value)}
                    className="rounded-lg border px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">To</label>
                  <input
                    type="date"
                    value={jeTo}
                    onChange={(e) => setJeTo(e.target.value)}
                    className="rounded-lg border px-3 py-2 text-sm"
                  />
                </div>
                <button
                  onClick={() => { void runJeTesting(); }}
                  disabled={jeLoading}
                  className="rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                >
                  {jeLoading ? "Running…" : "Run Report"}
                </button>
              </div>
              {jeError && (
                <p className="mt-3 text-sm text-destructive">{jeError}</p>
              )}
            </div>

            {jeReport && (
              <div className="space-y-3">
                <CollapsibleSection title="Cutoff Entries" items={jeReport.cutoff_entries} />
                <CollapsibleSection title="Weekend / Holiday Posts" items={jeReport.weekend_holiday_posts} />
                <CollapsibleSection title="Round Number Entries" items={jeReport.round_number_entries} />
                <CollapsibleSection title="Top 20 Largest Entries" items={jeReport.large_entries} />
                <CollapsibleSection title="Same-Day Reversals" items={jeReport.reversed_same_day} />
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
