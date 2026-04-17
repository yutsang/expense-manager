import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { ToastProvider } from "@/components/toast-provider";

export default function AppLayout({ children }: { readonly children: ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <AppShell>{children}</AppShell>
      <ToastProvider />
    </div>
  );
}
