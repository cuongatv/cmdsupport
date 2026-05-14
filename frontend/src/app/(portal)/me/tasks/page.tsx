"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { PaginatedResponse, Task, TaskPriority } from "@/lib/task-types";
import { formatTaskDate, formatTaskDateTime } from "@/lib/task-types";
import { PageHeader } from "@/components/shared/page-header";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/shared/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { TASK_PRIORITY_LABELS } from "@/components/tasks/task-list-filters";
import { useDashboardVersion, useFocusBump } from "@/lib/me-sync";
import { cn } from "@/lib/utils";

const DEFAULT_PAGE_SIZE = 20;
const PRIORITY_VALUES = new Set<string>([
  "none",
  "low",
  "medium",
  "high",
  "urgent",
]);
const PRIORITY_CLASSES: Record<TaskPriority, string> = {
  none: "border-border text-muted-foreground bg-background",
  low: "bg-emerald-50 text-emerald-700 border-emerald-200",
  medium: "bg-amber-50 text-amber-700 border-amber-200",
  high: "bg-orange-50 text-orange-700 border-orange-200",
  urgent: "bg-red-50 text-red-700 border-red-200",
};

function parsePositiveInt(value: string | null, fallback: number): number {
  if (!value) return fallback;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) return fallback;
  return parsed;
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

function priorityClass(priority: string): string {
  return (
    PRIORITY_CLASSES[priority as TaskPriority] ?? PRIORITY_CLASSES.none
  );
}

function priorityLabel(priority: string): string {
  return TASK_PRIORITY_LABELS[priority as TaskPriority] ?? priority;
}

function stripHtml(value: string | null): string {
  if (!value) return "";
  return value.replace(/<[^>]*>/g, "").trim();
}

