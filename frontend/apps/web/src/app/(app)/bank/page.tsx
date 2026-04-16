"use client";

import { useEffect, useRef, useState } from "react";
import {
  bankReconciliationApi,
  accountsApi,
  type BankAccount,
  type BankTransaction,
  type BankReconciliation,
  type BankImportResult,
  type Account,
} from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";

function fmt(amount: string) {
  const n = parseFloat(amount);
  const abs = Math.abs(n);
  const str = new Intl.NumberFormat("en-AU", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(abs);
  return n < 0 ? `(${str})` : str;
}

type Tab = "transactions" | "reconciliations";

export default function BankPage() {
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [coaAccounts, setCoaAccounts] = useState<Account[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create bank account form
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    name: "",
    bank_name: "",
    account_number: "",
    currency: "AUD",
    coa_account_id: "",
  });
  const [creating, setCreating] = useState(false);

  // Transactions
  const [tab, setTab] = useState<Tab>("transactions");
  const [transactions, setTransactions] = useState<BankTransaction[]>([]);
  const [txLoading, setTxLoading] = useState(false);

  // Add transaction form
  const [showAddTx, setShowAddTx] = useState(false);
  const [txForm, setTxForm] = useState({ date: "", description: "", reference: "", amount: "" });
  const [addingTx, setAddingTx] = useState(false);

  // Reconciliations
  const [reconciliations, setReconciliations] = useState<BankReconciliation[]>([]);
  const [recoLoading, setRecoLoading] = useState(false);
  const [showNewReco, setShowNewReco] = useState(false);
  const [recoForm, setRecoForm] = useState({ reconciliation_date: "", statement_balance: "" });
  const [savingReco, setSavingReco] = useState(false);

  // Import statement
  const [showImport, setShowImport] = useState(false);
  const [importAccountId, setImportAccountId] = useState<string>("");
  const [importCurrency, setImportCurrency] = useState("USD");
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<BankImportResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function loadAccounts() {
    setLoading(true);
    setError(null);
    try {
      const res = await bankReconciliationApi.listAccounts();
      setAccounts(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load bank accounts");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAccounts();
    void accountsApi.list().then((r) => setCoaAccounts(r.items));
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    if (tab === "transactions") {
      setTxLoading(true);
      bankReconciliationApi
        .listTransactions(selectedId)
        .then(setTransactions)
        .catch(() => setTransactions([]))
        .finally(() => setTxLoading(false));
    } else {
      setRecoLoading(true);
      bankReconciliationApi
        .listReconciliations(selectedId)
        .then(setReconciliations)
        .catch(() => setReconciliations([]))
        .finally(() => setRecoLoading(false));
    }
  }, [selectedId, tab]);

  async function handleCreateAccount(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      const payload: Parameters<typeof bankReconciliationApi.createAccount>[0] = {
        name: createForm.name,
        currency: createForm.currency,
        ...(createForm.bank_name ? { bank_name: createForm.bank_name } : {}),
        ...(createForm.account_number ? { account_number: createForm.account_number } : {}),
        ...(createForm.coa_account_id ? { coa_account_id: createForm.coa_account_id } : {}),
      };
      await bankReconciliationApi.createAccount(payload);
      setCreateForm({ name: "", bank_name: "", account_number: "", currency: "AUD", coa_account_id: "" });
      setShowCreate(false);
      await loadAccounts();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Create failed");
    } finally {
      setCreating(false);
    }
  }

  async function handleAddTransaction(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedId) return;
    setAddingTx(true);
    try {
      const payload: Parameters<typeof bankReconciliationApi.createTransaction>[1] = {
        date: txForm.date,
        description: txForm.description,
        amount: txForm.amount,
        ...(txForm.reference ? { reference: txForm.reference } : {}),
      };
      await bankReconciliationApi.createTransaction(selectedId, payload);
      setTxForm({ date: "", description: "", reference: "", amount: "" });
      setShowAddTx(false);
      const res = await bankReconciliationApi.listTransactions(selectedId);
      setTransactions(res);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to add transaction");
    } finally {
      setAddingTx(false);
    }
  }

  async function handleMatch(tx: BankTransaction) {
    if (!window.confirm(`Mark transaction "${tx.description}" as matched?`)) return;
    try {
      await bankReconciliationApi.matchTransaction(tx.id, "manual");
      if (selectedId) {
        const res = await bankReconciliationApi.listTransactions(selectedId);
        setTransactions(res);
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Match failed");
    }
  }

  async function handleNewReconciliation(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedId) return;
    setSavingReco(true);
    try {
      await bankReconciliationApi.createReconciliation(selectedId, {
        statement_balance: recoForm.statement_balance,
        reconciliation_date: recoForm.reconciliation_date,
      });
      setRecoForm({ reconciliation_date: "", statement_balance: "" });
      setShowNewReco(false);
      const res = await bankReconciliationApi.listReconciliations(selectedId);
      setReconciliations(res);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to save reconciliation");
    } finally {
      setSavingReco(false);
    }
  }

  function openImport() {
    setImportAccountId(selectedId ?? (accounts[0]?.id ?? ""));
    setImportCurrency("USD");
    setImportFile(null);
    setImportResult(null);
    setShowImport(true);
  }

  async function handleImport(e: React.FormEvent) {
    e.preventDefault();
    if (!importFile || !importAccountId) return;
    setImporting(true);
    setImportResult(null);
    try {
      const result = await bankReconciliationApi.importStatement(importAccountId, importFile, importCurrency);
      setImportResult(result);
      // Refresh transactions if the imported account is currently selected
      if (importAccountId === selectedId && tab === "transactions") {
        const txns = await bankReconciliationApi.listTransactions(importAccountId);
        setTransactions(txns);
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Import failed");
    } finally {
      setImporting(false);
    }
  }

  const selectedAccount = accounts.find((a) => a.id === selectedId);

  return (
    <>
      <PageHeader
        title="Bank Accounts"
        subtitle="Manage bank accounts and reconciliations"
        actions={
          <div className="flex gap-2">
            <button
              onClick={openImport}
              className="rounded-lg border px-4 py-2 text-sm font-semibold hover:bg-muted"
            >
              Import Statement
            </button>
            <button
              onClick={() => setShowCreate((v) => !v)}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90"
            >
              + New Bank Account
            </button>
          </div>
        }
      />
      <div className="mx-auto max-w-7xl px-6 py-6 space-y-6">
        {error && (
          <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}

        {/* Create form */}
        {showCreate && (
          <div className="rounded-lg border bg-card p-4 shadow-sm">
            <h2 className="mb-4 text-sm font-semibold">New Bank Account</h2>
            <form onSubmit={(e) => void handleCreateAccount(e)} className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Account Name *</label>
                <input
                  required
                  value={createForm.name}
                  onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                  className="w-full rounded-md border px-3 py-1.5 text-sm"
                  placeholder="Main Cheque Account"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Bank Name</label>
                <input
                  value={createForm.bank_name}
                  onChange={(e) => setCreateForm((f) => ({ ...f, bank_name: e.target.value }))}
                  className="w-full rounded-md border px-3 py-1.5 text-sm"
                  placeholder="Commonwealth Bank"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Account Number</label>
                <input
                  value={createForm.account_number}
                  onChange={(e) => setCreateForm((f) => ({ ...f, account_number: e.target.value }))}
                  className="w-full rounded-md border px-3 py-1.5 text-sm"
                  placeholder="06-2134 123456789"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Currency *</label>
                <input
                  required
                  value={createForm.currency}
                  onChange={(e) => setCreateForm((f) => ({ ...f, currency: e.target.value }))}
                  className="w-full rounded-md border px-3 py-1.5 text-sm"
                  placeholder="AUD"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Linked CoA Account</label>
                <select
                  value={createForm.coa_account_id}
                  onChange={(e) => setCreateForm((f) => ({ ...f, coa_account_id: e.target.value }))}
                  className="w-full rounded-md border px-3 py-1.5 text-sm"
                >
                  <option value="">— None —</option>
                  {coaAccounts.filter((a) => a.type === "asset").map((a) => (
                    <option key={a.id} value={a.id}>{a.code} — {a.name}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-2 flex gap-2 sm:col-span-3">
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                >
                  {creating ? "Creating…" : "Create"}
                </button>
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="rounded-md border px-4 py-1.5 text-sm font-medium hover:bg-muted"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Import Statement modal */}
        {showImport && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
            <div className="w-full max-w-md rounded-xl border bg-card p-6 shadow-xl">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-base font-semibold">Import Bank Statement</h2>
                <button
                  onClick={() => setShowImport(false)}
                  className="text-muted-foreground hover:text-foreground text-lg leading-none"
                >
                  ×
                </button>
              </div>

              {importResult ? (
                <div className="space-y-3">
                  <div className="rounded-md bg-green-50 p-3 text-sm text-green-800">
                    {importResult.imported} transaction{importResult.imported !== 1 ? "s" : ""} imported
                    {importResult.skipped_duplicates > 0 && `, ${importResult.skipped_duplicates} duplicate${importResult.skipped_duplicates !== 1 ? "s" : ""} skipped`}
                    .
                  </div>
                  {importResult.errors.length > 0 && (
                    <div className="rounded-md bg-yellow-50 p-3 text-xs text-yellow-800 space-y-1">
                      <p className="font-medium">{importResult.errors.length} row error{importResult.errors.length !== 1 ? "s" : ""}:</p>
                      <ul className="list-disc pl-4 space-y-0.5">
                        {importResult.errors.slice(0, 10).map((err, i) => (
                          <li key={i}>{err}</li>
                        ))}
                        {importResult.errors.length > 10 && <li>…and {importResult.errors.length - 10} more</li>}
                      </ul>
                    </div>
                  )}
                  <button
                    onClick={() => setShowImport(false)}
                    className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                  >
                    Done
                  </button>
                </div>
              ) : (
                <form onSubmit={(e) => void handleImport(e)} className="space-y-4">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">Bank Account *</label>
                    <select
                      required
                      value={importAccountId}
                      onChange={(e) => setImportAccountId(e.target.value)}
                      className="w-full rounded-md border px-3 py-2 text-sm"
                    >
                      <option value="">— Select account —</option>
                      {accounts.map((acc) => (
                        <option key={acc.id} value={acc.id}>
                          {acc.name}{acc.bank_name ? ` (${acc.bank_name})` : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">Currency *</label>
                    <select
                      value={importCurrency}
                      onChange={(e) => setImportCurrency(e.target.value)}
                      className="w-full rounded-md border px-3 py-2 text-sm"
                    >
                      {["USD", "HKD", "EUR", "GBP", "AUD", "SGD"].map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">CSV File *</label>
                    <div
                      onClick={() => fileInputRef.current?.click()}
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => {
                        e.preventDefault();
                        const f = e.dataTransfer.files[0];
                        if (f) setImportFile(f);
                      }}
                      className="flex cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed px-4 py-6 text-sm text-muted-foreground hover:border-primary hover:text-foreground transition-colors"
                    >
                      {importFile ? (
                        <span className="text-foreground font-medium">{importFile.name}</span>
                      ) : (
                        <>
                          <span>Drop a .csv file here, or click to browse</span>
                          <span className="mt-1 text-xs">Supports single-amount and debit/credit column formats</span>
                        </>
                      )}
                    </div>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".csv"
                      className="hidden"
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) setImportFile(f);
                      }}
                    />
                  </div>
                  <div className="flex gap-2 pt-1">
                    <button
                      type="submit"
                      disabled={importing || !importFile || !importAccountId}
                      className="flex-1 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                    >
                      {importing ? "Importing…" : "Import"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowImport(false)}
                      className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-muted"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Account list */}
          <div className="lg:col-span-1">
            <div className="rounded-lg border bg-card shadow-sm overflow-hidden">
              <div className="border-b bg-muted/20 px-4 py-3">
                <h2 className="text-sm font-semibold">Bank Accounts</h2>
              </div>
              {loading ? (
                <div className="py-8 text-center text-sm text-muted-foreground">Loading…</div>
              ) : accounts.length === 0 ? (
                <div className="py-8 text-center text-sm text-muted-foreground">No bank accounts yet.</div>
              ) : (
                <ul className="divide-y">
                  {accounts.map((acc) => (
                    <li key={acc.id}>
                      <button
                        onClick={() => { setSelectedId(acc.id); setTab("transactions"); }}
                        className={`w-full px-4 py-3 text-left hover:bg-muted/30 transition-colors ${selectedId === acc.id ? "bg-primary/5 border-l-2 border-primary" : ""}`}
                      >
                        <p className="text-sm font-medium">{acc.name}</p>
                        {acc.bank_name && (
                          <p className="text-xs text-muted-foreground">{acc.bank_name}</p>
                        )}
                        <div className="mt-1 flex items-center justify-between">
                          <span className="text-xs text-muted-foreground">{acc.currency}</span>
                          {acc.last_reconciled_date && (
                            <span className="text-xs text-muted-foreground">
                              Last reconciled {acc.last_reconciled_date}
                            </span>
                          )}
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* Selected account detail */}
          <div className="lg:col-span-2">
            {!selectedAccount ? (
              <div className="flex h-64 items-center justify-center rounded-lg border bg-card text-sm text-muted-foreground">
                Select a bank account to view details
              </div>
            ) : (
              <div className="rounded-lg border bg-card shadow-sm overflow-hidden">
                {/* Tabs */}
                <div className="flex border-b">
                  {(["transactions", "reconciliations"] as Tab[]).map((t) => (
                    <button
                      key={t}
                      onClick={() => setTab(t)}
                      className={`px-4 py-3 text-sm font-medium capitalize transition-colors ${
                        tab === t
                          ? "border-b-2 border-primary text-primary"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {t}
                    </button>
                  ))}
                  <div className="flex-1" />
                  {tab === "transactions" && (
                    <button
                      onClick={() => setShowAddTx((v) => !v)}
                      className="mr-3 my-2 rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                    >
                      + Add Transaction
                    </button>
                  )}
                  {tab === "reconciliations" && (
                    <button
                      onClick={() => setShowNewReco((v) => !v)}
                      className="mr-3 my-2 rounded-md bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                    >
                      New Reconciliation
                    </button>
                  )}
                </div>

                {/* Add transaction form */}
                {tab === "transactions" && showAddTx && (
                  <div className="border-b bg-muted/10 p-4">
                    <form onSubmit={(e) => void handleAddTransaction(e)} className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">Date *</label>
                        <input
                          required
                          type="date"
                          value={txForm.date}
                          onChange={(e) => setTxForm((f) => ({ ...f, date: e.target.value }))}
                          className="w-full rounded border px-2 py-1.5 text-sm"
                        />
                      </div>
                      <div className="col-span-2">
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">Description *</label>
                        <input
                          required
                          value={txForm.description}
                          onChange={(e) => setTxForm((f) => ({ ...f, description: e.target.value }))}
                          className="w-full rounded border px-2 py-1.5 text-sm"
                          placeholder="Bank transfer"
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">Amount *</label>
                        <input
                          required
                          type="number"
                          step="0.01"
                          value={txForm.amount}
                          onChange={(e) => setTxForm((f) => ({ ...f, amount: e.target.value }))}
                          className="w-full rounded border px-2 py-1.5 text-sm"
                          placeholder="100.00"
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">Reference</label>
                        <input
                          value={txForm.reference}
                          onChange={(e) => setTxForm((f) => ({ ...f, reference: e.target.value }))}
                          className="w-full rounded border px-2 py-1.5 text-sm"
                          placeholder="REF-001"
                        />
                      </div>
                      <div className="col-span-2 flex gap-2 sm:col-span-4">
                        <button
                          type="submit"
                          disabled={addingTx}
                          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                        >
                          {addingTx ? "Adding…" : "Add"}
                        </button>
                        <button
                          type="button"
                          onClick={() => setShowAddTx(false)}
                          className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted"
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  </div>
                )}

                {/* New reconciliation form */}
                {tab === "reconciliations" && showNewReco && (
                  <div className="border-b bg-muted/10 p-4">
                    <form onSubmit={(e) => void handleNewReconciliation(e)} className="flex flex-wrap items-end gap-3">
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">Statement Date *</label>
                        <input
                          required
                          type="date"
                          value={recoForm.reconciliation_date}
                          onChange={(e) => setRecoForm((f) => ({ ...f, reconciliation_date: e.target.value }))}
                          className="rounded border px-2 py-1.5 text-sm"
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs font-medium text-muted-foreground">Statement Closing Balance *</label>
                        <input
                          required
                          type="number"
                          step="0.01"
                          value={recoForm.statement_balance}
                          onChange={(e) => setRecoForm((f) => ({ ...f, statement_balance: e.target.value }))}
                          className="rounded border px-2 py-1.5 text-sm"
                          placeholder="10000.00"
                        />
                      </div>
                      <div className="flex gap-2">
                        <button
                          type="submit"
                          disabled={savingReco}
                          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
                        >
                          {savingReco ? "Saving…" : "Save"}
                        </button>
                        <button
                          type="button"
                          onClick={() => setShowNewReco(false)}
                          className="rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-muted"
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  </div>
                )}

                {/* Transactions tab */}
                {tab === "transactions" && (
                  txLoading ? (
                    <div className="py-8 text-center text-sm text-muted-foreground">Loading transactions…</div>
                  ) : transactions.length === 0 ? (
                    <div className="py-8 text-center text-sm text-muted-foreground">No transactions found.</div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="border-b bg-muted/30">
                          <tr>
                            <th className="px-4 py-2 text-left font-medium text-muted-foreground">Date</th>
                            <th className="px-4 py-2 text-left font-medium text-muted-foreground">Description</th>
                            <th className="px-4 py-2 text-left font-medium text-muted-foreground">Reference</th>
                            <th className="px-4 py-2 text-right font-medium text-muted-foreground">Amount</th>
                            <th className="px-4 py-2 text-center font-medium text-muted-foreground">Status</th>
                            <th className="px-4 py-2 text-center font-medium text-muted-foreground">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {transactions.map((tx) => (
                            <tr key={tx.id} className="hover:bg-muted/10">
                              <td className="px-4 py-2.5 text-muted-foreground">{tx.date}</td>
                              <td className="px-4 py-2.5">{tx.description}</td>
                              <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">{tx.reference ?? "—"}</td>
                              <td className={`px-4 py-2.5 text-right font-mono tabular-nums ${parseFloat(tx.amount) < 0 ? "text-red-600" : "text-green-700"}`}>
                                {fmt(tx.amount)}
                              </td>
                              <td className="px-4 py-2.5 text-center">
                                {tx.is_reconciled ? (
                                  <span className="inline-flex items-center gap-1 text-xs font-medium text-green-600">
                                    <span>✓</span> Matched
                                  </span>
                                ) : (
                                  <StatusBadge status="draft" />
                                )}
                              </td>
                              <td className="px-4 py-2.5 text-center">
                                {!tx.is_reconciled && (
                                  <button
                                    onClick={() => void handleMatch(tx)}
                                    className="text-xs text-blue-600 hover:underline"
                                  >
                                    Match
                                  </button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                )}

                {/* Reconciliations tab */}
                {tab === "reconciliations" && (
                  recoLoading ? (
                    <div className="py-8 text-center text-sm text-muted-foreground">Loading reconciliations…</div>
                  ) : reconciliations.length === 0 ? (
                    <div className="py-8 text-center text-sm text-muted-foreground">No reconciliations yet.</div>
                  ) : (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="border-b bg-muted/30">
                          <tr>
                            <th className="px-4 py-2 text-left font-medium text-muted-foreground">Date</th>
                            <th className="px-4 py-2 text-right font-medium text-muted-foreground">Statement Balance</th>
                            <th className="px-4 py-2 text-right font-medium text-muted-foreground">Book Balance</th>
                            <th className="px-4 py-2 text-right font-medium text-muted-foreground">Difference</th>
                            <th className="px-4 py-2 text-center font-medium text-muted-foreground">Status</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {reconciliations.map((reco) => (
                            <tr key={reco.id} className="hover:bg-muted/10">
                              <td className="px-4 py-2.5 text-muted-foreground">{reco.reconciliation_date}</td>
                              <td className="px-4 py-2.5 text-right font-mono tabular-nums">{fmt(reco.statement_balance)}</td>
                              <td className="px-4 py-2.5 text-right font-mono tabular-nums">{fmt(reco.book_balance)}</td>
                              <td className={`px-4 py-2.5 text-right font-mono tabular-nums ${parseFloat(reco.difference) !== 0 ? "text-red-600" : "text-green-600"}`}>
                                {fmt(reco.difference)}
                              </td>
                              <td className="px-4 py-2.5 text-center">
                                <StatusBadge status={reco.status} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
