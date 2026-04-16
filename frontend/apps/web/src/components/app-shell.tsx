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
  Calendar,
  Percent,
  Landmark,
  Sparkles,
  Shield,
  CheckSquare,
  SlidersHorizontal,
  Package,
  BarChart2,
  Plus,
  Moon,
  Sun,
} from "lucide-react";
import { authApi } from "@/lib/api";

const NAV_ITEMS = [
  { group: "AI",       href: "/assistant",              label: "AI Assistant",     icon: Sparkles },
  { group: "AI",       href: "/assistant/cost",          label: "AI Usage",         icon: BarChart2 },
  { group: null,        href: "/dashboard",              label: "Dashboard",        icon: LayoutDashboard },
  { group: "Ledger",    href: "/accounts",               label: "Chart of Accounts",icon: BookOpen },
  { group: "Ledger",    href: "/journals",               label: "Journal Entries",  icon: BookMarked },
  { group: "Ledger",    href: "/periods",                label: "Periods",          icon: Calendar },
  { group: "Sales",     href: "/contacts",               label: "Contacts",         icon: Users },
  { group: "Sales",     href: "/invoices",               label: "Invoices",         icon: FileText },
  { group: "Purchases", href: "/bills",                  label: "Bills",            icon: Receipt },
  { group: "Purchases", href: "/payments",               label: "Payments",         icon: CreditCard },
  { group: "Purchases", href: "/tax-codes",              label: "Tax Codes",        icon: Percent },
  { group: "Purchases", href: "/bank",                   label: "Bank",             icon: Landmark },
  { group: "Purchases", href: "/expense-claims",         label: "Expense Claims",   icon: Receipt },
  { group: "Reports",   href: "/reports/pl",             label: "Profit & Loss",    icon: TrendingUp },
  { group: "Reports",   href: "/reports/balance-sheet",  label: "Balance Sheet",    icon: Scale },
  { group: "Reports",   href: "/reports/cash-flow",      label: "Cash Flow",        icon: ArrowLeftRight },
  { group: "Reports",   href: "/reports/ar-aging",       label: "AR Aging",         icon: Clock },
  { group: "Reports",   href: "/reports/ap-aging",       label: "AP Aging",         icon: Clock },
  { group: "Reports",   href: "/reports/trial-balance",  label: "Trial Balance",    icon: Calculator },
  { group: "Reports",   href: "/reports/general-ledger", label: "General Ledger",   icon: Table2 },
  { group: "Audit",     href: "/audit/timeline",         label: "Audit Timeline",   icon: Shield },
  { group: "Audit",     href: "/audit/chain",            label: "Chain Verification", icon: CheckSquare },
  { group: "Audit",     href: "/audit/sampling",         label: "Sampling & Testing", icon: SlidersHorizontal },
  { group: "Audit",     href: "/audit/evidence",         label: "Evidence Package",  icon: Package },
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
        "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors relative " +
        (active
          ? "bg-indigo-50 text-indigo-700 font-medium border-l-2 border-indigo-600 dark:bg-indigo-950/40 dark:text-indigo-400 dark:border-indigo-500"
          : "text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100")
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      {label}
    </Link>
  );
}

function NewActionDropdown() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div ref={ref} className="relative px-3 mt-3">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-700 transition-colors dark:bg-indigo-700 dark:hover:bg-indigo-600"
      >
        <Plus className="h-4 w-4" />
        New
        <ChevronDown className="h-3.5 w-3.5 ml-auto" />
      </button>
      {open && (
        <div className="absolute left-3 right-3 mt-1 rounded-lg border bg-white shadow-lg z-50 py-1 dark:bg-gray-900 dark:border-gray-700">
          <Link
            href="/invoices"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800 transition-colors"
          >
            <FileText className="h-4 w-4 text-indigo-500" />
            New Invoice
          </Link>
          <Link
            href="/bills"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800 transition-colors"
          >
            <Receipt className="h-4 w-4 text-indigo-500" />
            New Bill
          </Link>
          <Link
            href="/journals"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800 transition-colors"
          >
            <BookMarked className="h-4 w-4 text-indigo-500" />
            New Journal
          </Link>
        </div>
      )}
    </div>
  );
}

