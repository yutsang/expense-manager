import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";

export default function AppLayout({ children }: { readonly children: ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <AppShell>{children}</AppShell>
    </div>
  );
}
