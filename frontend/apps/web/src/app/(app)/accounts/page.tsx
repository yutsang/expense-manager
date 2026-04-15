"use client";

import { useEffect, useState, type ReactNode } from "react";
import { accountsApi, type Account } from "@/lib/api";
import { PageHeader } from "@/components/page-header";

const TYPE_COLORS: Record<string, string> = {
  asset: "bg-blue-100 text-blue-800",
  liability: "bg-orange-100 text-orange-800",
  equity: "bg-purple-100 text-purple-800",
  revenue: "bg-green-100 text-green-800",
  expense: "bg-red-100 text-red-800",
};

function Badge({ type }: { type: string }) {
  const cls = TYPE_COLORS[type] ?? "bg-gray-100 text-gray-800";
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${cls}`}>
      {type}
    </span>
  );
}

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await accountsApi.list(includeInactive);
      setAccounts(res.items);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load accounts");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [includeInactive]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSave(id: string) {
    try {
      await accountsApi.update(id, { name: editName });
      setEditingId(null);
      await load();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Update failed");
    }
  }

  async function handleArchive(id: string, code: string) {
    if (!confirm(`Archive account ${code}? This cannot be undone if it has journal lines.`)) return;
    try {
      await accountsApi.archive(id);
      await load();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Archive failed");
    }
  }

  // Build a simple tree view — indent child accounts under their parents
  const byId = new Map(accounts.map((a) => [a.id, a]));
  const roots = accounts.filter((a) => !a.parent_id);
  const children = new Map<string, Account[]>();
  for (const a of accounts) {
    if (a.parent_id) {
      const list = children.get(a.parent_id) ?? [];
      list.push(a);
      children.set(a.parent_id, list);
    }
  }

  function renderRow(account: Account, depth = 0): ReactNode {
    const isEditing = editingId === account.id;
    const kids = children.get(account.id) ?? [];
    return (
      <>
        <tr key={account.id} className={account.is_active ? "" : "opacity-50"}>
          <td className="px-4 py-2 font-mono text-sm text-muted-foreground">
            <span style={{ paddingLeft: depth * 16 }}>{account.code}</span>
          </td>
          <td className="px-4 py-2 text-sm">
            {isEditing ? (
              <input
                className="w-full rounded border px-2 py-1 text-sm"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSave(account.id);
                  if (e.key === "Escape") setEditingId(null);
                }}
                autoFocus
              />
            ) : (
              account.name
            )}
          </td>
          <td className="px-4 py-2">
            <Badge type={account.type} />
          </td>
          <td className="px-4 py-2 text-sm text-muted-foreground">{account.normal_balance}</td>
          <td className="px-4 py-2 text-sm text-muted-foreground">
            {account.is_system && (
              <span className="rounded bg-gray-100 px-1.5 py-0.5 text-xs">system</span>
            )}
          </td>
          <td className="px-4 py-2">
            {!account.is_system && (
              <div className="flex items-center gap-2">
                {isEditing ? (
                  <>
                    <button
                      onClick={() => handleSave(account.id)}
                      className="text-xs text-green-600 hover:underline"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="text-xs text-muted-foreground hover:underline"
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => {
                        setEditingId(account.id);
                        setEditName(account.name);
                      }}
                      className="text-xs text-blue-600 hover:underline"
                    >
                      Edit
                    </button>
                    {account.is_active && (
                      <button
                        onClick={() => handleArchive(account.id, account.code)}
                        className="text-xs text-red-500 hover:underline"
                      >
                        Archive
                      </button>
                    )}
                  </>
                )}
              </div>
            )}
          </td>
        </tr>
        {kids.map((child) => renderRow(child, depth + 1))}
      </>
    );
  }

  const headerActions = (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={includeInactive}
        onChange={(e) => setIncludeInactive(e.target.checked)}
      />
      Show inactive
    </label>
  );

  return (
    <>
      <PageHeader
        title="Chart of Accounts"
        subtitle={`${accounts.length} account${accounts.length !== 1 ? "s" : ""}`}
        actions={headerActions}
      />
    <div className="mx-auto max-w-7xl px-6 py-6">

      {error && (
        <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          Loading accounts…
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b bg-muted/40 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-3">Code</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Normal Balance</th>
                <th className="px-4 py-3">Flags</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {roots.map((account) => renderRow(account))}
            </tbody>
          </table>
        </div>
      )}
    </div>
    </>
  );
}
