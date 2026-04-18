"use client";

import { useState, useEffect, useCallback } from "react";
import { PageHeader } from "@/components/page-header";
import { Settings, User, Bell, Check, AlertCircle } from "lucide-react";
import { settingsApi } from "@/lib/api";
import type { TenantSettings } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────

interface OrgSettings {
  org_name: string;
  country: string;
  functional_currency: string;
  fiscal_year_start_month: number;
}

interface ProfileSettings {
  display_name: string;
  email: string;
}

interface NotificationSettings {
  email_overdue_invoices: boolean;
  daily_sanctions_scan: boolean;
  period_close_reminders: boolean;
  kyc_expiry_alerts: boolean;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const CURRENCIES = ["AUD", "USD", "GBP", "EUR", "HKD", "SGD", "JPY"] as const;
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
] as const;
const COUNTRIES = [
  "Australia", "Canada", "France", "Germany", "Hong Kong", "Japan",
  "New Zealand", "Singapore", "United Kingdom", "United States",
] as const;

const LS_ORG = "aegis_org_settings";
const LS_NOTIF = "aegis_notif_settings";

const DEFAULT_ORG: OrgSettings = {
  org_name: "My Organisation",
  country: "Australia",
  functional_currency: "AUD",
  fiscal_year_start_month: 7,
};

const DEFAULT_NOTIF: NotificationSettings = {
  email_overdue_invoices: true,
  daily_sanctions_scan: false,
  period_close_reminders: true,
  kyc_expiry_alerts: true,
};

// ── Toast ─────────────────────────────────────────────────────────────────────

function Toast({ message, variant = "success", onDismiss }: { message: string; variant?: "success" | "error"; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 3000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-lg bg-gray-900 px-4 py-3 text-sm text-white shadow-lg dark:bg-gray-100 dark:text-gray-900">
      {variant === "success" ? (
        <Check className="h-4 w-4 shrink-0 text-green-400 dark:text-green-600" />
      ) : (
        <AlertCircle className="h-4 w-4 shrink-0 text-red-400 dark:text-red-600" />
      )}
      {message}
    </div>
  );
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

type Tab = "organisation" | "profile" | "notifications";

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "organisation",  label: "Organisation",  icon: Settings },
  { id: "profile",       label: "Profile",        icon: User },
  { id: "notifications", label: "Notifications",  icon: Bell },
];

// ── Shared form primitives ────────────────────────────────────────────────────

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
      {children}
    </label>
  );
}

function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { className, ...rest } = props;
  return (
    <input
      {...rest}
      className={
        "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm placeholder-gray-400 " +
        "focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 " +
        "disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-500 " +
        "dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:placeholder-gray-500 " +
        "dark:focus:border-indigo-400 dark:focus:ring-indigo-400/20 " +
        (className ?? "")
      }
    />
  );
}

function SelectInput(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  const { className, ...rest } = props;
  return (
    <select
      {...rest}
      className={
        "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 shadow-sm " +
        "focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 " +
        "disabled:cursor-not-allowed disabled:bg-gray-50 " +
        "dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 " +
        "dark:focus:border-indigo-400 " +
        (className ?? "")
      }
    />
  );
}

function SaveButton({ loading, onClick }: { loading?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-60 transition-colors"
    >
      {loading && (
        <span className="h-3.5 w-3.5 rounded-full border-2 border-white border-t-transparent animate-spin" />
      )}
      Save changes
    </button>
  );
}

// ── Organisation tab ──────────────────────────────────────────────────────────

