"use client";

import React from "react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/shared/empty-state";
import { ScopeBadge } from "@/components/shared/scope-badge";

import { KnowledgeType, Department, Source } from "./types";
import { fileIcons, getFileExt } from "./utils";
import { StatusDot } from "./status-dot";
import { EditSourceDialog } from "./edit-source-dialog";
import { PlanReviewDialog } from "./plan-review-dialog";

type Props = {
  sources: Source[];
  types: KnowledgeType[];
  departments: Department[];
  loading: boolean;
  onRefresh: () => void;
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (page: number) => void;
  search: string;
  onSearch: (q: string) => void;
};

export function KnowledgeTable({
  sources,
  types,
  departments,
  loading,
  onRefresh,
  page,
  totalPages,
  total,
  onPageChange,
  search,
  onSearch,
}: Props) {
  const [actionError, setActionError] = React.useState<string | null>(null);
  const [editSource, setEditSource] = React.useState<Source | null>(null);
  const [planSource, setPlanSource] = React.useState<Source | null>(null);
  const [reingestingIds, setReingestingIds] = React.useState<Set<string>>(new Set());
  const [searchInput, setSearchInput] = React.useState(search);

  const handleDelete = async (id: string) => {
    if (!confirm("Xoá tài liệu này? Hành động không thể hoàn tác.")) return;
    setActionError(null);
    try {
      await api(`/api/sources/${id}`, { method: "DELETE" });
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to delete");
    }
  };

  const handleReingest = async (id: string) => {
    setActionError(null);
    setReingestingIds((prev) => new Set(prev).add(id));
    try {
      await api(`/api/sources/${id}/recompile`, { method: "POST" });
      onRefresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to recompile");
    } finally {
      setReingestingIds((prev) => { const s = new Set(prev); s.delete(id); return s; });
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(searchInput);
  };

  return (
    <div className="flex flex-col gap-2">
      {actionError && (
        <div className="text-sm text-destructive bg-destructive/10 px-4 py-2 rounded-lg flex items-center gap-2 mb-2">
          <span className="material-symbols-outlined text-base">error</span>
          {actionError}
        </div>
      )}

      {/* Search bar + stats */}
      <div className="flex items-center justify-between mb-2">
        <form onSubmit={handleSearchSubmit} className="flex items-center gap-2">
          <div className="relative">
            <span className="material-symbols-outlined text-sm text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2">
              search
            </span>
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Tìm kiếm tài liệu…"
              className="h-9 pl-9 pr-3 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/50 w-[260px] placeholder:text-muted-foreground/60"
            />
            {searchInput && (
              <button
                type="button"
                onClick={() => { setSearchInput(""); onSearch(""); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <span className="material-symbols-outlined text-sm">close</span>
              </button>
            )}
          </div>
        </form>
        <span className="text-xs text-muted-foreground tabular-nums">
          {total} tài liệu
        </span>
      </div>

      {/* Table */}
      <div className="bg-card rounded-xl border border-border shadow-sahara overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <span className="material-symbols-outlined text-3xl text-muted-foreground animate-spin">
              progress_activity
            </span>
          </div>
        ) : sources.length === 0 ? (
          <EmptyState
            icon="cloud_upload"
            title={search ? "Không tìm thấy kết quả" : "Chưa có tài liệu"}
            description={search ? `Không tìm thấy tài liệu phù hợp "${search}"` : "Tải lên tài liệu để bắt đầu xây dựng kho tri thức."}
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">Tài liệu</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">Phân loại</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">Phạm vi</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">Đơn vị</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">Trang</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">Wiki</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">Người đóng góp</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">Trạng thái</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">Ngày tạo</TableHead>
                <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground text-right w-[60px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sources.map((source) => (
                <TableRow key={source.id} className="group hover:bg-secondary/30 transition-colors">
                  {/* Document name + icon */}
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <span className="material-symbols-outlined text-muted-foreground" style={{ fontSize: 18 }}>
                        {fileIcons[getFileExt(source)] || (source.source_type === "url" ? "link" : "description")}
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground truncate max-w-[280px]">{source.title}</p>
                        {source.file_name && source.file_name !== source.title && (
                          <p className="text-[10px] text-muted-foreground truncate max-w-[280px]">{source.file_name}</p>
                        )}
                      </div>
                    </div>
                  </TableCell>

                  {/* Category (Knowledge Type) */}
                  <TableCell>
                    {source.knowledge_type_name ? (
                      <Badge
                        variant="outline"
                        className="text-[10px] font-medium h-5 px-2"
                        style={{
                          borderColor: source.knowledge_type_color,
                          color: source.knowledge_type_color,
                        }}
                      >
                        {source.knowledge_type_name}
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground/50">—</span>
                    )}
                  </TableCell>

                  {/* Visibility */}
                  <TableCell>
                    <ScopeBadge scopeType={source.scope_type} scopeId={source.scope_id} />
                  </TableCell>

                  {/* Department(s) */}
                  <TableCell>
                    {source.department_names && source.department_names.length > 0 ? (
                      <div className="flex flex-wrap gap-1">
                        {source.department_names.map((name, i) => (
                          <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-secondary text-secondary-foreground">
                            {name}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground/50 italic">Global</span>
                    )}
                  </TableCell>

                  {/* Page count */}
                  <TableCell>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {source.page_count ?? "—"}
                    </span>
                  </TableCell>

                  {/* Wiki page count */}
                  <TableCell>
                    {(source.wiki_page_count ?? 0) > 0 ? (
                      <span className="text-xs text-foreground tabular-nums">
                        {source.wiki_page_count}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground/50">—</span>
                    )}
                  </TableCell>

                  {/* Contributed by */}
                  <TableCell>
                    {source.contributed_by_name ? (
                      <span className="text-xs text-muted-foreground">{source.contributed_by_name}</span>
                    ) : (
                      <span className="text-xs text-muted-foreground/50">—</span>
                    )}
                  </TableCell>

                  {/* Status */}
                  <TableCell>
                    <StatusDot source={source} />
                  </TableCell>

                  {/* Created date */}
                  <TableCell>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {new Date(source.created_at).toLocaleDateString("vi-VN", {
                        day: "2-digit", month: "2-digit", year: "numeric",
                      })}
                    </span>
                  </TableCell>

                  {/* Actions */}
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger className="inline-flex items-center justify-center h-7 w-7 rounded-md hover:bg-accent text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity">
                        <span className="material-symbols-outlined text-base">more_vert</span>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => setEditSource(source)}>
                          <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>edit</span>
                          Sửa
                        </DropdownMenuItem>
                        {source.ingestion_pipeline === "mrp" && source.status === "plan_ready" && (
                          <DropdownMenuItem onClick={() => setPlanSource(source)}>
                            <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>
                              rule
                            </span>
                            Duyệt kế hoạch MRP
                          </DropdownMenuItem>
                        )}
                        <DropdownMenuItem
                          onClick={() => handleReingest(source.id)}
                          disabled={reingestingIds.has(source.id) || source.status === "processing" || source.status === "pending"}
                        >
                          <span className={`material-symbols-outlined mr-2 ${reingestingIds.has(source.id) ? "animate-spin" : ""}`} style={{ fontSize: 16 }}>
                            refresh
                          </span>
                           {reingestingIds.has(source.id) ? "Đang xử lý lại…" : "Xử lý lại"}
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          onClick={() => handleDelete(source.id)}
                          className="text-destructive"
                        >
                          <span className="material-symbols-outlined mr-2" style={{ fontSize: 16 }}>delete</span>
                          Xoá
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-3">
          <span className="text-xs text-muted-foreground">
            Trang {page} / {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
              className="h-8 px-2.5"
            >
              <span className="material-symbols-outlined text-sm">chevron_left</span>
            </Button>
            {Array.from({ length: Math.min(totalPages, 7) }, (_, i) => {
              let p: number;
              if (totalPages <= 7) {
                p = i + 1;
              } else if (page <= 4) {
                p = i + 1;
              } else if (page >= totalPages - 3) {
                p = totalPages - 6 + i;
              } else {
                p = page - 3 + i;
              }
              return (
                <Button
                  key={p}
                  variant={p === page ? "default" : "outline"}
                  size="sm"
                  onClick={() => onPageChange(p)}
                  className={`h-8 w-8 p-0 text-xs ${p === page ? "bg-primary text-primary-foreground" : ""}`}
                >
                  {p}
                </Button>
              );
            })}
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
              className="h-8 px-2.5"
            >
              <span className="material-symbols-outlined text-sm">chevron_right</span>
            </Button>
          </div>
        </div>
      )}

      {editSource && (
        <EditSourceDialog
          source={editSource}
          types={types}
          departments={departments}
          onClose={() => setEditSource(null)}
          onSaved={() => { setEditSource(null); onRefresh(); }}
        />
      )}

      {planSource && (
        <PlanReviewDialog
          source={planSource}
          onClose={() => setPlanSource(null)}
          onReviewed={() => { setPlanSource(null); onRefresh(); }}
        />
      )}
    </div>
  );
}
