"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { createPersonalTask } from "@/lib/habit-api";
import { listTaskStates } from "@/lib/task-api";
import type {
  PaginatedResponse,
  Task,
  TaskPriority,
  TaskState,
} from "@/lib/task-types";
import { formatTaskDate, formatTaskDateTime } from "@/lib/task-types";

// Lazy-load Kanban: it has no SSR-relevant content and bundles a click-only
// card component that's pointless to render before hydration. Mirrors how
// /admin/tasks defers its DnD-kit-backed Kanban for the same reason.
const MyTasksKanban = dynamic(
  () => import("@/components/tasks/my-tasks-kanban"),
  {
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center rounded-xl border border-border bg-card py-16 text-sm text-muted-foreground">
        <span className="material-symbols-outlined mr-2 animate-spin text-base">
          progress_activity
        </span>
        Đang tải bảng kanban…
      </div>
    ),
  },
);
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/shared/empty-state";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { TaskScopeSwitcher } from "@/components/tasks/task-scope-switcher";
import {
  bumpDashboardVersion,
  bumpUnitsVersion,
  useDashboardVersion,
  useFocusBump,
} from "@/lib/me-sync";

const DEFAULT_PAGE_SIZE = 20;
// Kanban shows every task on a single board (no pagination), so we request
// the largest page the backend allows. `/api/me/tasks` caps `page_size` at
// 200 (`Query(le=200)` in app/routers/habits.py); requesting more returns 422.
const KANBAN_PAGE_SIZE = 200;
const PRIORITY_VALUES = new Set<string>([
  "none",
  "low",
  "medium",
  "high",
  "urgent",
]);
type ViewMode = "list" | "kanban";
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

  // The personal task list shares the dataset that drives /me's dashboard
  // buckets — subscribing to dashboardVersion refetches whenever a habit
  // mutation or task-assignment change bumps the dashboard. `useFocusBump`
  // covers the tab-refocus stale check.
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
  const viewParam = searchParams.get("view");
  const view: ViewMode = viewParam === "kanban" ? "kanban" : "list";
  const isKanbanView = view === "kanban";
  // Kanban skips pagination — always request page 1 with KANBAN_PAGE_SIZE so
  // every assigned task lands on the board. List view keeps the user-chosen
  // page + pageSize for stable URLs.
  const effectivePage = isKanbanView ? 1 : page;
  const effectivePageSize = isKanbanView ? KANBAN_PAGE_SIZE : pageSize;

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

  // state_id -> TaskState union across every project_id present in `tasks`.
  // Kanban needs this to map each task's state_id to a `state.group` so it
  // can bucket cards into the 5 canonical columns. Refetched whenever the
  // task list changes; project-scoped TaskStates are tiny (a handful of
  // rows each), and most users only see tasks from 1-3 projects.
  const [stateMap, setStateMap] = useState<Record<string, TaskState>>({});
  // project_id -> TaskState[] sorted by position asc. Drag & drop in the
  // Kanban needs this: when a card is dropped into a different group
  // column, we have to pick a real `state_id` in *that task's project*
  // matching the target group. Stored separately from `stateMap` so the
  // Kanban can resolve "first state in project X with group=done" cheaply.
  const [projectStatesMap, setProjectStatesMap] = useState<
    Record<string, TaskState[]>
  >({});

  // Retry counter — wired to the error band's "Thử lại" button so the user
  // can re-run the fetch without leaving the page.
  const [reloadTick, setReloadTick] = useState(0);
  const reload = useCallback(() => setReloadTick((t) => t + 1), []);

  // Create-task dialog state
  const [createOpen, setCreateOpen] = useState(false);
  const [createTitle, setCreateTitle] = useState("");
  const [createDescription, setCreateDescription] = useState("");
  const [createPriority, setCreatePriority] = useState<TaskPriority>("none");
  // Two separate inputs so the user can pick a date and optionally a time.
  // If the time is left blank the backend renders the task at 09:00 Hanoi
  // on the calendar (see app/routers/habits.py "Default-time rule").
  const [createDueDate, setCreateDueDate] = useState(""); // YYYY-MM-DD
  const [createDueTime, setCreateDueTime] = useState(""); // HH:mm (optional)
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [createError, setCreateError] = useState("");

  const resetCreateForm = useCallback(() => {
    setCreateTitle("");
    setCreateDescription("");
    setCreatePriority("none");
    setCreateDueDate("");
    setCreateDueTime("");
    setCreateError("");
  }, []);

  const handleCreateOpenChange = useCallback(
    (open: boolean) => {
      setCreateOpen(open);
      if (!open) resetCreateForm();
    },
    [resetCreateForm],
  );

  const handleCreateSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const title = createTitle.trim();
      if (!title) {
        setCreateError("Tiêu đề không được để trống");
        return;
      }
      setCreateSubmitting(true);
      setCreateError("");
      try {
        // Compose date + optional time into an ISO timestamp. When the time
        // input is empty we send midnight Hanoi (start of day); the backend's
        // "Default-time rule" then renders that on the calendar at 09:00.
        // Browser interprets the bare "YYYY-MM-DDTHH:mm" string as local
        // wall-clock and toISOString() converts to UTC for storage.
        let dueIso: string | null = null;
        if (createDueDate) {
          const timePart = createDueTime || "00:00";
          dueIso = new Date(`${createDueDate}T${timePart}`).toISOString();
        }
        await createPersonalTask({
          title,
          description: createDescription.trim() || null,
          priority: createPriority,
          due_date: dueIso,
        });
        bumpDashboardVersion();
        bumpUnitsVersion();
        handleCreateOpenChange(false);
        reload();
      } catch (err) {
        setCreateError(getErrorMessage(err, "Không tạo được công việc"));
      } finally {
        setCreateSubmitting(false);
      }
    },
    [
      createTitle,
      createDescription,
      createPriority,
      createDueDate,
      createDueTime,
      handleCreateOpenChange,
      reload,
    ],
  );

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
    params.set("page", String(effectivePage));
    params.set("page_size", String(effectivePageSize));
    return params.toString();
  }, [priority, overdueParam, searchParam, effectivePage, effectivePageSize]);

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

  const handleViewChange = (nextView: ViewMode) => {
    // Reset page when switching to kanban (the board ignores pagination).
    // Drop the param entirely on `list` so the URL stays clean by default.
    updateUrl({
      view: nextView === "kanban" ? "kanban" : "",
      page: "",
    });
  };

  // Union TaskState across every project_id present in the current tasks.
  // Personal task list spans many projects (cá nhân, đơn vị, không gian
  // làm việc) and there's no `/api/me/states` endpoint, so we fan out one
  // `listTaskStates` call per distinct project_id and merge into a flat
  // map keyed by state_id. Skipped when the Kanban view isn't active —
  // list view doesn't use this map.
  useEffect(() => {
    if (!isKanbanView) return;
    let cancelled = false;
    // setTimeout(0) defers every setState past the synchronous effect body,
    // matching the project's React 19 / `react-hooks/set-state-in-effect`
    // pattern used elsewhere in this file.
    const timerId = window.setTimeout(() => {
      if (cancelled) return;
      if (tasks.length === 0) {
        setStateMap({});
        setProjectStatesMap({});
        return;
      }
      void (async () => {
        const projectIds = Array.from(
          new Set(tasks.map((t) => t.task_project_id)),
        );
        try {
          const perProject = await Promise.all(
            projectIds.map((id) =>
              listTaskStates(id)
                .catch(() => [] as TaskState[])
                .then((states) => ({ id, states })),
            ),
          );
          if (cancelled) return;
          const merged: Record<string, TaskState> = {};
          const byProject: Record<string, TaskState[]> = {};
          for (const { id, states } of perProject) {
            // Sort by position asc so "first state with group=X" is stable.
            byProject[id] = [...states].sort(
              (a, b) => a.position - b.position,
            );
            for (const state of states) {
              merged[state.id] = state;
            }
          }
          setStateMap(merged);
          setProjectStatesMap(byProject);
        } catch {
          if (cancelled) return;
          setStateMap({});
          setProjectStatesMap({});
        }
      })();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [isKanbanView, tasks]);

  const hasFilters = priority !== "" || overdueParam || searchParam !== "";
  const startIndex = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const endIndex = Math.min(page * pageSize, total);

  return (
    <>
      <PageHeader
        title="Công việc của tôi"
        description="Mọi công việc bạn được phân công trên toàn bộ đơn vị và không gian nghiệp vụ."
        action={
          <Button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="min-h-[40px] px-3 sm:min-h-8 sm:px-2.5 bg-primary text-primary-foreground hover:bg-primary/90"
          >
            <span className="material-symbols-outlined text-sm">add</span>
            Tạo công việc
          </Button>
        }
      />

      <TaskScopeSwitcher current="personal" />

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
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground tabular-nums">
            {isKanbanView
              ? total > 0
                ? `${total} công việc trên bảng`
                : loading
                  ? "Đang tải…"
                  : "0 công việc"
              : total > 0
                ? `Hiển thị ${startIndex}–${endIndex} trên ${total} công việc`
                : loading
                  ? "Đang tải…"
                  : "0 công việc"}
          </span>

          <div
            className="inline-flex rounded-lg border border-border bg-card p-0.5 shadow-sm"
            role="group"
            aria-label="Chế độ hiển thị"
            data-testid="me-task-view-toggle"
          >
            <button
              type="button"
              onClick={() => handleViewChange("list")}
              data-testid="me-task-view-list-btn"
              aria-pressed={view === "list"}
              className={`inline-flex h-7 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors ${
                view === "list"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <span className="material-symbols-outlined text-[14px]">
                view_list
              </span>
              Danh sách
            </button>
            <button
              type="button"
              onClick={() => handleViewChange("kanban")}
              data-testid="me-task-view-kanban-btn"
              aria-pressed={view === "kanban"}
              className={`inline-flex h-7 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors ${
                view === "kanban"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <span className="material-symbols-outlined text-[14px]">
                view_kanban
              </span>
              Kanban
            </button>
          </div>
        </div>

        {isKanbanView ? (
          <div data-testid="me-tasks-kanban-wrapper">
            {loading ? (
              <div className="flex items-center justify-center rounded-xl border border-border bg-card py-16 text-sm text-muted-foreground">
                <span className="material-symbols-outlined mr-2 animate-spin text-base">
                  progress_activity
                </span>
                Đang tải công việc…
              </div>
            ) : tasks.length === 0 ? (
              <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
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
                        <span className="material-symbols-outlined text-sm">
                          close
                        </span>
                        Xoá bộ lọc
                      </Button>
                    ) : null
                  }
                />
              </div>
            ) : (
              <MyTasksKanban
                tasks={tasks}
                stateMap={stateMap}
                projectStatesMap={projectStatesMap}
                onTaskMoved={reload}
              />
            )}
          </div>
        ) : (
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
        )}

        {!isKanbanView && totalPages > 1 && (
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

      <Dialog open={createOpen} onOpenChange={handleCreateOpenChange}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Tạo công việc cá nhân</DialogTitle>
            <DialogDescription>
              Công việc sẽ được tạo trong Không gian làm việc cá nhân của bạn,
              không chia sẻ với đơn vị hay nhóm.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="me-create-title"
                className="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
              >
                Tiêu đề
              </label>
              <Input
                id="me-create-title"
                value={createTitle}
                onChange={(e) => setCreateTitle(e.target.value)}
                placeholder="Ví dụ: Soạn báo cáo tuần"
                maxLength={500}
                required
                autoFocus
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="me-create-priority"
                className="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
              >
                Ưu tiên
              </label>
              <select
                id="me-create-priority"
                value={createPriority}
                onChange={(e) =>
                  setCreatePriority(e.target.value as TaskPriority)
                }
                className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="none">Không</option>
                <option value="low">Thấp</option>
                <option value="medium">Trung bình</option>
                <option value="high">Cao</option>
                <option value="urgent">Khẩn</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="me-create-due-date"
                  className="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                >
                  Ngày đến hạn
                </label>
                <Input
                  id="me-create-due-date"
                  type="date"
                  value={createDueDate}
                  onChange={(e) => {
                    setCreateDueDate(e.target.value);
                    if (!e.target.value) setCreateDueTime("");
                  }}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label
                  htmlFor="me-create-due-time"
                  className="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                >
                  Giờ đến hạn (tuỳ chọn)
                </label>
                <Input
                  id="me-create-due-time"
                  type="time"
                  value={createDueTime}
                  onChange={(e) => setCreateDueTime(e.target.value)}
                  disabled={!createDueDate}
                  placeholder="09:00"
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="me-create-description"
                className="text-xs font-semibold uppercase tracking-wider text-muted-foreground"
              >
                Mô tả (tuỳ chọn)
              </label>
              <textarea
                id="me-create-description"
                value={createDescription}
                onChange={(e) => setCreateDescription(e.target.value)}
                rows={4}
                placeholder="Ghi chú thêm cho công việc này..."
                className="rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            {createError && (
              <p className="text-xs text-destructive" role="alert">
                {createError}
              </p>
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => handleCreateOpenChange(false)}
                disabled={createSubmitting}
              >
                Huỷ
              </Button>
              <Button type="submit" disabled={createSubmitting}>
                {createSubmitting ? (
                  <>
                    <span className="material-symbols-outlined text-sm animate-spin">
                      progress_activity
                    </span>
                    Đang tạo...
                  </>
                ) : (
                  "Tạo công việc"
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
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
