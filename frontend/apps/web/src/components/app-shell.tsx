"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import {
  LayoutDashboard,
  BookOpen,
  BookMarked,
  Users,
  FileText,
  Receipt,
  CreditCard,
  TrendingUp,
  Scale,
  ArrowLeftRight,
  Clock,
  Calculator,
  Table2,
  Menu,
  X,
  ChevronDown,
  Settings,
  LogOut,
  HelpCircle,
} from "lucide-react";
import { authApi } from "@/lib/api";

const NAV_ITEMS = [
  { group: null,        href: "/dashboard",              label: "Dashboard",        icon: LayoutDashboard },
  { group: "Ledger",    href: "/accounts",               label: "Chart of Accounts",icon: BookOpen },
  { group: "Ledger",    href: "/journals",               label: "Journal Entries",  icon: BookMarked },
  { group: "Sales",     href: "/contacts",               label: "Contacts",         icon: Users },
  { group: "Sales",     href: "/invoices",               label: "Invoices",         icon: FileText },
  { group: "Purchases", href: "/bills",                  label: "Bills",            icon: Receipt },
  { group: "Purchases", href: "/payments",               label: "Payments",         icon: CreditCard },
  { group: "Reports",   href: "/reports/pl",             label: "Profit & Loss",    icon: TrendingUp },
  { group: "Reports",   href: "/reports/balance-sheet",  label: "Balance Sheet",    icon: Scale },
  { group: "Reports",   href: "/reports/cash-flow",      label: "Cash Flow",        icon: ArrowLeftRight },
  { group: "Reports",   href: "/reports/ar-aging",       label: "AR Aging",         icon: Clock },
  { group: "Reports",   href: "/reports/ap-aging",       label: "AP Aging",         icon: Clock },
  { group: "Reports",   href: "/reports/trial-balance",  label: "Trial Balance",    icon: Calculator },
  { group: "Reports",   href: "/reports/general-ledger", label: "General Ledger",   icon: Table2 },
];

function NavItem({
  href,
  label,
  icon: Icon,
  onClick,
}: {
  href: string;
  label: string;
  icon: React.ElementType;
  onClick?: (() => void) | undefined;
}) {
  const pathname = usePathname();
  const active = pathname === href || pathname.startsWith(href + "/");
  return (
    <Link
      href={href}
      {...(onClick ? { onClick } : {})}
      className={
        "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors " +
        (active
          ? "bg-primary/10 text-primary"
          : "text-muted-foreground hover:bg-muted hover:text-foreground")
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      {label}
    </Link>
  );
}

function UserMenu() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function handleSignOut() {
    try { await authApi.logout(); } catch { /* ignore */ }
    router.push("/login");
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted transition-colors"
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
          A
        </div>
        <span className="hidden sm:block text-sm font-medium text-foreground">Admin</span>
        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute right-0 mt-1 w-48 rounded-lg border bg-card shadow-md z-50 py-1">
          <div className="border-b px-3 py-2">
            <p className="text-sm font-medium">Admin User</p>
            <p className="text-xs text-muted-foreground">admin@aegis.io</p>
          </div>
          <Link
            href="/settings"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors"
          >
            <Settings className="h-4 w-4 text-muted-foreground" />
            Settings
          </Link>
          <Link
            href="/help"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted transition-colors"
          >
            <HelpCircle className="h-4 w-4 text-muted-foreground" />
            Help & docs
          </Link>
          <div className="border-t mt-1">
            <button
              onClick={() => { void handleSignOut(); }}
              className="flex w-full items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-muted transition-colors"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function SidebarContent({ onNavClick }: { onNavClick?: (() => void) | undefined }) {
  return (
    <div className="flex h-full flex-col bg-card">
      {/* Logo */}
      <div className="flex h-14 items-center px-4 border-b shrink-0">
        <Link href="/dashboard" className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground text-xs font-bold">
            A
          </div>
          <span className="text-base font-bold tracking-tight">Aegis ERP</span>
        </Link>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item, i) => {
            const prevGroup = i > 0 ? NAV_ITEMS[i - 1]!.group : undefined;
            const showHeader = item.group && item.group !== prevGroup;
            return (
              <li key={item.href}>
                {showHeader && (
                  <p className="mt-4 mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                    {item.group}
                  </p>
                )}
                <NavItem
                  href={item.href}
                  label={item.label}
                  icon={item.icon}
                  onClick={onNavClick}
                />
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Footer */}
      <div className="border-t px-2 py-2 shrink-0">
        <Link
          href="/settings"
          className="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          <Settings className="h-4 w-4 shrink-0" />
          Settings
        </Link>
      </div>
    </div>
  );
}

export function AppShell({ children }: { readonly children: ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={
          "fixed inset-y-0 left-0 z-50 w-56 border-r shadow-sm transition-transform duration-200 md:static md:translate-x-0 md:shadow-none " +
          (sidebarOpen ? "translate-x-0" : "-translate-x-full")
        }
      >
        {/* Mobile close button */}
        <button
          onClick={() => setSidebarOpen(false)}
          className="absolute right-2 top-2 rounded-md p-1.5 text-muted-foreground hover:bg-muted md:hidden"
        >
          <X className="h-4 w-4" />
        </button>
        <SidebarContent onNavClick={() => setSidebarOpen(false)} />
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-card px-4">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors md:hidden"
            aria-label="Open navigation"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex-1" />
          <UserMenu />
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
