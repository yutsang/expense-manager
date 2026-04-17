"use client";

import { useEffect, useState, useCallback } from "react";
import { subscribeToast, type Toast } from "@/lib/toast";

const TOAST_DURATION = 5000;

const variantStyles: Record<string, string> = {
  error: "border-red-500 bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-200",
  success: "border-green-500 bg-green-50 text-green-900 dark:bg-green-950 dark:text-green-200",
  warning: "border-yellow-500 bg-yellow-50 text-yellow-900 dark:bg-yellow-950 dark:text-yellow-200",
  info: "border-blue-500 bg-blue-50 text-blue-900 dark:bg-blue-950 dark:text-blue-200",
};

export function ToastProvider() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    return subscribeToast((toast) => {
      setToasts((prev) => [...prev, toast]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== toast.id));
      }, TOAST_DURATION);
    });
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 max-w-sm">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`rounded-lg border-l-4 px-4 py-3 shadow-lg transition-all ${variantStyles[toast.variant] ?? variantStyles.info}`}
          role="alert"
        >
          <div className="flex items-start justify-between gap-2">
            <div>
              <p className="text-sm font-semibold">{toast.title}</p>
              {toast.description && (
                <p className="mt-0.5 text-xs opacity-80">{toast.description}</p>
              )}
            </div>
            <button
              onClick={() => dismiss(toast.id)}
              className="shrink-0 text-xs opacity-60 hover:opacity-100"
              aria-label="Dismiss"
            >
              x
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
