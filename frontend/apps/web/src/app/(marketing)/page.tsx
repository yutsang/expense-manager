import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Aegis ERP — AI-assisted, audit-first accounting",
  description:
    "The accounting platform built for accuracy and auditability. Claude-powered AI that reasons over your ledger, an airtight audit trail, and an offline-first mobile companion.",
  openGraph: {
    title: "Aegis ERP",
    description: "AI-assisted, audit-first accounting for growing businesses.",
    type: "website",
  },
};

const FEATURES = [
  {
    icon: "🔐",
    title: "Audit-first by design",
    body: "Every mutation is logged to a tamper-evident, SHA-256 hash-chained audit trail. Give auditors a scoped workspace and a one-click evidence package — no more zip files of JPEGs.",
  },
  {
    icon: "🤖",
    title: "Claude AI built in",
    body: "Ask your books anything. The AI reasons over your live general ledger, drafts journal entries with citations, flags anomalies, and proposes reconciliation matches. You approve — it never acts unilaterally.",
  },
  {
    icon: "📱",
    title: "Offline-first mobile",
    body: "Capture receipts, approve bills, and review dashboards on iOS or Android — even without a connection. Changes sync deterministically when you're back online.",
  },
  {
    icon: "🌍",
    title: "Multi-currency & multi-entity",
    body: "Full FX rate management, functional-currency revaluation, and a compliant chart of accounts per jurisdiction (US GAAP, AU AASB, UK FRS). One platform for your whole group.",
  },
  {
    icon: "⚖️",
    title: "Double-entry enforced",
    body: "Balanced journals are enforced at three layers: Pydantic, ORM validation, and a Postgres trigger. Money is always NUMERIC — never a float.",
  },
  {
    icon: "🚀",
    title: "API-first",
    body: "Every feature is available through a versioned REST API with cursor-based pagination and OpenAPI spec. Build integrations without workarounds.",
  },
];

const LOGOS = ["Vercel", "Fly.io", "Postgres", "Redis", "Anthropic"];

export default function HomePage() {
  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden bg-gradient-to-b from-primary/5 to-background px-6 py-24 text-center md:py-36">
        <div className="mx-auto max-w-3xl">
          <div className="mb-6 inline-flex items-center rounded-full border bg-background px-4 py-1.5 text-xs font-medium text-muted-foreground shadow-sm">
            Now in early access · AI-powered accounting
          </div>
          <h1 className="mb-6 text-4xl font-bold tracking-tight text-foreground md:text-6xl">
            The books that<br />
            <span className="text-primary">never lie.</span>
          </h1>
          <p className="mx-auto mb-10 max-w-2xl text-lg text-muted-foreground md:text-xl">
            Aegis ERP is a Xero-class accounting platform with a Claude AI assistant that reasons over your live ledger, an airtight audit trail, and an offline-first mobile companion. Correct by construction.
          </p>
          <div className="flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <Link
              href="/login"
              className="w-full rounded-lg bg-primary px-8 py-3 text-base font-semibold text-primary-foreground hover:bg-primary/90 transition-colors sm:w-auto"
            >
              Start free — no card needed
            </Link>
            <Link
              href="/pricing"
              className="w-full rounded-lg border px-8 py-3 text-base font-medium text-foreground hover:bg-muted transition-colors sm:w-auto"
            >
              See pricing
            </Link>
          </div>
        </div>
      </section>

      {/* Social proof logos */}
      <section className="border-y bg-muted/30 py-8">
        <div className="mx-auto max-w-4xl px-6">
          <p className="mb-6 text-center text-xs font-medium uppercase tracking-widest text-muted-foreground">
            Built on battle-tested infrastructure
          </p>
          <div className="flex flex-wrap items-center justify-center gap-8 opacity-60">
            {LOGOS.map((l) => (
              <span key={l} className="text-sm font-semibold text-muted-foreground">{l}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Features grid */}
      <section className="px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <div className="mb-16 text-center">
            <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
              Everything your accountant wants.<br />Everything your auditor needs.
            </h2>
            <p className="mx-auto max-w-xl text-muted-foreground">
              Built for accuracy-first, with AI on top — not AI bolted on later.
            </p>
          </div>
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="rounded-xl border bg-card p-6 shadow-sm">
                <div className="mb-4 text-3xl">{f.icon}</div>
                <h3 className="mb-2 text-base font-semibold">{f.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA band */}
      <section className="bg-primary px-6 py-20 text-center">
        <div className="mx-auto max-w-2xl">
          <h2 className="mb-4 text-3xl font-bold text-primary-foreground md:text-4xl">
            Ready for books that don&apos;t lie?
          </h2>
          <p className="mb-8 text-primary-foreground/80">
            Get started in minutes. No credit card. Cancel any time.
          </p>
          <Link
            href="/login"
            className="inline-block rounded-lg bg-white px-8 py-3 text-base font-semibold text-primary hover:bg-white/90 transition-colors"
          >
            Create your free account
          </Link>
        </div>
      </section>
    </>
  );
}
