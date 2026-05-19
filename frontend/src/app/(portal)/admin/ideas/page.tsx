"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  CATEGORY_LABELS,
  STATUS_LABELS,
  STATUS_TONES,
} from "@/components/ideas/constants";
import { AdminIdeaDetail } from "@/components/ideas/admin-idea-detail";
import type { AdminIdea, AdminIdeaList } from "@/components/ideas/types";

const PAGE_SIZE = 20;

export default function AdminIdeasPage() {
  const [items, setItems] = useState<AdminIdea[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");

  const [selected, setSelected] = useState<AdminIdea | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      setError(null);
      try {
        const qs = new URLSearchParams();
        qs.set("page", String(p));
        qs.set("page_size", String(PAGE_SIZE));
        if (statusFilter !== "all") qs.set("status", statusFilter);
        if (categoryFilter !== "all") qs.set("category", categoryFilter);
        if (search.trim()) qs.set("search", search.trim());
        const data = await api<AdminIdeaList>(
          `/api/admin/ideas?${qs.toString()}`
        );
        setItems(data.items);
        setTotal(data.total);
        setPage(data.page);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Không thể tải danh sách.");
      } finally {
        setLoading(false);
      }
    },
    [statusFilter, categoryFilter, search]
  );

  useEffect(() => {
    load(1);
  }, [load]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const stats = useMemo(() => {
    const counts: Record<string, number> = {
      new: 0,
      reviewing: 0,
      planned: 0,
      in_progress: 0,
      shipped: 0,
      declined: 0,
    };
    for (const item of items) {
      counts[item.status] = (counts[item.status] ?? 0) + 1;
    }
    return counts;
  }, [items]);

  const openDetail = (idea: AdminIdea) => {
    setSelected(idea);
    setDetailOpen(true);
  };

  const handleUpdated = (next: AdminIdea) => {
    setItems((prev) => prev.map((i) => (i.id === next.id ? next : i)));
    setSelected(next);
  };

  const handleDeleted = (id: string) => {
    setItems((prev) => prev.filter((i) => i.id !== id));
    setTotal((t) => Math.max(0, t - 1));
  };

  return (
    <>
      <PageHeader
        title="Góp ý cải tiến"
        description="Quản lý ý tưởng và phản hồi từ người dùng về hệ thống CMD Support."
        action={
          <Button
            variant="outline"
            size="sm"
            onClick={() => load(page)}
            disabled={loading}
          >
            <span
              className={`material-symbols-outlined text-[16px] ${
                loading ? "animate-spin" : ""
              }`}
            >
              refresh
            </span>
            Làm mới
          </Button>
        }
      />

      {/* Stat strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {(["new", "reviewing", "planned", "in_progress", "shipped", "declined"] as const).map(
          (s) => (
            <button
              key={s}
              onClick={() => {
                setStatusFilter(s === statusFilter ? "all" : s);
              }}
              className={`text-left rounded-xl border p-3 transition-all hover:shadow-sm ${
                statusFilter === s
                  ? "border-primary ring-1 ring-primary/40 bg-primary/[0.04]"
                  : "border-border bg-card"
              }`}
            >
              <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
                {STATUS_LABELS[s]}
              </div>
              <div className="text-2xl font-bold mt-1 text-foreground">
                {stats[s]}
              </div>
            </button>
          )
        )}
      </div>

      {/* Filters */}
      <div className="rounded-xl border border-border bg-card p-3 flex flex-col sm:flex-row gap-2">
        <div className="flex-1 flex items-center gap-2">
          <span className="material-symbols-outlined text-muted-foreground text-[18px]">
            search
          </span>
          <Input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") setSearch(searchInput);
            }}
            placeholder="Tìm theo tên người gửi, tiêu đề, nội dung..."
            className="border-0 shadow-none focus-visible:ring-0"
          />
        </div>
        <div className="flex gap-2">
          <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v ?? "all")}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Mọi trạng thái</SelectItem>
              {Object.entries(STATUS_LABELS).map(([v, lbl]) => (
                <SelectItem key={v} value={v}>
                  {lbl}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={categoryFilter} onValueChange={(v) => setCategoryFilter(v ?? "all")}>
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Mọi loại</SelectItem>
              {Object.entries(CATEGORY_LABELS).map(([v, lbl]) => (
                <SelectItem key={v} value={v}>
                  {lbl}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px]">error</span>
          {error}
        </div>
      )}

      {/* List */}
      <div className="rounded-xl border border-border bg-card overflow-hidden">
        {loading ? (
          <div className="py-16 flex items-center justify-center text-muted-foreground gap-2">
            <span className="material-symbols-outlined animate-spin">
              progress_activity
            </span>
            Đang tải…
          </div>
        ) : items.length === 0 ? (
          <div className="py-16 flex flex-col items-center justify-center text-center gap-2">
            <span className="material-symbols-outlined text-[48px] text-muted-foreground/40">
              forum
            </span>
            <p className="text-sm text-muted-foreground">
              Chưa có góp ý nào phù hợp bộ lọc.
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {items.map((idea) => (
              <li key={idea.id}>
                <button
                  onClick={() => openDetail(idea)}
                  className="w-full text-left px-4 py-3 hover:bg-muted/40 transition-colors flex gap-3 items-start"
                >
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center flex-wrap gap-2">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold ${
                          STATUS_TONES[idea.status] ?? ""
                        }`}
                      >
                        {STATUS_LABELS[idea.status] ?? idea.status}
                      </span>
                      <span className="text-[11px] text-muted-foreground">
                        {CATEGORY_LABELS[idea.category] ?? idea.category}
                      </span>
                      {idea.images.length > 0 && (
                        <span className="inline-flex items-center gap-0.5 text-[11px] text-muted-foreground">
                          <span className="material-symbols-outlined text-[14px]">
                            image
                          </span>
                          {idea.images.length}
                        </span>
                      )}
                    </div>
                    <div className="font-semibold text-sm text-foreground truncate">
                      {idea.title || idea.description.slice(0, 100)}
                    </div>
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {idea.description}
                    </p>
                    <div className="flex items-center flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground pt-1">
                      <span className="inline-flex items-center gap-1">
                        <span className="material-symbols-outlined text-[14px]">
                          person
                        </span>
                        {idea.contributor_name}
                      </span>
                      {idea.contributor_department && (
                        <span className="inline-flex items-center gap-1">
                          <span className="material-symbols-outlined text-[14px]">
                            domain
                          </span>
                          {idea.contributor_department}
                        </span>
                      )}
                      {idea.contributor_phone && (
                        <span className="inline-flex items-center gap-1 font-mono">
                          <span className="material-symbols-outlined text-[14px] font-sans">
                            call
                          </span>
                          {idea.contributor_phone}
                        </span>
                      )}
                      <span className="inline-flex items-center gap-1">
                        <span className="material-symbols-outlined text-[14px]">
                          schedule
                        </span>
                        {new Date(idea.created_at).toLocaleString("vi-VN")}
                      </span>
                    </div>
                  </div>
                  <span className="material-symbols-outlined text-muted-foreground shrink-0 self-center">
                    chevron_right
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-1">
          <span className="text-sm text-muted-foreground">
            Trang {page} / {totalPages} · {total} góp ý
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1 || loading}
              onClick={() => load(page - 1)}
            >
              Trước
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages || loading}
              onClick={() => load(page + 1)}
            >
              Tiếp
            </Button>
          </div>
        </div>
      )}

      <AdminIdeaDetail
        idea={selected}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        onUpdated={handleUpdated}
        onDeleted={handleDeleted}
      />
    </>
  );
}
