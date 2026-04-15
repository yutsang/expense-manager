"use client";

import { PageHeader } from "@/components/page-header";

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Manage your organisation and account"
      />
    <div className="mx-auto max-w-7xl px-6 py-6 space-y-8 max-w-2xl">

      {/* Section 1: Organisation */}
      <section className="rounded-xl border bg-card shadow-sm">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div>
            <h2 className="font-semibold">Organisation</h2>
            <p className="text-xs text-muted-foreground">Details about your company</p>
          </div>
          <div className="relative group">
            <button
              disabled
              className="rounded-lg border px-3 py-1.5 text-sm font-medium text-muted-foreground cursor-not-allowed opacity-60"
            >
              Edit
            </button>
            <div className="absolute right-0 top-9 z-10 hidden group-hover:block whitespace-nowrap rounded-md border bg-card px-3 py-1.5 text-xs text-muted-foreground shadow-md">
              Coming soon
            </div>
          </div>
        </div>
        <dl className="divide-y px-6">
          <div className="flex items-center justify-between py-4">
            <dt className="text-sm font-medium text-muted-foreground">Organisation name</dt>
            <dd className="text-sm font-medium">Aegis Demo Co.</dd>
          </div>
          <div className="flex items-center justify-between py-4">
            <dt className="text-sm font-medium text-muted-foreground">Country</dt>
            <dd className="text-sm">United States</dd>
          </div>
          <div className="flex items-center justify-between py-4">
            <dt className="text-sm font-medium text-muted-foreground">Functional currency</dt>
            <dd className="text-sm">USD — US Dollar</dd>
          </div>
          <div className="flex items-center justify-between py-4">
            <dt className="text-sm font-medium text-muted-foreground">Fiscal year start</dt>
            <dd className="text-sm">1 January</dd>
          </div>
        </dl>
      </section>

      {/* Section 2: Your profile */}
      <section className="rounded-xl border bg-card shadow-sm">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div>
            <h2 className="font-semibold">Your profile</h2>
            <p className="text-xs text-muted-foreground">Your personal account details</p>
          </div>
        </div>
        <dl className="divide-y px-6">
          <div className="flex items-center justify-between py-4">
            <dt className="text-sm font-medium text-muted-foreground">Display name</dt>
            <dd className="text-sm font-medium">Admin User</dd>
          </div>
          <div className="flex items-center justify-between py-4">
            <dt className="text-sm font-medium text-muted-foreground">Email</dt>
            <dd className="text-sm text-muted-foreground">admin@aegis.io</dd>
          </div>
          <div className="flex items-center justify-between py-4">
            <dt className="text-sm font-medium text-muted-foreground">Password</dt>
            <dd className="text-sm">
              <div className="relative group inline-block">
                <button
                  disabled
                  className="rounded-lg border px-3 py-1.5 text-sm font-medium text-muted-foreground cursor-not-allowed opacity-60"
                >
                  Change password
                </button>
                <div className="absolute right-0 top-9 z-10 hidden group-hover:block whitespace-nowrap rounded-md border bg-card px-3 py-1.5 text-xs text-muted-foreground shadow-md">
                  Coming soon
                </div>
              </div>
            </dd>
          </div>
        </dl>
      </section>

      {/* Section 3: Danger zone */}
      <section className="rounded-xl border border-destructive/40 bg-card shadow-sm">
        <div className="border-b border-destructive/40 px-6 py-4">
          <h2 className="font-semibold text-destructive">Danger zone</h2>
          <p className="text-xs text-muted-foreground">Irreversible and destructive actions</p>
        </div>
        <div className="flex items-center justify-between px-6 py-4">
          <div>
            <p className="text-sm font-medium">Delete organisation</p>
            <p className="text-xs text-muted-foreground">
              Permanently delete this organisation and all its data. This action cannot be undone.
            </p>
          </div>
          <div className="relative group">
            <button
              disabled
              className="rounded-lg border border-destructive/50 bg-destructive/5 px-3 py-1.5 text-sm font-medium text-destructive cursor-not-allowed opacity-60"
            >
              Delete organisation
            </button>
            <div className="absolute right-0 top-9 z-10 hidden group-hover:block whitespace-nowrap rounded-md border bg-card px-3 py-1.5 text-xs text-muted-foreground shadow-md">
              Contact support to delete your organisation
            </div>
          </div>
        </div>
      </section>
    </div>
    </>
  );
}