function DarkModeToggle() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    setIsDark(stored === "dark" || (!stored && prefersDark));
  }, []);

  const toggle = () => {
    const next = !isDark;
    setIsDark(next);
    if (next) {
      document.documentElement.classList.add("dark");
      localStorage.setItem("theme", "dark");
    } else {
      document.documentElement.classList.remove("dark");
      localStorage.setItem("theme", "light");
    }
  };

  return (
    <button
      onClick={toggle}
      className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-gray-600 hover:bg-gray-50 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100 transition-colors w-full"
    >
      {isDark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      {isDark ? "Light mode" : "Dark mode"}
    </button>
  );
}

function UserSection() {
  const router = useRouter();
  const [userInfo, setUserInfo] = useState<{ initials: string; email: string }>({
    initials: "U",
    email: "",
  });

  useEffect(() => {
    try {
      const raw = localStorage.getItem("aegis-auth");
      if (raw) {
        const parsed = JSON.parse(raw) as { state?: { user?: { email?: string; display_name?: string } } };
        const user = parsed?.state?.user;
        if (user) {
          const name = user.display_name ?? user.email ?? "";
          const initials = name
            .split(" ")
            .map((w: string) => w[0])
            .join("")
            .slice(0, 2)
            .toUpperCase() || "U";
          setUserInfo({ initials, email: user.email ?? "" });
        }
      }
    } catch {
      // ignore
    }
  }, []);

  const handleSignOut = async () => {
    try { await authApi.logout(); } catch { /* ignore */ }
    router.push("/login");
  };

  return (
    <div className="border-t border-gray-200 dark:border-gray-800 px-3 py-3 shrink-0">
      <div className="flex items-center gap-2.5 mb-2">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-semibold text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-400">
          {userInfo.initials}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-gray-900 dark:text-gray-100">
            {userInfo.email || "Admin User"}
          </p>
          {userInfo.email && (
            <p className="truncate text-xs text-gray-500 dark:text-gray-500">{userInfo.email}</p>
          )}
        </div>
        <button
          onClick={() => { void handleSignOut(); }}
          title="Sign out"
          className="shrink-0 rounded p-1 text-gray-400 hover:text-red-500 transition-colors"
        >
          <LogOut className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

function SidebarContent({ onNavClick }: { onNavClick?: (() => void) | undefined }) {
  return (
    <div className="flex h-full flex-col bg-white border-r border-gray-200 dark:bg-gray-900 dark:border-gray-800">
      {/* Logo */}
      <div className="flex h-14 items-center px-4 border-b border-gray-200 dark:border-gray-800 shrink-0">
        <Link href="/dashboard" className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gray-900 text-white text-sm font-bold dark:bg-indigo-600">
            A
          </div>
          <span className="text-base font-bold tracking-tight text-gray-900 dark:text-gray-100">Aegis ERP</span>
        </Link>
      </div>

      {/* New + button */}
      <NewActionDropdown />

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-2 py-3">
        <ul className="space-y-0.5">
          {NAV_ITEMS.map((item, i) => {
            const prevGroup = i > 0 ? NAV_ITEMS[i - 1]!.group : undefined;
            const showHeader = item.group && item.group !== prevGroup;
            return (
              <li key={item.href}>
                {showHeader && (
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider px-3 mb-1 mt-4 dark:text-gray-500">
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

      {/* Dark mode toggle */}
      <div className="px-2 py-1 shrink-0">
        <DarkModeToggle />
      </div>

      {/* User section */}
      <UserSection />
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
          "fixed inset-y-0 left-0 z-50 w-60 shadow-sm transition-transform duration-200 md:static md:translate-x-0 md:shadow-none " +
          (sidebarOpen ? "translate-x-0" : "-translate-x-full")
        }
      >
        {/* Mobile close button */}
        <button
          onClick={() => setSidebarOpen(false)}
          className="absolute right-2 top-2 rounded-md p-1.5 text-gray-500 hover:bg-gray-100 md:hidden"
        >
          <X className="h-4 w-4" />
        </button>
        <SidebarContent onNavClick={() => setSidebarOpen(false)} />
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden min-h-screen bg-gray-50 dark:bg-gray-950">
        {/* Top bar */}
        <header className="flex h-14 shrink-0 items-center gap-3 border-b bg-white dark:bg-gray-900 dark:border-gray-800 px-4">
          <button
            onClick={() => setSidebarOpen(true)}
            className="rounded-md p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors md:hidden"
            aria-label="Open navigation"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex-1" />
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
