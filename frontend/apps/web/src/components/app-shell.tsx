"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const NAV_ITEMS = [
  { group: null, href: "/dashboard", label: "Dashboard" },
  { group: "Ledger", href: "/accounts", label: "Chart of Accounts" },
  { group: "Ledger", href: "/journals", label: "Journal Entries" },
  { group: "Sales", href: "/contacts", label: "Contacts" },
  { group: "Sales", href: "/invoices", label: "Invoices" },
  { group: "Purchases", href: "/bills", label: "Bills" },
  { group: "Reports", href: "/reports/pl", label: "Profit & Loss" },
  { group: "Reports", href: "/reports/balance-sheet", label: "Balance Sheet" },
  { group: "Reports", href: "/reports/cash-flow", label: "Cash Flow" },
  { group: "Reports", href: "/reports/ar-aging", label: "AR Aging" },
  { group: "Reports", href: "/reports/ap-aging", label: "AP Aging" },
  { group: "Reports", href: "/reports/trial-balance", label: "Trial Balance" },
  { group: "Reports", href: "/reports/general-ledger", label: "General Ledger" },
];

function NavItem({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href || pathname.startsWith(href + "/");
  return (
    <Link
      href={href}
      className={
        "block rounded-md px-3 py-2 text-sm font-medium transition-colors " +
        (active
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-muted hover:text-foreground")
      }
    >
      {label}
    </Link>
  );
}

export function AppShell({ children }: { readonly children: ReactNode }) {
  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 border-r bg-card px-3 py-4">
        <div className="mb-6 px-3">
          <span className="text-lg font-bold tracking-tight">Aegis ERP</span>
        </div>
        <nav>
          <ul className="space-y-0.5">
            {NAV_ITEMS.map((item, i) => {
              const prevGroup = i > 0 ? NAV_ITEMS[i - 1]!.group : undefined;
              const showHeader = item.group && item.group !== prevGroup;
              return (
                <li key={item.href}>
                  {showHeader && (
                    <p className="mt-4 mb-1 px-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                      {item.group}
                    </p>
                  )}
                  <NavItem href={item.href} label={item.label} />
                </li>
              );
            })}
          </ul>
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
