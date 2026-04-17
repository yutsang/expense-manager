"use client";

import { showToast } from "@/lib/toast";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { type Receipt, receiptsApi } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";

function fmt(amount: string | null, currency: string | null) {
  if (!amount || !currency) return amount ?? "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(parseFloat(amount));
}

function fileSizeLabel(kb: number): string {
  if (kb < 1024) return `${kb} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-600",
  processing: "bg-yellow-100 text-yellow-700",
  done: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

export default function ReceiptsPage() {
  const router = useRouter();
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [selected, setSelected] = useState<Receipt | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await receiptsApi.list();
      setReceipts(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load receipts");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleUpload = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const receipt = await receiptsApi.upload(file);
      setSelected(receipt);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void handleUpload(file);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) void handleUpload(file);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this receipt?")) return;
    try {
      await receiptsApi.delete(id);
      if (selected?.id === id) setSelected(null);
      await load();
    } catch (e) {
      showToast("error", "Operation failed", e instanceof Error ? e.message : String(e));
    }
  };

  const createBillFromReceipt = (receipt: Receipt) => {
    const params = new URLSearchParams();
    if (receipt.ocr_vendor) params.set("vendor", receipt.ocr_vendor);
    if (receipt.ocr_date) params.set("issue_date", receipt.ocr_date);
    if (receipt.ocr_currency) params.set("currency", receipt.ocr_currency);
    if (receipt.ocr_total) params.set("total", receipt.ocr_total);
    router.push(`/bills?${params.toString()}`);
  };

  return (
    <>
      <PageHeader
        title="Receipts"
        subtitle="Upload receipts to auto-extract bill data via AI"
      />
      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">

        {/* Upload area */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`
            flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 cursor-pointer transition-colors
            ${dragging ? "border-indigo-500 bg-indigo-50" : "border-muted-foreground/30 hover:border-indigo-400 hover:bg-muted/30"}
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,application/pdf"
            className="hidden"
            onChange={handleFileChange}
          />
          {uploading ? (
            <div className="flex flex-col items-center gap-2 text-indigo-600">
              <div className="h-8 w-8 animate-spin rounded-full border-4 border-indigo-600 border-t-transparent" />
              <p className="text-sm font-medium">Uploading and running OCR…</p>
            </div>
          ) : (
            <>
              <svg className="mb-3 h-10 w-10 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
              </svg>
              <p className="text-sm font-semibold text-foreground">Drag & drop a receipt, or click to browse</p>
              <p className="mt-1 text-xs text-muted-foreground">Supports JPEG, PNG, GIF, WebP, PDF — max 10 MB</p>
            </>
          )}
        </div>

        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}

        {/* OCR result card */}
        {selected && selected.status === "done" && (
          <div className="rounded-xl border bg-card p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold">OCR Result — {selected.filename}</h3>
              <button
                onClick={() => setSelected(null)}
                className="rounded p-1 text-muted-foreground hover:bg-muted"
              >
                ✕
              </button>
            </div>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              {[
                { label: "Vendor", value: selected.ocr_vendor ?? "—" },
                { label: "Date", value: selected.ocr_date ?? "—" },
                { label: "Currency", value: selected.ocr_currency ?? "—" },
                { label: "Total", value: fmt(selected.ocr_total, selected.ocr_currency) },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-lg border bg-muted/20 p-3">
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="mt-0.5 text-sm font-semibold">{value}</p>
                </div>
              ))}
            </div>
            {selected.ocr_raw.line_items && selected.ocr_raw.line_items.length > 0 && (
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Line Items</p>
                <table className="w-full text-sm">
                  <thead className="border-b">
                    <tr className="text-xs text-muted-foreground">
                      <th className="pb-1 text-left font-medium">Description</th>
                      <th className="pb-1 text-right font-medium">Qty</th>
                      <th className="pb-1 text-right font-medium">Unit Price</th>
                      <th className="pb-1 text-right font-medium">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {selected.ocr_raw.line_items.map((line, i) => (
                      <tr key={i}>
                        <td className="py-1">{line.description ?? "—"}</td>
                        <td className="py-1 text-right tabular-nums">{line.quantity ?? "—"}</td>
                        <td className="py-1 text-right tabular-nums">{line.unit_price ?? "—"}</td>
                        <td className="py-1 text-right font-mono tabular-nums">{line.amount ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="flex justify-end">
              <button
                onClick={() => createBillFromReceipt(selected)}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors"
              >
                Create Bill from Receipt
              </button>
            </div>
          </div>
        )}

        {/* Recent receipts table */}
        <div>
          <h3 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">Recent Receipts</h3>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : receipts.length === 0 ? (
            <div className="rounded-xl border bg-card p-10 text-center">
              <p className="text-muted-foreground">No receipts yet. Upload one above.</p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
              <table className="w-full text-sm">
                <thead className="border-b bg-muted/40">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">File</th>
                    <th className="px-4 py-3 text-left font-medium">Vendor</th>
                    <th className="px-4 py-3 text-left font-medium">Date</th>
                    <th className="px-4 py-3 text-right font-medium">Total</th>
                    <th className="px-4 py-3 text-left font-medium">Status</th>
                    <th className="px-4 py-3 text-left font-medium">Bill</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {receipts.map((r) => (
                    <tr
                      key={r.id}
                      className="hover:bg-muted/20 cursor-pointer"
                      onClick={() => setSelected(r)}
                    >
                      <td className="px-4 py-3">
                        <div>
                          <p className="font-medium truncate max-w-[180px]">{r.filename}</p>
                          <p className="text-xs text-muted-foreground">{fileSizeLabel(r.file_size_kb)}</p>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{r.ocr_vendor ?? "—"}</td>
                      <td className="px-4 py-3 text-muted-foreground">{r.ocr_date ?? "—"}</td>
                      <td className="px-4 py-3 text-right font-mono tabular-nums">
                        {fmt(r.ocr_total, r.ocr_currency)}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[r.status] ?? "bg-gray-100 text-gray-600"}`}
                        >
                          {r.status}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {r.linked_bill_id ? (
                          <span className="text-xs text-green-600 font-medium">Linked</span>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => { void handleDelete(r.id); }}
                          className="text-xs text-muted-foreground hover:text-red-600 transition-colors"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