export default function MyTasksPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { hasPermission } = useAuth();

  // The personal task list shares the dataset that drives /me's dashboard
  // buckets — subscribing to dashboardVersion refetches whenever a habit
  // mutation or task-assignment change bumps the dashboard. `useFocusBump`
  // covers the tab-refocus stale check.
  const dashboardVersion = useDashboardVersion();
  useFocusBump();

  // Personal task creation today requires the full create dialog from the
  // admin task module (scope picker + project resolution). Anyone who can
  // create a task somewhere will see the link; everyone else just gets the
  // read-only list.
  const canCreate =
    hasPermission("task:create:own_dept") ||
    hasPermission("task:create:all");

  const priorityParam = searchParams.get("priority") ?? "";
  const overdueParam = searchParams.get("overdue") === "true";
  const searchParam = searchParams.get("search") ?? "";
  const page = parsePositiveInt(searchParams.get("page"), 1);
  const pageSize = parsePositiveInt(
    searchParams.get("page_size"),
    DEFAULT_PAGE_SIZE,
  );

  const priority = PRIORITY_VALUES.has(priorityParam) ? priorityParam : "";

  // Local mirror of the search box so typing feels instant and we only
  // dispatch one URL update per submit (matches the admin tasks UX).
  const [searchDraft, setSearchDraft] = useState(searchParam);
  useEffect(() => {
    // setTimeout(0) keeps the URL → draft sync out of the synchronous
    // effect body, matching the project's established React 19 pattern.
    const timerId = window.setTimeout(() => setSearchDraft(searchParam), 0);
    return () => window.clearTimeout(timerId);
  }, [searchParam]);

  const [tasks, setTasks] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Retry counter — wired to the error band's "Thử lại" button so the user
  // can re-run the fetch without leaving the page.
  const [reloadTick, setReloadTick] = useState(0);
  const reload = useCallback(() => setReloadTick((t) => t + 1), []);

  const updateUrl = useCallback(
    (updates: Record<string, string>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (value === "") {
          next.delete(key);
        } else {
          next.set(key, value);
        }
      }
      const query = next.toString();
      const target = query ? `${pathname}?${query}` : pathname;
      router.replace(target);
    },
    [pathname, router, searchParams],
  );

  // Resetting page on any non-page filter change keeps results stable: if
  // the user shrinks the result set, they shouldn't be stranded on an empty
  // tail page.
  const updateFilter = useCallback(
    (updates: Record<string, string>) => {
      updateUrl({ ...updates, page: "" });
    },
    [updateUrl],
  );

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (priority) params.set("priority", priority);
    if (overdueParam) params.set("overdue", "true");
    if (searchParam) params.set("search", searchParam);
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    return params.toString();
  }, [priority, overdueParam, searchParam, page, pageSize]);

  useEffect(() => {
    let cancelled = false;
    // setTimeout(0) defers the setLoading + fetch chain past the effect tick
    // so the lint sees no synchronous setState inside the effect body.
    const timerId = window.setTimeout(() => {
      setLoading(true);
      setError("");
      void (async () => {
        try {
          const data = await api<PaginatedResponse<Task>>(
            `/api/me/tasks?${queryString}`,
          );
          if (cancelled) return;
          setTasks(data.items);
          setTotal(data.total);
          setTotalPages(data.total_pages);
        } catch (err) {
          if (cancelled) return;
          setTasks([]);
          setTotal(0);
          setTotalPages(0);
          setError(
            getErrorMessage(err, "Không tải được danh sách công việc của bạn"),
          );
        } finally {
          if (!cancelled) setLoading(false);
        }
      })();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [queryString, dashboardVersion, reloadTick]);

  const handleSearchSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    updateFilter({ search: searchDraft.trim() });
  };

  const handlePageChange = (next: number) => {
    updateUrl({ page: next > 1 ? String(next) : "" });
  };

  const hasFilters = priority !== "" || overdueParam || searchParam !== "";
  const startIndex = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const endIndex = Math.min(page * pageSize, total);

  return (
    <>
      <PageHeader
        title="Công việc của tôi"
        description="Mọi công việc bạn được phân công trên toàn bộ đơn vị và không gian nghiệp vụ."
        action={
          canCreate ? (
            <Link
              href="/admin/tasks"
              className={cn(
                buttonVariants({ variant: "default" }),
                "min-h-[40px] px-3 sm:min-h-8 sm:px-2.5 bg-primary text-primary-foreground hover:bg-primary/90",
              )}
            >
              <span className="material-symbols-outlined text-sm">add</span>
              Tạo công việc
            </Link>
          ) : null
        }
      />

      {error && (
        <div
          className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3"
          role="alert"
        >
          <span className="flex items-start gap-2 flex-1">
            <span className="material-symbols-outlined text-base mt-0.5 shrink-0">
              error_outline
            </span>
            <span>{error}</span>
          </span>
          <Button
            variant="outline"
            size="sm"
            onClick={reload}
            className="min-h-[40px] sm:min-h-7 self-start sm:self-auto border-destructive/30 text-destructive hover:bg-destructive/10"
          >
            <span className="material-symbols-outlined text-sm">refresh</span>
            Thử lại
          </Button>
        </div>
      )}

      <div className="rounded-xl border border-border bg-card shadow-sahara p-4 flex flex-col gap-4 lg:flex-row lg:items-end">
        <form
          onSubmit={handleSearchSubmit}
          className="flex-1 flex flex-col gap-1"
        >
          <label
            htmlFor="me-tasks-search"
            className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
          >
            Tìm kiếm
          </label>
          <div className="relative">
            <Input
              id="me-tasks-search"
              type="search"
              value={searchDraft}
              onChange={(e) => setSearchDraft(e.target.value)}
              placeholder="Tiêu đề hoặc mô tả…"
              className="pl-9"
            />
            <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground material-symbols-outlined text-base">
              search
            </span>
          </div>
        </form>

        <div className="flex flex-col gap-1 lg:w-48">
          <label
            htmlFor="me-tasks-priority"
            className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
          >
            Ưu tiên
          </label>
          {/* Native <select> intentional: avoids Base UI Select coupling for a
              single dropdown with 6 static options. Smaller bundle, no portal
              gotchas inside the existing scroll container. */}
          <select
            id="me-tasks-priority"
            value={priority}
            onChange={(e) => updateFilter({ priority: e.target.value })}
            className="h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <option value="">Tất cả</option>
            <option value="urgent">Khẩn cấp</option>
            <option value="high">Cao</option>
            <option value="medium">Trung bình</option>
            <option value="low">Thấp</option>
            <option value="none">Không có</option>
          </select>
        </div>

        <div className="flex items-center gap-2 lg:pb-2">
          <Checkbox
            id="me-tasks-overdue"
            checked={overdueParam}
            onCheckedChange={(checked) =>
              updateFilter({ overdue: checked ? "true" : "" })
            }
          />
          <label
            htmlFor="me-tasks-overdue"
            className="text-sm text-foreground cursor-pointer select-none"
          >
            Chỉ quá hạn
          </label>
        </div>

        {hasFilters && (
          <Button
            variant="ghost"
            className="lg:self-end text-xs text-muted-foreground hover:text-foreground"
            onClick={() => {
              setSearchDraft("");
              updateFilter({ priority: "", overdue: "", search: "" });
            }}
          >
            <span className="material-symbols-outlined text-sm">close</span>
            Xoá bộ lọc
          </Button>
        )}
      </div>

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground tabular-nums">
            {total > 0
              ? `Hiển thị ${startIndex}–${endIndex} trên ${total} công việc`
              : loading
                ? "Đang tải…"
                : "0 công việc"}
          </span>
        </div>

        <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
          {loading ? (
            <TaskTableSkeleton />
          ) : tasks.length === 0 ? (
            <EmptyState
              icon={hasFilters ? "filter_list_off" : "checklist"}
              title={
                hasFilters
                  ? "Không có công việc phù hợp bộ lọc"
                  : "Bạn chưa có công việc nào"
              }
              description={
                hasFilters
                  ? "Hãy thử bỏ một số bộ lọc để xem thêm kết quả."
                  : "Khi quản trị viên hoặc đồng nghiệp giao việc cho bạn, công việc sẽ xuất hiện tại đây."
              }
              action={
                hasFilters ? (
                  <Button
                    variant="outline"
                    onClick={() => {
                      setSearchDraft("");
                      updateFilter({ priority: "", overdue: "", search: "" });
                    }}
                    className="min-h-[40px] sm:min-h-8"
                  >
                    <span className="material-symbols-outlined text-sm">close</span>
                    Xoá bộ lọc
                  </Button>
                ) : null
              }
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                    Công việc
                  </TableHead>
                  <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                    Ưu tiên
                  </TableHead>
                  <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                    Hạn
                  </TableHead>
                  <TableHead className="text-[11px] uppercase tracking-wider font-semibold text-muted-foreground">
                    Cập nhật
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tasks.map((task) => (
                  <TableRow
                    key={task.id}
                    className="hover:bg-secondary/30 transition-colors"
                  >
                    <TableCell className="max-w-[420px]">
                      <div className="flex flex-col gap-1">
                        <span className="truncate font-medium text-foreground">
                          {task.title}
                        </span>
                        {task.description && (
                          <p className="truncate text-xs text-muted-foreground">
                            {stripHtml(task.description)}
                          </p>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={priorityClass(task.priority)}
                      >
                        {priorityLabel(task.priority)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-muted-foreground tabular-nums">
                        {formatTaskDate(task.due_date)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground tabular-nums">
                        {formatTaskDateTime(task.updated_at)}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              Trang {page} / {totalPages}
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => handlePageChange(page - 1)}
                className="min-h-[40px] min-w-[40px] sm:min-h-8 sm:min-w-0 px-2.5"
                aria-label="Trang trước"
              >
                <span className="material-symbols-outlined text-sm">
                  chevron_left
                </span>
              </Button>
              <span className="px-3 text-xs text-muted-foreground tabular-nums">
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => handlePageChange(page + 1)}
                className="min-h-[40px] min-w-[40px] sm:min-h-8 sm:min-w-0 px-2.5"
                aria-label="Trang sau"
              >
                <span className="material-symbols-outlined text-sm">
                  chevron_right
                </span>
              </Button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

/**
 * Skeleton table — 5 rows that mirror the real row layout so the page
 * doesn't flash a spinner. The leading title cell is wider than the rest
 * to suggest its real proportions; the trailing date cells stay narrow.
 */
function TaskTableSkeleton() {
  return (
    <div className="divide-y divide-border" aria-busy="true" aria-label="Đang tải công việc">
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="flex items-center gap-3 px-4 py-3 animate-pulse"
        >
          <div className="flex-1 flex flex-col gap-1.5 min-w-0">
            <div className="h-4 w-3/4 max-w-[420px] rounded bg-muted" />
            <div className="h-3 w-1/2 max-w-[320px] rounded bg-muted" />
          </div>
          <div className="hidden sm:block h-5 w-16 rounded-md bg-muted shrink-0" />
          <div className="hidden md:block h-3 w-20 rounded bg-muted shrink-0" />
          <div className="hidden lg:block h-3 w-24 rounded bg-muted shrink-0" />
        </div>
      ))}
    </div>
  );
}
