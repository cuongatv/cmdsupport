"use client";

import React from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { WikiPageSummary } from "@/types/wiki";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { wikiTypeIcon, wikiTypeColor, wikiTypeGroupLabel } from "./wiki-type-badge";

const GROUP_ORDER = ["entity", "concept", "topic", "source"];

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export function WikiSearchDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const router = useRouter();
  const [pages, setPages] = React.useState<WikiPageSummary[]>([]);
  const [query, setQuery] = React.useState("");
  const inputRef = React.useRef<HTMLInputElement>(null);
  const debouncedQuery = useDebounce(query, 120);

  React.useEffect(() => {
    if (!open) return;
    api<WikiPageSummary[]>("/api/wiki/pages?limit=300")
      .then((d) => setPages(Array.isArray(d) ? d : []))
      .catch(() => setPages([]));
  }, [open]);

  React.useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery("");
    }
  }, [open]);

  const filtered = React.useMemo(() => {
    if (!debouncedQuery) return pages.filter((p) => p.page_type !== "index" && p.page_type !== "log");
    const q = debouncedQuery.toLowerCase();
    return pages.filter(
      (p) =>
        p.page_type !== "index" &&
        p.page_type !== "log" &&
        (p.title.toLowerCase().includes(q) ||
          p.slug.toLowerCase().includes(q) ||
          p.summary.toLowerCase().includes(q))
    );
  }, [pages, debouncedQuery]);

  const grouped = React.useMemo(() => {
    const map = new Map<string, WikiPageSummary[]>();
    for (const p of filtered.slice(0, 60)) {
      if (!map.has(p.page_type)) map.set(p.page_type, []);
      map.get(p.page_type)!.push(p);
    }
    return map;
  }, [filtered]);

  const navigate = (slug: string) => {
    router.push(`/admin/wiki/${slug}`);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg p-0 overflow-hidden gap-0">
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
          <span className="material-symbols-outlined text-muted-foreground text-base">
            search
          </span>
          <input
            ref={inputRef}
            type="text"
            placeholder="Tìm kiếm trang tri thức..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") onOpenChange(false);
            }}
            className="flex-1 text-sm bg-transparent outline-none text-foreground placeholder:text-muted-foreground"
          />
          {query && (
            <button onClick={() => setQuery("")} className="text-muted-foreground hover:text-foreground">
              <span className="material-symbols-outlined text-base">close</span>
            </button>
          )}
        </div>

        {/* Results */}
        <div className="max-h-96 overflow-y-auto py-2">
          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground px-4 py-6 text-center">
              {query ? "Không tìm thấy trang phù hợp." : "Chưa có trang nào."}
            </p>
          ) : (
            GROUP_ORDER.filter((t) => grouped.has(t)).map((type) => (
              <div key={type} className="mb-1">
                <div className="flex items-center gap-2 px-4 py-1.5">
                  <span
                    className="material-symbols-outlined"
                    style={{ color: wikiTypeColor(type), fontSize: 13 }}
                  >
                    {wikiTypeIcon(type)}
                  </span>
                  <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                    {wikiTypeGroupLabel(type)}
                  </span>
                </div>
                {grouped.get(type)!.map((page) => (
                  <button
                    key={page.slug}
                    onClick={() => navigate(page.slug)}
                    className="w-full flex items-start gap-3 px-4 py-2 hover:bg-accent/50 transition-colors text-left"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">
                        {page.title}
                      </p>
                      {page.summary && (
                        <p className="text-xs text-muted-foreground truncate mt-0.5">
                          {page.summary}
                        </p>
                      )}
                    </div>
                    <span className="text-xs text-muted-foreground mt-0.5 shrink-0">
                      {page.slug}
                    </span>
                  </button>
                ))}
              </div>
            ))
          )}
        </div>

        <div className="border-t border-border px-4 py-2 flex items-center gap-4 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded border border-border font-mono text-xs">↵</kbd>
            điều hướng
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded border border-border font-mono text-xs">Esc</kbd>
            đóng
          </span>
          <span className="ml-auto">{filtered.length} trang</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
