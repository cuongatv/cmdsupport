"use client";

/**
 * Searchable dropdown để chọn sản phẩm/chính sách từ wiki pages
 * (knowledge_type=Product hoặc tương tự) HOẶC nhập tên mới ("+ Thêm mới").
 *
 * Value model:
 *   - { wiki_page_id }            khi chọn từ dropdown
 *   - { product_name_custom }     khi nhập tay
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { WikiTaxonomyBadge } from "@/components/wiki/wiki-type-badge";
import { getWikiTaxonomyGroup } from "@/lib/wiki-labels";
import type { WikiSourceItem, KnowledgeTypeOption } from "./types";

export type ProductSourceValue = {
  wikiPageId: string | null;
  customName: string | null;
};

type Props = {
  value: ProductSourceValue;
  onChange: (next: ProductSourceValue) => void;
  disabled?: boolean;
};

export function ProductSourceSelect({ value, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [knowledgeTypes, setKnowledgeTypes] = useState<KnowledgeTypeOption[]>([]);
  const [activeKt, setActiveKt] = useState<string>(""); // empty = all
  const [items, setItems] = useState<WikiSourceItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  // Keep the full selected source row so we can render the taxonomy warning
  // even before the user opens the dropdown (edit-existing-rule case).
  const [selectedSource, setSelectedSource] =
    useState<WikiSourceItem | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Load knowledge types once
  useEffect(() => {
    api<KnowledgeTypeOption[]>("/api/cmd-support/rules/sources/knowledge-types")
      .then(setKnowledgeTypes)
      .catch(() => setKnowledgeTypes([]));
  }, []);

  // Load wiki pages whenever filter changes (debounced search)
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      setLoading(true);
      const params = new URLSearchParams();
      if (activeKt) params.set("knowledge_type_slug", activeKt);
      if (search.trim()) params.set("search", search.trim());
      const qs = params.toString();
      api<WikiSourceItem[]>(
        `/api/cmd-support/rules/sources/wiki-pages${qs ? `?${qs}` : ""}`,
      )
        .then(setItems)
        .catch(() => setItems([]))
        .finally(() => setLoading(false));
    }, 200);
    return () => clearTimeout(t);
  }, [open, activeKt, search]);

  // Close on outside click
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  // Keep selectedSource synced with value.wikiPageId so the taxonomy warning
  // renders on edit-existing-rule mount too. Try the already-loaded items
  // first; fall back to a one-shot unfiltered fetch if nothing matches yet.
  // Only `.then()` callbacks update state here — never the effect body
  // directly — to keep React 19 set-state-in-effect quiet.
  useEffect(() => {
    if (!value.wikiPageId) return;
    if (selectedSource?.id === value.wikiPageId) return;
    const fromItems = items.find((i) => i.id === value.wikiPageId);
    if (fromItems) {
      // Defer to a microtask so we don't set state synchronously in the effect body.
      Promise.resolve().then(() => setSelectedSource(fromItems));
      return;
    }
    let cancelled = false;
    api<WikiSourceItem[]>("/api/cmd-support/rules/sources/wiki-pages")
      .then((all) => {
        if (cancelled) return;
        const match = all.find((i) => i.id === value.wikiPageId);
        if (match) setSelectedSource(match);
      })
      .catch(() => {
        /* warning simply won't render — non-fatal */
      });
    return () => {
      cancelled = true;
    };
  }, [value.wikiPageId, items, selectedSource]);

  // selectedSource may lag behind value.wikiPageId being cleared; derive the
  // effective source so the warning hides immediately when wikiPageId is null.
  const effectiveSelectedSource = useMemo(() => {
    if (!value.wikiPageId) return null;
    if (selectedSource?.id === value.wikiPageId) return selectedSource;
    return items.find((i) => i.id === value.wikiPageId) ?? null;
  }, [value.wikiPageId, selectedSource, items]);

  const selectedLabel = useMemo(() => {
    if (value.wikiPageId) {
      if (effectiveSelectedSource) return effectiveSelectedSource.title;
      return "(Đã chọn từ wiki)";
    }
    if (value.customName) return `${value.customName} (tự nhập)`;
    return "";
  }, [value, effectiveSelectedSource]);

  // Warn when the selected source carries a `supporting_knowledge.*` slug or
  // any `*.other` slug — the link is allowed but probably wants a review.
  const showSupportingWarning = useMemo(() => {
    if (!effectiveSelectedSource) return false;
    return effectiveSelectedSource.knowledge_type_slugs.some((slug) => {
      if (getWikiTaxonomyGroup(slug) === "supporting_knowledge") return true;
      return slug.endsWith(".other");
    });
  }, [effectiveSelectedSource]);

  const handlePickWiki = (item: WikiSourceItem) => {
    onChange({ wikiPageId: item.id, customName: null });
    setSelectedSource(item);
    setOpen(false);
  };

  const handleAddCustom = () => {
    const name = search.trim();
    if (!name) return;
    onChange({ wikiPageId: null, customName: name });
    setOpen(false);
    setSearch("");
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "w-full h-9 px-3 text-left text-sm rounded-md border border-input bg-background flex items-center justify-between gap-2",
          "hover:border-foreground/30 transition-colors",
          disabled && "opacity-50 cursor-not-allowed",
        )}
      >
        <span className={cn("truncate", !selectedLabel && "text-muted-foreground")}>
          {selectedLabel || "Chọn sản phẩm/chính sách hoặc thêm mới…"}
        </span>
        <span className="material-symbols-outlined text-base text-muted-foreground">
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>

      {open && (
        <div className="absolute z-30 mt-1 w-full rounded-md border border-border bg-popover shadow-lg">
          <div className="p-2 border-b border-border space-y-2">
            <Input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm theo tên hoặc nhập sản phẩm mới…"
              className="h-8 text-sm"
            />
            {knowledgeTypes.length > 0 && (
              <div className="flex flex-wrap gap-1">
                <button
                  type="button"
                  onClick={() => setActiveKt("")}
                  className={cn(
                    "text-[11px] px-2 py-0.5 rounded-full border border-border",
                    activeKt === "" ? "bg-primary text-primary-foreground border-primary" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  Tất cả
                </button>
                {knowledgeTypes.map((kt) => (
                  <button
                    type="button"
                    key={kt.slug}
                    onClick={() => setActiveKt(kt.slug)}
                    className={cn(
                      "text-[11px] px-2 py-0.5 rounded-full border border-border",
                      activeKt === kt.slug ? "bg-primary text-primary-foreground border-primary" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {kt.name}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="max-h-64 overflow-y-auto">
            {loading ? (
              <div className="px-3 py-4 text-sm text-muted-foreground">Đang tải…</div>
            ) : items.length === 0 ? (
              <div className="px-3 py-4 text-sm text-muted-foreground">
                Không có wiki page khớp. Bạn có thể thêm mới bên dưới.
              </div>
            ) : (
              items.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  onClick={() => handlePickWiki(item)}
                  className="block w-full text-left px-3 py-2 text-sm hover:bg-muted"
                >
                  <div className="font-medium text-foreground truncate">{item.title}</div>
                  {item.knowledge_type_slugs.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {item.knowledge_type_slugs.map((slug) => (
                        <WikiTaxonomyBadge key={slug} slug={slug} />
                      ))}
                    </div>
                  )}
                  <div className="text-[11px] text-muted-foreground truncate mt-1">
                    {item.slug}
                  </div>
                </button>
              ))
            )}
          </div>

          {search.trim() && (
            <div className="border-t border-border p-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="w-full justify-start"
                onClick={handleAddCustom}
              >
                <span className="material-symbols-outlined text-base mr-1">add</span>
                Thêm mới: <span className="font-semibold ml-1">{search.trim()}</span>
              </Button>
            </div>
          )}
        </div>
      )}

      {showSupportingWarning && (
        <p
          data-testid="supporting-knowledge-link-warning"
          className="mt-1 flex items-start gap-1 text-[11px] text-amber-700 dark:text-amber-500"
        >
          <span
            aria-hidden
            className="material-symbols-outlined"
            style={{ fontSize: 14, lineHeight: "16px" }}
          >
            warning
          </span>
          <span>
            <span className="font-medium">Kiến thức bổ trợ</span>
            {" "}— nên xem lại liên kết quy tắc tư vấn.
          </span>
        </p>
      )}
    </div>
  );
}
