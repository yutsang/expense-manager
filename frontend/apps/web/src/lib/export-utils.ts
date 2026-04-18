/**
 * Report export utilities — CSV, Excel (.xls via HTML table), and PDF (print).
 *
 * CSV: builds a UTF-8 BOM string and triggers a download.
 * Excel: builds an HTML table, wraps it in an .xls-compatible blob, triggers download.
 *        (No external dependency required — Excel/Sheets can open HTML tables saved as .xls.)
 * PDF: delegates to window.print() with a @media print stylesheet that hides chrome.
 */

export type ExportColumn = {
  key: string;
  header: string;
};

// ── CSV ──────────────────────────────────────────────────────────────────────

function escapeCsvCell(value: string): string {
  if (value.includes('"') || value.includes(",") || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

export function exportToCSV(
  data: Record<string, unknown>[],
  filename: string,
  columns: ExportColumn[],
): void {
  const header = columns.map((c) => escapeCsvCell(c.header)).join(",");
  const rows = data.map((row) =>
    columns.map((c) => escapeCsvCell(String(row[c.key] ?? ""))).join(","),
  );

  // UTF-8 BOM so Excel opens with correct encoding
  const BOM = "\uFEFF";
  const csv = BOM + [header, ...rows].join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });

  triggerDownload(blob, filename.endsWith(".csv") ? filename : `${filename}.csv`);
}

// ── Excel (HTML table as .xls) ───────────────────────────────────────────────

export function exportToExcel(
  data: Record<string, unknown>[],
  filename: string,
  columns: ExportColumn[],
): void {
  const headerCells = columns.map((c) => `<th>${escapeHtml(c.header)}</th>`).join("");
  const bodyRows = data
    .map((row) => {
      const cells = columns
        .map((c) => `<td>${escapeHtml(String(row[c.key] ?? ""))}</td>`)
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");

  const html = `
    <html xmlns:o="urn:schemas-microsoft-com:office:office"
          xmlns:x="urn:schemas-microsoft-com:office:excel"
          xmlns="http://www.w3.org/TR/REC-html40">
    <head><meta charset="utf-8" /></head>
    <body>
      <table border="1">
        <thead><tr>${headerCells}</tr></thead>
        <tbody>${bodyRows}</tbody>
      </table>
    </body>
    </html>`;

  const blob = new Blob([html], { type: "application/vnd.ms-excel;charset=utf-8;" });
  triggerDownload(blob, filename.endsWith(".xls") ? filename : `${filename}.xls`);
}

// ── PDF (print) ──────────────────────────────────────────────────────────────

export function triggerPrintPDF(): void {
  window.print();
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
