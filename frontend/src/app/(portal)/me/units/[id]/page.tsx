"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  useParams,
  usePathname,
  useRouter,
  useSearchParams,
} from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { listTasks } from "@/lib/task-api";
import type {
  PaginatedResponse,
  Task,
  TaskPriority,
} from "@/lib/task-types";
import { formatTaskDate, formatTaskDateTime } from "@/lib/task-types";
import type { UnitDashboardAggregate } from "@/lib/habit-types";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TASK_PRIORITY_LABELS } from "@/components/tasks/task-list-filters";
import {
  useDashboardVersion,
  useFocusBump,
  useUnitsVersion,
} from "@/lib/me-sync";

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

export default function MyUnitDetailPage() {
  const params = useParams();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const unitId = (params.id as string) ?? "";

  // Cross-surface sync: refetch on units or dashboard bumps + tab focus.
  // Dashboard is included because the buckets on this page are aggregated
  // from the same dataset that drives /me's dashboard cards.
  const unitsVersion = useUnitsVersion();
  const dashboardVersion = useDashboardVersion();
  useFocusBump();

  const priorityParam = searchParams.get("priority") ?? "";
  const overdueParam = searchParams.get("overdue") === "true";
  const searchParam = searchParams.get("search") ?? "";
  const page = parsePositiveInt(searchParams.get("page"), 1);
  const pageSize = parsePositiveInt(
    searchParams.get("page_size"),
    DEFAULT_PAGE_SIZE,
  );
  const priority = PRIORITY_VALUES.has(priorityParam) ? priorityParam : "";

  const [unit, setUnit] = useState<UnitDashboardAggregate | null>(null);
  const [unitLoading, setUnitLoading] = useState(true);
  const [unitError, setUnitError] = useState("");

  const [tasks, setTasks] = useState<Task[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState("");

  // Two retry counters because the page has two independent data sources
  // (unit membership + tasks list). The error band next to each shows its
  // own "Thử lại" button which bumps just the relevant counter.
  const [unitReloadTick, setUnitReloadTick] = useState(0);
  const [tasksReloadTick, setTasksReloadTick] = useState(0);
  const reloadUnit = useCallback(() => setUnitReloadTick((t) => t + 1), []);
  const reloadTasks = useCallback(() => setTasksReloadTick((t) => t + 1), []);

  const [searchDraft, setSearchDraft] = useState(searchParam);
  useEffect(() => {
    let cancelled = false;
    const timerId = window.setTimeout(() => {
      if (!cancelled) setSearchDraft(searchParam);
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [searchParam]);

  // Membership gate: /api/me/units returns only units the user belongs to.
  // If the URL id isn't in that list we treat it as a 404 instead of falling
  // back to the global /api/departments endpoint (which would leak names to
  // non-members).
  useEffect(() => {
    if (!unitId) return;
    let cancelled = false;
    const timerId = window.setTimeout(() => {
      setUnitLoading(true);
      setUnitError("");
      void (async () => {
        try {
          const units = await api<UnitDashboardAggregate[]>("/api/me/units");
          if (cancelled) return;
          const match = units.find((u) => u.unit_id === unitId) ?? null;
          setUnit(match);
          if (match === null) {
            setUnitError("Đơn vị không tồn tại hoặc bạn không phải thành viên.");
          }
        } catch (err) {
          if (cancelled) return;
          setUnit(null);
          setUnitError(getErrorMessage(err, "Không tải được thông tin đơn vị"));
        } finally {
          if (!cancelled) setUnitLoading(false);
        }
      })();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [unitId, unitsVersion, dashboardVersion, unitReloadTick]);

  const filters = useMemo(
    () => ({
      department_id: unitId,
      priority: priority || undefined,
      overdue: overdueParam || undefined,
      search: searchParam || undefined,
      page,
      page_size: pageSize,
      sort_by: "due_date" as const,
      sort_dir: "asc" as const,
    }),
    [unitId, priority, overdueParam, searchParam, page, pageSize],
  );

  // Tasks load is gated on `unit !== null` (the membership check); once the
  // membership resolves the effect re-runs with the actual unit object and
  // fetches the filtered task list. Cancellation guards against rapid
  // filter changes superseding an in-flight request.
  useEffect(() => {
    if (!unitId || unit === null) return;
    let cancelled = false;
    const timerId = window.setTimeout(() => {
      setTasksLoading(true);
      setTasksError("");
      void (async () => {
        try {
          const data: PaginatedResponse<Task> = await listTasks({
            ...filters,
            priority: filters.priority as TaskPriority | undefined,
          });
          if (cancelled) return;
          setTasks(data.items);
          setTotal(data.total);
          setTotalPages(data.total_pages);
        } catch (err) {
          if (cancelled) return;
          setTasks([]);
          setTotal(0);
          setTotalPages(0);
          setTasksError(
            getErrorMessage(err, "Không tải được danh sách công việc của đơn vị"),
          );
        } finally {
          if (!cancelled) setTasksLoading(false);
        }
      })();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [unitId, unit, filters, unitsVersion, dashboardVersion, tasksReloadTick]);

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

  const updateFilter = useCallback(
    (updates: Record<string, string>) => {
      updateUrl({ ...updates, page: "" });
    },
    [updateUrl],
  );

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
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Link
          href="/me/units"
          className="inline-flex items-center gap-1 hover:text-primary transition-colors"
        >
          <span className="material-symbols-outlined text-sm">arrow_back</span>
          Đơn vị của tôi
        </Link>
      </div>

      {unitLoading ? (
        <UnitDetailHeaderSkeleton />
      ) : unit === null ? (
        <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
          <EmptyState
            icon="block"
            title="Không tìm thấy đơn vị"
            description={
              unitError ||
              "Bạn có thể đã bị gỡ khỏi đơn vị này, hoặc URL không hợp lệ."
            }
            action={
              unitError ? (
                <Button
                  variant="outline"
                  onClick={reloadUnit}
                  className="min-h-[40px] sm:min-h-8"
                >
                  <span className="material-symbols-outlined text-sm">refresh</span>
                  Thử lại
                </Button>
              ) : null
            }
          />
        </div>
      ) : (
        <>
          <PageHeader
            title={unit.unit_name}
            description={`Đơn vị · ${unit.unit_type}`}
          />

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <BucketCard
              label="Tổng"
              value={unit.buckets.total}
              icon="assignment"
              tone="primary"
            />
            <BucketCard
              label="Quá hạn"
              value={unit.buckets.overdue}
              icon="warning"
              tone="red"
            />
            <BucketCard
              label="Sắp đến hạn"
              value={unit.buckets.due_soon}
              icon="schedule"
              tone="amber"
            />
            <BucketCard
              label="Chưa tới hạn"
              value={unit.buckets.not_due_yet}
              icon="event_available"
              tone="green"
            />
          </div>

          {tasksError && (
            <div
              className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3"
              role="alert"
            >
              <span className="flex items-start gap-2 flex-1">
                <span className="material-symbols-outlined text-base mt-0.5 shrink-0">
                  error_outline
                </span>
                <span>{tasksError}</span>
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={reloadTasks}
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
                htmlFor="unit-tasks-search"
                className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
              >
                Tìm kiếm
              </label>
              <div className="relative">
                <Input
                  id="unit-tasks-search"
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
                htmlFor="unit-tasks-priority"
                className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"
              >
                Ưu tiên
              </label>
              <select
                id="unit-tasks-priority"
                value={priority}
                onChange={(e) =>
                  updateFilter({ priority: e.target.value })
                }
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
                id="unit-tasks-overdue"
                checked={overdueParam}
                onCheckedChange={(checked) =>
                  updateFilter({ overdue: checked ? "true" : "" })
                }
              />
              <label
                htmlFor="unit-tasks-overdue"
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
                <span className="material-symbols-outlined text-sm">
                  close
                </span>
                Xoá bộ lọc
              </Button>
            )}
          </div>

          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground tabular-nums">
                {total > 0
                  ? `Hiển thị ${startIndex}–${endIndex} trên ${total} công việc`
                  : tasksLoading
                    ? "Đang tải…"
                    : "0 công việc"}
              </span>
            </div>

            <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
              {tasksLoading ? (
                <UnitTaskTableSkeleton />
              ) : tasks.length === 0 ? (
                <EmptyState
                  icon={hasFilters ? "filter_list_off" : "checklist"}
                  title={
                    hasFilters
                      ? "Không có công việc phù hợp bộ lọc"
                      : "Đơn vị chưa có công việc nào"
                  }
                  description={
                    hasFilters
                      ? "Hãy thử bỏ một số bộ lọc để xem thêm kết quả."
                      : "Khi có công việc trong đơn vị, danh sách sẽ hiển thị tại đây."
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
              <div className="flex items-center justify-between">
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
      )}
    </>
  );
}

/**
 * Skeleton for the unit detail header — title placeholder, then 4 stat
 * cards in the same 2×2 / 4×1 grid that follows once data lands.
 */
function UnitDetailHeaderSkeleton() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true" aria-label="Đang tải đơn vị">
      <div className="flex flex-col gap-2 animate-pulse">
        <div className="h-8 w-2/3 max-w-[420px] rounded bg-muted" />
        <div className="h-4 w-1/3 max-w-[260px] rounded bg-muted" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="bg-card rounded-xl border border-border shadow-sahara p-4 flex items-center gap-3 animate-pulse"
          >
            <div className="h-10 w-10 rounded-lg bg-muted shrink-0" />
            <div className="flex flex-col gap-1.5 min-w-0 flex-1">
              <div className="h-2.5 w-12 rounded bg-muted" />
              <div className="h-7 w-10 rounded bg-muted" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Skeleton task list for the unit detail page — mirrors the row layout
 * (title + priority + due date) without the trailing "Cập nhật" column on
 * narrow viewports.
 */
function UnitTaskTableSkeleton() {
  return (
    <div
      className="divide-y divide-border"
      aria-busy="true"
      aria-label="Đang tải công việc của đơn vị"
    >
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

type BucketTone = "primary" | "red" | "amber" | "green";

function BucketCard({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number;
  icon: string;
  tone: BucketTone;
}) {
  const TONE: Record<BucketTone, { wrap: string; icon: string; value: string }> = {
    primary: {
      wrap: "bg-primary/10 border-primary/20",
      icon: "text-primary",
      value: "text-primary",
    },
    red: {
      wrap: "bg-red-50 border-red-200",
      icon: "text-red-600",
      value: "text-red-700",
    },
    amber: {
      wrap: "bg-amber-50 border-amber-200",
      icon: "text-amber-600",
      value: "text-amber-700",
    },
    green: {
      wrap: "bg-emerald-50 border-emerald-200",
      icon: "text-emerald-600",
      value: "text-emerald-700",
    },
  };
  const t = TONE[tone];
  return (
    <div className="bg-card rounded-xl border border-border shadow-sahara p-4 flex items-center gap-3">
      <span
        className={`flex h-10 w-10 items-center justify-center rounded-lg border ${t.wrap}`}
      >
        <span
          className={`material-symbols-outlined text-base ${t.icon}`}
          style={{
            fontVariationSettings: "'FILL' 1, 'wght' 400, 'GRAD' 0, 'opsz' 20",
          }}
        >
          {icon}
        </span>
      </span>
      <div className="flex flex-col">
        <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        <span className={`text-2xl font-bold tabular-nums ${t.value}`}>
          {value}
        </span>
      </div>
    </div>
  );
}
