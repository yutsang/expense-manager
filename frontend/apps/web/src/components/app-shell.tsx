"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/accounts", label: "Chart of Accounts" },
  { href: "/journals", label: "Journal Entries" },
  { href: "/reports/trial-balance", label: "Trial Balance" },
  { href: "/reports/general-ledger", label: "General Ledger" },
];

function NavItem({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathname === href || pathname.startsWith(href + "/");
  return (
    <li>
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
    </li>
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
          <ul className="space-y-1">
            {NAV_ITEMS.map((item) => (
              <NavItem key={item.href} {...item} />
            ))}
          </ul>
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
}
