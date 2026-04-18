"use client";

import { useRef, useState } from "react";
import { showToast } from "@/lib/toast";
import { BASE } from "@/lib/api";
import { getTenantIdOrRedirect } from "@/lib/get-tenant-id";

interface CsvImportExportProps {
  entityType: string;
  templateUrl: string;
  importUrl: string;
  onImportComplete: () => void;
}

export function CsvImportExport({
  entityType,
  templateUrl,
  importUrl,
  onImportComplete,
}: CsvImportExportProps) {
  const [open, setOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleMouseEnter() {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setOpen(true);
  }

  function handleMouseLeave() {
    timeoutRef.current = setTimeout(() => setOpen(false), 150);
  }

  function getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {};
    try {
      headers["X-Tenant-ID"] = getTenantIdOrRedirect();
    } catch {
      // tenant redirect will handle it
    }
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("aegis_token");
      if (token) headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  }

  async function handleDownloadTemplate() {
    setOpen(false);
    try {
      const res = await fetch(`${BASE}${templateUrl}`, {
        method: "GET",
        headers: getHeaders(),
        credentials: "include",
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => res.statusText);
        showToast("error", "Template download failed", detail);
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${entityType}-template.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      showToast("error", "Template download failed", e instanceof Error ? e.message : String(e));
    }
  }

  function handleImportClick() {
    setOpen(false);
    fileInputRef.current?.click();
  }

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    // Reset the input so the same file can be selected again
    e.target.value = "";

    setImporting(true);
    try {
      const form = new FormData();
      form.append("file", file);

      const res = await fetch(`${BASE}${importUrl}`, {
        method: "POST",
        headers: getHeaders(),
        credentials: "include",
        body: form,
      });

      if (!res.ok) {
        const detail = await res.text().catch(() => res.statusText);
        showToast("error", "Import failed", detail);
        return;
      }

      const result = await res.json();
      const imported = result.imported ?? result.created ?? 0;
      const skipped = result.skipped ?? result.skipped_duplicates ?? 0;
      const failed = result.failed ?? result.errors?.length ?? 0;

      if (failed > 0 && imported > 0) {
        showToast(
          "warning",
          `Imported ${imported}, ${failed} failed`,
          "Check console for details"
        );
        if (result.errors) console.warn("CSV import errors:", result.errors);
      } else if (failed > 0 && imported === 0) {
        showToast("error", "Import failed", `All ${failed} record(s) failed`);
        if (result.errors) console.error("CSV import errors:", result.errors);
      } else {
        const parts = [`Imported ${imported} record${imported !== 1 ? "s" : ""}`];
        if (skipped > 0) parts.push(`${skipped} skipped`);
        showToast("success", parts.join(", "));
      }

      onImportComplete();
    } catch (e) {
      showToast("error", "Import failed", e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(false);
    }
  }

  return (
    <div
      className="relative print:hidden"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={importing}
        className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors disabled:opacity-50"
      >
        {importing ? (
          <span className="h-4 w-4 rounded-full border-2 border-current border-t-transparent animate-spin" />
        ) : (
          <svg
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
            />
          </svg>
        )}
        CSV
      </button>

      {open && !importing && (
        <div className="absolute right-0 top-full z-20 mt-1 w-44 rounded-lg border bg-card shadow-lg">
          <button
            type="button"
            onClick={() => void handleDownloadTemplate()}
            className="w-full px-4 py-2 text-left text-sm hover:bg-muted transition-colors rounded-t-lg"
          >
            Download Template
          </button>
          <button
            type="button"
            onClick={handleImportClick}
            className="w-full px-4 py-2 text-left text-sm hover:bg-muted transition-colors rounded-b-lg"
          >
            Import CSV
          </button>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => void handleFileSelected(e)}
      />
    </div>
  );
}
