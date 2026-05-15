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

  const selectedLabel = useMemo(() => {
    if (value.wikiPageId) {
      const found = items.find((i) => i.id === value.wikiPageId);
      if (found) return found.title;
      return "(Đã chọn từ wiki)";
    }
    if (value.customName) return `${value.customName} (tự nhập)`;
    return "";
  }, [value, items]);

  const handlePickWiki = (item: WikiSourceItem) => {
    onChange({ wikiPageId: item.id, customName: null });
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
                  <div className="text-[11px] text-muted-foreground truncate">
                    {item.knowledge_type_slugs.join(", ") || "—"} · {item.slug}
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
    </div>
  );
}
