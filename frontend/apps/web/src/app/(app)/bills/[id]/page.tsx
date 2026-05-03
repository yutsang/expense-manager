"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, FileText } from "lucide-react";
import {
  type Account,
  type Bill,
  type Contact,
  accountsApi,
  billsApi,
  contactsApi,
} from "@/lib/api";
import { showToast } from "@/lib/toast";
import { StatusBadge } from "@/components/status-badge";
import { safeFmt } from "@/lib/money-safe";

function fmt(amount: string, currency = "USD") {
  return safeFmt(amount, currency);
}

function Field({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={mono ? "font-mono text-sm break-all" : "text-sm font-medium"}>
        {value || <span className="text-muted-foreground">—</span>}
      </dd>
    </div>
  );
}

export default function BillDetailPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const [bill, setBill] = useState<Bill | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);

  const load = async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const [b, c, a] = await Promise.all([
        billsApi.get(id),
        contactsApi.list({ contact_type: "supplier" }),
        accountsApi.list(),
      ]);
      setBill(b);
      setContacts(c.items);
      setAccounts(a.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load bill");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const contactName = (cid: string) =>
    contacts.find((c) => c.id === cid)?.name ?? cid;
  const accountName = (aid: string) =>
    accounts.find((a) => a.id === aid)
      ? `${accounts.find((a) => a.id === aid)?.code} ${accounts.find((a) => a.id === aid)?.name}`
      : aid;

  const submit = async () => {
    if (!bill) return;
    setActing(true);
    try {
      await billsApi.submit(bill.id);
      await load();
      showToast("success", `Bill ${bill.number} submitted for approval`);
    } catch (e) {
      showToast("error", "Submit failed", String(e));
    } finally {
      setActing(false);
    }
  };

  const approve = async () => {
    if (!bill) return;
    setActing(true);
    try {
      await billsApi.approve(bill.id);
      await load();
      showToast("success", `Bill ${bill.number} approved`);
    } catch (e) {
      showToast("error", "Approve failed", String(e));
    } finally {
      setActing(false);
    }
  };

  const voidBill = async () => {
    if (!bill) return;
    if (!confirm(`Void ${bill.number}? This cannot be undone.`)) return;
    setActing(true);
    try {
      await billsApi.void(bill.id);
      showToast("success", `Bill ${bill.number} voided`);
      router.push("/bills");
    } catch (e) {
      showToast("error", "Void failed", String(e));
      setActing(false);
    }
  };

  return (
    <div className="space-y-6">
      <Link
        href="/bills"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to bills
      </Link>

      {loading && (
        <div className="rounded-xl border bg-card p-8 text-center text-sm text-muted-foreground">
          Loading…
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-400">
          {error}
        </div>
      )}

      {bill && (
        <>
          <div className="flex items-start gap-3">
            <FileText className="h-7 w-7 text-blue-500 shrink-0 mt-1" />
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-3 flex-wrap">
                <h1 className="text-2xl font-semibold tracking-tight font-mono">
                  {bill.number}
                </h1>
                <StatusBadge status={bill.status} />
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                Bill from <span className="font-medium text-foreground">{contactName(bill.contact_id)}</span>
                {bill.supplier_reference ? (
                  <> · supplier ref {bill.supplier_reference}</>
                ) : null}
              </p>
            </div>

            <div className="flex gap-2 shrink-0">
              {bill.status === "draft" && (
                <button
                  onClick={() => void submit()}
                  disabled={acting}
                  className="rounded-lg border bg-yellow-500 text-white px-3 py-2 text-sm font-medium hover:bg-yellow-600 disabled:opacity-60"
                >
                  Submit for approval
                </button>
              )}
              {bill.status === "awaiting_approval" && (
                <button
                  onClick={() => void approve()}
                  disabled={acting}
                  className="rounded-lg border bg-blue-500 text-white px-3 py-2 text-sm font-medium hover:bg-blue-600 disabled:opacity-60"
                >
                  Approve
                </button>
              )}
              {bill.status !== "void" && bill.status !== "paid" && (
                <button
                  onClick={() => void voidBill()}
                  disabled={acting}
                  className="rounded-lg border px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 disabled:opacity-60"
                >
                  Void
                </button>
              )}
            </div>
          </div>

          {/* Summary fields */}
          <div className="rounded-xl border bg-card p-4">
            <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-3 text-sm">
              <Field label="Issue date" value={bill.issue_date} />
              <Field label="Due date" value={bill.due_date} />
              <Field label="Currency" value={bill.currency} />
              <Field label="Subtotal" value={fmt(bill.subtotal, bill.currency)} mono />
              <Field label="Tax total" value={fmt(bill.tax_total, bill.currency)} mono />
              <Field label="Total" value={fmt(bill.total, bill.currency)} mono />
              <Field label="Amount due" value={fmt(bill.amount_due, bill.currency)} mono />
              <Field label="Created" value={new Date(bill.created_at).toLocaleString()} />
              <Field label="Bill ID" value={bill.id} mono />
            </dl>
          </div>

          {/* Line items */}
          <div className="rounded-xl border overflow-hidden">
            <div className="px-4 py-3 border-b bg-muted/30">
              <h2 className="text-sm font-semibold">Line items ({bill.lines.length})</h2>
            </div>
            <table className="w-full text-sm">
              <thead className="bg-muted/20">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide w-12">#</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">Account</th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wide">Description</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wide">Qty</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wide">Unit price</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wide">Tax</th>
                  <th className="px-4 py-2 text-right text-xs font-semibold text-muted-foreground uppercase tracking-wide">Amount</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {bill.lines.map((line) => (
                  <tr key={line.id}>
                    <td className="px-4 py-3 text-muted-foreground">{line.line_no}</td>
                    <td className="px-4 py-3">{accountName(line.account_id)}</td>
                    <td className="px-4 py-3">{line.description ?? "—"}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">{line.quantity}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">
                      {fmt(line.unit_price, bill.currency)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">
                      {fmt(line.tax_amount, bill.currency)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums font-medium">
                      {fmt(line.line_amount, bill.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot className="bg-muted/20 border-t">
                <tr>
                  <td colSpan={5} />
                  <td className="px-4 py-2 text-right text-xs text-muted-foreground">Subtotal</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">
                    {fmt(bill.subtotal, bill.currency)}
                  </td>
                </tr>
                <tr>
                  <td colSpan={5} />
                  <td className="px-4 py-2 text-right text-xs text-muted-foreground">Tax</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums">
                    {fmt(bill.tax_total, bill.currency)}
                  </td>
                </tr>
                <tr>
                  <td colSpan={5} />
                  <td className="px-4 py-2 text-right text-sm font-semibold">Total</td>
                  <td className="px-4 py-2 text-right font-mono tabular-nums font-semibold">
                    {fmt(bill.total, bill.currency)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
