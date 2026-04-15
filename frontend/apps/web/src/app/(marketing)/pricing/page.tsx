import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Pricing — Aegis ERP",
  description: "Simple, transparent pricing. Start free, scale as you grow.",
};

const PLANS = [
  {
    name: "Starter",
    price: "$0",
    period: "forever",
    description: "For freelancers and solo operators.",
    features: [
      "1 entity / 1 user",
      "Unlimited journal entries",
      "Chart of accounts (US/AU/UK templates)",
      "Trial balance + general ledger",
      "100 AI assistant messages/month",
      "Community support",
    ],
    cta: "Start free",
    href: "/login",
    highlight: false,
  },
  {
    name: "Growth",
    price: "$49",
    period: "per month",
    description: "For small businesses with a bookkeeper.",
    features: [
      "Up to 5 users",
      "3 entities",
      "Invoices, bills, bank reconciliation",
      "Unlimited AI assistant",
      "Audit trail + auditor workspace",
      "Mobile app (iOS + Android)",
      "Email support",
    ],
    cta: "Start 14-day trial",
    href: "/login",
    highlight: true,
  },
  {
    name: "Scale",
    price: "$149",
    period: "per month",
    description: "For controllers and multi-entity groups.",
    features: [
      "Unlimited users",
      "Unlimited entities",
      "All Growth features",
      "API access + webhooks",
      "SOC 2 evidence packages",
      "Priority support + onboarding",
      "Custom CoA templates",
    ],
    cta: "Contact sales",
    href: "/login",
    highlight: false,
  },
];

const FAQS = [
  {
    q: "Is there a free trial?",
    a: "The Starter plan is free forever. Growth and Scale plans have a 14-day free trial — no credit card required.",
  },
  {
    q: "What is an entity?",
    a: "An entity is one company/organisation with its own chart of accounts and general ledger. Multi-entity groups (e.g. a holding company + subsidiaries) need the Growth or Scale plan.",
  },
  {
    q: "How does the AI assistant work?",
    a: "The AI (powered by Claude) reads your live ledger via secure read-only tools. It can answer questions, draft journal entries, and flag anomalies — but always requires your approval before posting anything.",
  },
  {
    q: "Can I export my data?",
    a: "Yes. All plans include CSV and PDF exports. Scale includes machine-readable audit evidence packages (XBRL-ready). Your data is yours and portable at any time.",
  },
];

export default function PricingPage() {
  return (
    <div className="px-6 py-24">
      <div className="mx-auto max-w-6xl">
        {/* Header */}
        <div className="mb-16 text-center">
          <h1 className="mb-4 text-4xl font-bold tracking-tight md:text-5xl">
            Simple, honest pricing
          </h1>
          <p className="mx-auto max-w-xl text-lg text-muted-foreground">
            No per-transaction fees. No surprise overages. Start free and upgrade when you need to.
          </p>
        </div>

        {/* Plans */}
        <div className="mb-24 grid gap-6 md:grid-cols-3">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={`relative rounded-2xl border p-8 shadow-sm ${
                plan.highlight
                  ? "border-primary bg-primary/5 shadow-primary/10 shadow-lg"
                  : "bg-card"
              }`}
            >
              {plan.highlight && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-4 py-1 text-xs font-semibold text-primary-foreground">
                  Most popular
                </div>
              )}
              <div className="mb-6">
                <h2 className="mb-1 text-lg font-bold">{plan.name}</h2>
                <p className="text-sm text-muted-foreground">{plan.description}</p>
              </div>
              <div className="mb-6">
                <span className="text-4xl font-bold">{plan.price}</span>
                <span className="ml-1 text-sm text-muted-foreground">/{plan.period}</span>
              </div>
              <ul className="mb-8 space-y-3">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm">
                    <span className="mt-0.5 text-green-500">✓</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <Link
                href={plan.href}
                className={`block w-full rounded-lg px-4 py-2.5 text-center text-sm font-semibold transition-colors ${
                  plan.highlight
                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : "border hover:bg-muted"
                }`}
              >
                {plan.cta}
              </Link>
            </div>
          ))}
        </div>

        {/* FAQ */}
        <div className="mx-auto max-w-2xl">
          <h2 className="mb-8 text-center text-2xl font-bold">Frequently asked</h2>
          <div className="space-y-6">
            {FAQS.map((faq) => (
              <div key={faq.q} className="rounded-lg border bg-card p-6">
                <h3 className="mb-2 font-semibold">{faq.q}</h3>
                <p className="text-sm text-muted-foreground">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
