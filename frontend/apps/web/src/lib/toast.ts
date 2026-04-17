/**
 * Toast notification utility for non-blocking error/success messages.
 *
 * Issue #5: Replace alert() with toast notifications.
 *
 * Uses a simple event-based approach with a global toast state.
 * Components subscribe via useToast() hook from the ToastProvider.
 */

export type ToastVariant = "error" | "success" | "warning" | "info";

export type Toast = {
  id: string;
  variant: ToastVariant;
  title: string;
  description?: string;
};

type ToastListener = (toast: Toast) => void;

const listeners: Set<ToastListener> = new Set();

let nextId = 0;

/**
 * Show a toast notification. This is the primary entry point
 * that replaces all alert() calls.
 */
export function showToast(
  variant: ToastVariant,
  title: string,
  description?: string,
): void {
  const toast: Toast = {
    id: String(++nextId),
    variant,
    title,
    description,
  };
  for (const listener of listeners) {
    listener(toast);
  }
}

/**
 * Subscribe to toast events. Returns an unsubscribe function.
 */
export function subscribeToast(listener: ToastListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
