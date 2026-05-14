"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import {
  attachDepartmentSource,
  detachDepartmentSource,
  listDepartmentSources,
} from "@/lib/department-api";
import type { DepartmentSource, UnitType } from "@/lib/department-types";
import { UNIT_TYPE_LABEL } from "@/lib/department-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

type Props = {
  departmentId: string;
  unitType: UnitType;
};

type SourcesListResponse = {
  items: Array<{
    id: string;
    title?: string | null;
    source_type?: string | null;
    file_name?: string | null;
    status: string;
    knowledge_type_name?: string | null;
  }>;
  total: number;
};

function statusDotClass(status: string): string {
  if (status === "ready") return "bg-green-500";
  if (status === "processing" || status === "pending")
    return "bg-yellow-500 animate-pulse";
  if (status === "error") return "bg-destructive";
  return "bg-muted-foreground";
}

function sourceIcon(s: { source_type?: string | null; file_name?: string | null }) {
  if (s.source_type === "url") return "link";
  return "description";
}

export function KnowledgeTab({ departmentId, unitType }: Props) {
  const [items, setItems] = useState<DepartmentSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await listDepartmentSources(departmentId);
      setItems(rows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được danh sách nguồn");
    } finally {
      setLoading(false);
    }
  }, [departmentId]);

  useEffect(() => {
    void load();
  }, [load]);

  const attachedIds = useMemo(
    () => new Set(items.map((r) => r.source_id)),
    [items]
  );

  const handleDetach = async (sourceId: string) => {
    if (!confirm("Bỏ gắn nguồn này khỏi đơn vị?")) return;
    setBusyId(sourceId);
    setError(null);
    try {
      await detachDepartmentSource(departmentId, sourceId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bỏ gắn thất bại");
    } finally {
      setBusyId(null);
    }
  };

  const handleAttach = async (sourceId: string) => {
    setBusyId(sourceId);
    setError(null);
    try {
      await attachDepartmentSource(departmentId, sourceId);
      await load();
      setPickerOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gắn nguồn thất bại");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div
      className="flex flex-col gap-4"
      data-testid="dept-tab-panel-knowledge"
      data-department-id={departmentId}
    >
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <span>
            {UNIT_TYPE_LABEL[unitType]} đang gắn{" "}
            <span className="font-semibold text-foreground">{items.length}</span>{" "}
            nguồn tri thức
          </span>
        </div>
        <Button
          size="sm"
          onClick={() => setPickerOpen(true)}
          className="bg-primary text-primary-foreground hover:bg-primary/90"
          data-testid="source-attach"
        >
          <span className="material-symbols-outlined text-base mr-1.5">add_link</span>
          Gắn nguồn
        </Button>
      </div>

      {error && (
        <div className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg flex items-center gap-2">
          <span className="material-symbols-outlined text-sm">error</span>
          {error}
        </div>
      )}

      {/* List */}
      {loading ? (
        <div className="py-12 text-center text-sm text-muted-foreground">
          Đang tải...
        </div>
      ) : items.length === 0 ? (
        <div className="bg-card rounded-xl border border-dashed border-border py-12 flex flex-col items-center gap-2">
          <span className="material-symbols-outlined text-4xl text-muted-foreground/40">
            folder_open
          </span>
          <p className="text-sm text-muted-foreground">
            Chưa có nguồn tri thức nào được gắn với đơn vị này.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((s) => {
            const icon = sourceIcon(s);
            return (
              <div
                key={s.source_id}
                className="bg-card border border-border rounded-xl px-4 py-3 flex items-center gap-3 hover:border-primary/30 transition-colors"
                data-testid="dept-source-row"
                data-source-id={s.source_id}
              >
                <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <span
                    className="material-symbols-outlined text-primary"
                    style={{ fontSize: 18 }}
                  >
                    {icon}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-foreground truncate">
                      {s.title || s.file_name || s.source_id}
                    </span>
                    {s.knowledge_type_name && (
                      <Badge
                        variant="outline"
                        className="text-[10px] h-4 px-1.5 font-medium"
                      >
                        {s.knowledge_type_name}
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2 mt-0.5 text-xs text-muted-foreground">
                    <span className="capitalize">{s.source_type || "file"}</span>
                    <span>·</span>
                    <span className="flex items-center gap-1.5">
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${statusDotClass(s.status)}`}
                      />
                      {s.status}
                    </span>
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busyId === s.source_id}
                  onClick={() => handleDetach(s.source_id)}
                  data-testid="dept-source-detach"
                >
                  <span className="material-symbols-outlined text-base mr-1">link_off</span>
                  Bỏ gắn
                </Button>
              </div>
            );
          })}
        </div>
      )}

      <SourcePickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        attachedIds={attachedIds}
        busyId={busyId}
        onPick={handleAttach}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Picker dialog
// ---------------------------------------------------------------------------

function SourcePickerDialog({
  open,
  onOpenChange,
  attachedIds,
  busyId,
  onPick,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  attachedIds: Set<string>;
  busyId: string | null;
  onPick: (sourceId: string) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SourcesListResponse["items"]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const runSearch = useCallback(async (q: string) => {
    setSearching(true);
    setSearchError(null);
    try {
      const params = new URLSearchParams({ page_size: "20" });
      if (q.trim()) params.set("search", q.trim());
      const resp = await api<SourcesListResponse>(`/api/sources?${params.toString()}`);
      setResults(resp.items);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : "Tìm kiếm thất bại");
    } finally {
      setSearching(false);
    }
  }, []);

  // Initial load + debounced search
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      void runSearch(query);
    }, 200);
    return () => clearTimeout(t);
  }, [open, query, runSearch]);

  // Reset on close
  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
      setSearchError(null);
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px] p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-2">
          <DialogTitle className="text-lg font-heading">Gắn nguồn tri thức</DialogTitle>
        </DialogHeader>
        <div className="px-6 pb-6 flex flex-col gap-3">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tìm theo tên tài liệu..."
            data-testid="source-picker-search"
            autoFocus
          />
          {searchError && (
            <div className="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-lg">
              {searchError}
            </div>
          )}
          <div className="max-h-[360px] overflow-y-auto flex flex-col gap-1 border border-border rounded-lg">
            {searching ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                Đang tìm...
              </div>
            ) : results.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground">
                Không có tài liệu phù hợp.
              </div>
            ) : (
              results.map((s) => {
                const already = attachedIds.has(s.id);
                const busy = busyId === s.id;
                return (
                  <button
                    type="button"
                    key={s.id}
                    disabled={already || busy}
                    onClick={() => void onPick(s.id)}
                    className="flex items-center gap-3 px-3 py-2.5 text-left hover:bg-accent/40 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    data-testid="source-picker-item"
                    data-source-id={s.id}
                  >
                    <span className="material-symbols-outlined text-sm text-muted-foreground shrink-0">
                      {s.source_type === "url" ? "link" : "description"}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-foreground truncate">
                        {s.title || s.file_name || s.id}
                      </div>
                      <div className="text-xs text-muted-foreground flex items-center gap-2 mt-0.5">
                        {s.knowledge_type_name && (
                          <span className="bg-accent/50 px-1.5 py-0.5 rounded text-[10px]">
                            {s.knowledge_type_name}
                          </span>
                        )}
                        <span
                          className={`w-1.5 h-1.5 rounded-full ${statusDotClass(s.status)}`}
                        />
                        <span>{s.status}</span>
                      </div>
                    </div>
                    {already && (
                      <span className="text-[10px] text-muted-foreground bg-accent/50 px-2 py-0.5 rounded shrink-0">
                        Đã gắn
                      </span>
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