function OrganisationTab({ onSaved, onError }: { onSaved: () => void; onError: (msg: string) => void }) {
  const [form, setForm] = useState<OrgSettings>(DEFAULT_ORG);
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await settingsApi.get();
        if (!cancelled) {
          setForm({
            org_name: data.org_name,
            country: data.country,
            functional_currency: data.functional_currency,
            fiscal_year_start_month: data.fiscal_year_start_month,
          });
          // Write-through cache
          localStorage.setItem(LS_ORG, JSON.stringify({
            org_name: data.org_name,
            country: data.country,
            functional_currency: data.functional_currency,
            fiscal_year_start_month: data.fiscal_year_start_month,
          }));
        }
      } catch {
        // Fall back to localStorage
        try {
          const raw = localStorage.getItem(LS_ORG);
          if (raw && !cancelled) setForm(JSON.parse(raw) as OrgSettings);
        } catch {
          // use defaults
        }
      } finally {
        if (!cancelled) setFetching(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  function patch<K extends keyof OrgSettings>(key: K, value: OrgSettings[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setLoading(true);
    try {
      const updated = await settingsApi.update({
        org_name: form.org_name,
        country: form.country,
        functional_currency: form.functional_currency,
        fiscal_year_start_month: form.fiscal_year_start_month,
      });
      // Write-through cache
      localStorage.setItem(LS_ORG, JSON.stringify({
        org_name: updated.org_name,
        country: updated.country,
        functional_currency: updated.functional_currency,
        fiscal_year_start_month: updated.fiscal_year_start_month,
      }));
      onSaved();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setLoading(false);
    }
  }

  if (fetching) {
    return (
      <div className="flex items-center justify-center py-12">
        <span className="h-5 w-5 rounded-full border-2 border-indigo-600 border-t-transparent animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
          Organisation Settings
        </h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          These settings apply to your entire organisation.
        </p>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900 space-y-5">
        <div>
          <FieldLabel>Organisation name</FieldLabel>
          <TextInput
            type="text"
            value={form.org_name}
            onChange={(e) => patch("org_name", e.target.value)}
            placeholder="Acme Corp"
          />
        </div>

        <div>
          <FieldLabel>Country</FieldLabel>
          <SelectInput
            value={form.country}
            onChange={(e) => patch("country", e.target.value)}
          >
            {COUNTRIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </SelectInput>
        </div>

        <div>
          <FieldLabel>Functional currency</FieldLabel>
          <SelectInput
            value={form.functional_currency}
            onChange={(e) => patch("functional_currency", e.target.value)}
          >
            {CURRENCIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </SelectInput>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            The base currency for your general ledger. Changing this after data entry requires a full revaluation.
          </p>
        </div>

        <div>
          <FieldLabel>Fiscal year start month</FieldLabel>
          <SelectInput
            value={String(form.fiscal_year_start_month)}
            onChange={(e) => patch("fiscal_year_start_month", Number(e.target.value))}
          >
            {MONTHS.map((m, i) => (
              <option key={m} value={String(i + 1)}>{m}</option>
            ))}
          </SelectInput>
        </div>
      </div>

      <div className="flex justify-end">
        <SaveButton loading={loading} onClick={handleSave} />
      </div>
    </div>
  );
}

// ── Profile tab ───────────────────────────────────────────────────────────────

function ProfileTab({ onSaved }: { onSaved: () => void }) {
  const [profile, setProfile] = useState<ProfileSettings>({ display_name: "", email: "" });
  const [pw, setPw] = useState({ current: "", next: "", confirm: "" });
  const [profileLoading, setProfileLoading] = useState(false);
  const [pwLoading, setPwLoading] = useState(false);
  const [pwError, setPwError] = useState<string | null>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("aegis-auth");
      if (raw) {
        const parsed = JSON.parse(raw) as {
          state?: { user?: { email?: string; display_name?: string } };
        };
        const user = parsed?.state?.user;
        if (user) {
          setProfile({
            display_name: user.display_name ?? "",
            email: user.email ?? "",
          });
        }
      }
    } catch {
      // ignore
    }
  }, []);

  function handleSaveProfile() {
    setProfileLoading(true);
    setTimeout(() => {
      setProfileLoading(false);
      onSaved();
    }, 300);
  }

  function handleChangePassword() {
    setPwError(null);
    if (!pw.current) { setPwError("Current password is required."); return; }
    if (pw.next.length < 8) { setPwError("New password must be at least 8 characters."); return; }
    if (pw.next !== pw.confirm) { setPwError("New passwords do not match."); return; }
    setPwLoading(true);
    setTimeout(() => {
      setPwLoading(false);
      setPw({ current: "", next: "", confirm: "" });
      onSaved();
    }, 300);
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Profile</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Manage your personal details and password.
        </p>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900 space-y-5">
        <div>
          <FieldLabel>Display name</FieldLabel>
          <TextInput
            type="text"
            value={profile.display_name}
            onChange={(e) => setProfile((p) => ({ ...p, display_name: e.target.value }))}
            placeholder="Your name"
          />
        </div>
        <div>
          <FieldLabel>Email address</FieldLabel>
          <TextInput type="email" value={profile.email} disabled />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Email is managed by your authentication provider and cannot be changed here.
          </p>
        </div>
        <div className="flex justify-end">
          <SaveButton loading={profileLoading} onClick={handleSaveProfile} />
        </div>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900 space-y-5">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Change password</h3>

        <div>
          <FieldLabel>Current password</FieldLabel>
          <TextInput
            type="password"
            value={pw.current}
            onChange={(e) => setPw((p) => ({ ...p, current: e.target.value }))}
            autoComplete="current-password"
          />
        </div>
        <div>
          <FieldLabel>New password</FieldLabel>
          <TextInput
            type="password"
            value={pw.next}
            onChange={(e) => setPw((p) => ({ ...p, next: e.target.value }))}
            autoComplete="new-password"
          />
        </div>
        <div>
          <FieldLabel>Confirm new password</FieldLabel>
          <TextInput
            type="password"
            value={pw.confirm}
            onChange={(e) => setPw((p) => ({ ...p, confirm: e.target.value }))}
            autoComplete="new-password"
          />
        </div>

        {pwError && (
          <p className="text-sm text-red-600 dark:text-red-400">{pwError}</p>
        )}

        <div className="flex justify-end">
          <SaveButton loading={pwLoading} onClick={handleChangePassword} />
        </div>
      </div>
    </div>
  );
}

// ── Notifications tab ─────────────────────────────────────────────────────────

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: string;
}

function Toggle({ checked, onChange, label, description }: ToggleProps) {
  return (
    <div className="flex items-start gap-4 py-4 border-b border-gray-100 dark:border-gray-800 last:border-0">
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={
          "relative mt-0.5 inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 " +
          (checked ? "bg-indigo-600" : "bg-gray-200 dark:bg-gray-700")
        }
      >
        <span
          className={
            "pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out " +
            (checked ? "translate-x-4" : "translate-x-0")
          }
        />
      </button>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{label}</p>
        {description && (
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{description}</p>
        )}
      </div>
    </div>
  );
}

function NotificationsTab({ onSaved, onError }: { onSaved: () => void; onError: (msg: string) => void }) {
  const [settings, setSettings] = useState<NotificationSettings>(DEFAULT_NOTIF);
  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await settingsApi.get();
        if (!cancelled) {
          const prefs = data.notification_prefs || {};
          setSettings({
            email_overdue_invoices: prefs.email_overdue_invoices ?? DEFAULT_NOTIF.email_overdue_invoices,
            daily_sanctions_scan: prefs.daily_sanctions_scan ?? DEFAULT_NOTIF.daily_sanctions_scan,
            period_close_reminders: prefs.period_close_reminders ?? DEFAULT_NOTIF.period_close_reminders,
            kyc_expiry_alerts: prefs.kyc_expiry_alerts ?? DEFAULT_NOTIF.kyc_expiry_alerts,
          });
          // Write-through cache
          localStorage.setItem(LS_NOTIF, JSON.stringify(prefs));
        }
      } catch {
        // Fall back to localStorage
        try {
          const raw = localStorage.getItem(LS_NOTIF);
          if (raw && !cancelled) setSettings(JSON.parse(raw) as NotificationSettings);
        } catch {
          // use defaults
        }
      } finally {
        if (!cancelled) setFetching(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  function patch<K extends keyof NotificationSettings>(key: K, value: NotificationSettings[K]) {
    setSettings((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setLoading(true);
    try {
      const updated = await settingsApi.update({
        notification_prefs: settings as unknown as Record<string, boolean>,
      });
      // Write-through cache
      localStorage.setItem(LS_NOTIF, JSON.stringify(updated.notification_prefs));
      onSaved();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Failed to save notification settings");
    } finally {
      setLoading(false);
    }
  }

  if (fetching) {
    return (
      <div className="flex items-center justify-center py-12">
        <span className="h-5 w-5 rounded-full border-2 border-indigo-600 border-t-transparent animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Notifications</h2>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Choose which alerts you receive by email.
        </p>
      </div>

      <div className="rounded-xl border border-gray-200 bg-white px-6 shadow-sm dark:border-gray-800 dark:bg-gray-900">
        <Toggle
          checked={settings.email_overdue_invoices}
          onChange={(v) => patch("email_overdue_invoices", v)}
          label="Email reminders for overdue invoices"
          description="Receive a daily digest of invoices that are past their due date."
        />
        <Toggle
          checked={settings.daily_sanctions_scan}
          onChange={(v) => patch("daily_sanctions_scan", v)}
          label="Daily sanctions scan alerts"
          description="Get notified when new potential sanctions matches are detected."
        />
        <Toggle
          checked={settings.period_close_reminders}
          onChange={(v) => patch("period_close_reminders", v)}
          label="Period close reminders"
          description="Reminder emails as the current accounting period approaches its close date."
        />
        <Toggle
          checked={settings.kyc_expiry_alerts}
          onChange={(v) => patch("kyc_expiry_alerts", v)}
          label="KYC expiry alerts"
          description="Alerts when contact identity documents are due to expire within 60 days."
        />
      </div>

      <div className="flex justify-end">
        <SaveButton loading={loading} onClick={handleSave} />
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("organisation");
  const [toast, setToast] = useState<{ message: string; variant: "success" | "error" } | null>(null);

  const showSaved = useCallback(() => setToast({ message: "Settings saved", variant: "success" }), []);
  const showError = useCallback((msg: string) => setToast({ message: msg, variant: "error" }), []);
  const dismissToast = useCallback(() => setToast(null), []);

  return (
    <>
      <PageHeader title="Settings" subtitle="Manage your organisation and account preferences" />

      <div className="mx-auto max-w-3xl px-6 py-6">
        {/* Tab bar */}
        <div className="flex gap-1 rounded-lg border border-gray-200 bg-gray-100 p-1 dark:border-gray-800 dark:bg-gray-800/50 mb-6">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={
                "flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors " +
                (activeTab === id
                  ? "bg-white text-indigo-700 shadow-sm dark:bg-gray-900 dark:text-indigo-400"
                  : "text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200")
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </button>
          ))}
        </div>

        {activeTab === "organisation" && <OrganisationTab onSaved={showSaved} onError={showError} />}
        {activeTab === "profile" && <ProfileTab onSaved={showSaved} />}
        {activeTab === "notifications" && <NotificationsTab onSaved={showSaved} onError={showError} />}
      </div>

      {toast && <Toast message={toast.message} variant={toast.variant} onDismiss={dismissToast} />}
    </>
  );
}
