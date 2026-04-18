"use client";

import { useRef, useState } from "react";
import { Download } from "lucide-react";
import {
  exportToCSV,
  exportToExcel,
  triggerPrintPDF,
  type ExportColumn,
} from "@/lib/export-utils";

interface ExportDropdownProps {
  data: Record<string, unknown>[];
  filename: string;
  columns: ExportColumn[];
}

export function ExportDropdown({ data, filename, columns }: ExportDropdownProps) {
  const [open, setOpen] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleMouseEnter() {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setOpen(true);
  }

  function handleMouseLeave() {
    timeoutRef.current = setTimeout(() => setOpen(false), 150);
  }

  function handleExport(format: "csv" | "excel" | "pdf") {
    setOpen(false);
    switch (format) {
      case "csv":
        exportToCSV(data, filename, columns);
        break;
      case "excel":
        exportToExcel(data, filename, columns);
        break;
      case "pdf":
        triggerPrintPDF();
        break;
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
        className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
      >
        <Download className="h-4 w-4" />
        Export
      </button>

      {open && (
        <div className="absolute right-0 top-full z-20 mt-1 w-40 rounded-lg border bg-card shadow-lg">
          <button
            type="button"
            onClick={() => handleExport("excel")}
            className="w-full px-4 py-2 text-left text-sm hover:bg-muted transition-colors rounded-t-lg"
          >
            Excel (.xls)
          </button>
          <button
            type="button"
            onClick={() => handleExport("csv")}
            className="w-full px-4 py-2 text-left text-sm hover:bg-muted transition-colors"
          >
            CSV (.csv)
          </button>
          <button
            type="button"
            onClick={() => handleExport("pdf")}
            className="w-full px-4 py-2 text-left text-sm hover:bg-muted transition-colors rounded-b-lg"
          >
            PDF (Print)
          </button>
        </div>
      )}
    </div>
  );
}
