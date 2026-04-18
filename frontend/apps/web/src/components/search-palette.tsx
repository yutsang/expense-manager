"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Search,
  FileText,
  Receipt,
  BookMarked,
  Users,
  BookOpen,
  Loader2,
} from "lucide-react";
import { searchApi, type SearchResultItem } from "@/lib/api";

const DEBOUNCE_MS = 300;

const ENTITY_META: Record<string, { icon: typeof FileText; label: string }> = {
  invoice: { icon: FileText, label: "Invoice" },
  bill: { icon: Receipt, label: "Bill" },
  journal_entry: { icon: BookMarked, label: "Journal" },
  contact: { icon: Users, label: "Contact" },
  account: { icon: BookOpen, label: "Account" },
};

function getEntityMeta(entityType: string) {
  return ENTITY_META[entityType] ?? { icon: Search, label: entityType };
}

interface SearchPaletteProps {
  open: boolean;
  onClose: () => void;
}

export function SearchPalette({ open, onClose }: SearchPaletteProps) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset state when opening
  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setSelectedIndex(0);
      setError(null);
      setLoading(false);
      // Focus the input after a frame so the dialog is mounted
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }, [open]);

  // Debounced search
  const performSearch = useCallback(async (q: string) => {
    if (q.trim().length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await searchApi.search(q, 20);
      setResults(response.items);
      setSelectedIndex(0);
    } catch {
      setError("Search failed. Please try again.");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    if (query.trim().length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    debounceRef.current = setTimeout(() => {
      void performSearch(query);
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [query, performSearch]);

  // Navigate to result
  const navigateTo = useCallback(
    (item: SearchResultItem) => {
      if (item.url) {
        router.push(item.url);
        onClose();
      }
    },
    [router, onClose],
  );

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case "ArrowDown": {
          e.preventDefault();
          setSelectedIndex((prev) => Math.min(prev + 1, results.length - 1));
          break;
        }
        case "ArrowUp": {
          e.preventDefault();
          setSelectedIndex((prev) => Math.max(prev - 1, 0));
          break;
        }
        case "Enter": {
          e.preventDefault();
          const selected = results[selectedIndex];
          if (selected) {
            navigateTo(selected);
          }
          break;
        }
        case "Escape": {
          e.preventDefault();
          onClose();
          break;
        }
      }
    },
    [results, selectedIndex, navigateTo, onClose],
  );

  // Scroll selected item into view
  useEffect(() => {
    if (listRef.current) {
      const selected = listRef.current.querySelector(
        `[data-index="${selectedIndex}"]`,
      );
      if (selected) {
        selected.scrollIntoView({ block: "nearest" });
      }
    }
  }, [selectedIndex]);

  // Close on backdrop click
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) {
        onClose();
      }
    },
    [onClose],
  );

  if (!open) return null;

  // Group results by entity_type
  const grouped: Record<string, SearchResultItem[]> = {};
  for (const item of results) {
    const key = item.entity_type;
    if (!grouped[key]) {
      grouped[key] = [];
    }
    grouped[key].push(item);
  }

  // Build a flat index mapping for arrow key navigation
  let flatIndex = 0;
  const groupEntries = Object.entries(grouped);

  return (
    <div
      className="fixed inset-0 z-[90] flex items-start justify-center bg-black/50 pt-[15vh]"
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-label="Search"
    >
      <div
        className="w-full max-w-lg rounded-xl border border-gray-200 bg-white shadow-2xl dark:border-gray-700 dark:bg-gray-900"
        onKeyDown={handleKeyDown}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-gray-200 px-4 dark:border-gray-700">
          <Search className="h-4 w-4 shrink-0 text-gray-400" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search invoices, bills, journals, contacts..."
            className="h-12 flex-1 bg-transparent text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none dark:text-gray-100 dark:placeholder:text-gray-500"
          />
          {loading && <Loader2 className="h-4 w-4 animate-spin text-gray-400" />}
          <kbd className="hidden rounded border border-gray-200 px-1.5 py-0.5 text-[10px] font-medium text-gray-400 sm:inline-block dark:border-gray-600">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-80 overflow-y-auto p-2">
          {/* Empty state: no query yet */}
          {query.trim().length < 2 && !loading && (
            <p className="px-3 py-8 text-center text-sm text-gray-400 dark:text-gray-500">
              Type at least 2 characters to search
            </p>
          )}

          {/* Error state */}
          {error && (
            <p className="px-3 py-8 text-center text-sm text-red-500">{error}</p>
          )}

          {/* No results */}
          {!error &&
            query.trim().length >= 2 &&
            !loading &&
            results.length === 0 && (
              <p className="px-3 py-8 text-center text-sm text-gray-400 dark:text-gray-500">
                No results for &ldquo;{query}&rdquo;
              </p>
            )}

          {/* Grouped results */}
          {groupEntries.map(([entityType, items]) => {
            const meta = getEntityMeta(entityType);
            return (
              <div key={entityType}>
                <p className="mb-1 mt-2 px-3 text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500">
                  {meta.label}s
                </p>
                {items.map((item) => {
                  const idx = flatIndex++;
                  const Icon = meta.icon;
                  const isSelected = idx === selectedIndex;
                  return (
                    <button
                      key={item.entity_id}
                      data-index={idx}
                      type="button"
                      className={
                        "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm transition-colors " +
                        (isSelected
                          ? "bg-indigo-50 text-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-300"
                          : "text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-800")
                      }
                      onClick={() => navigateTo(item)}
                      onMouseEnter={() => setSelectedIndex(idx)}
                    >
                      <Icon className="h-4 w-4 shrink-0 text-gray-400 dark:text-gray-500" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium">{item.title}</p>
                        {item.subtitle && (
                          <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                            {item.subtitle}
                          </p>
                        )}
                      </div>
                      {isSelected && (
                        <kbd className="hidden shrink-0 rounded border border-gray-200 px-1.5 py-0.5 text-[10px] font-medium text-gray-400 sm:inline-block dark:border-gray-600">
                          Enter
                        </kbd>
                      )}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        {results.length > 0 && (
          <div className="flex items-center gap-3 border-t border-gray-200 px-4 py-2 text-xs text-gray-400 dark:border-gray-700 dark:text-gray-500">
            <span>{results.length} result{results.length !== 1 ? "s" : ""}</span>
            <span className="ml-auto hidden gap-1 sm:flex">
              <kbd className="rounded border border-gray-200 px-1 py-0.5 dark:border-gray-600">
                &uarr;
              </kbd>
              <kbd className="rounded border border-gray-200 px-1 py-0.5 dark:border-gray-600">
                &darr;
              </kbd>
              <span className="ml-1">to navigate</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
