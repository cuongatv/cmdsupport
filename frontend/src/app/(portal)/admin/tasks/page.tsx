"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  getTask,
  listEligibleAssignees,
  listTaskLabels,
  listTaskProjects,
  listTaskStates,
  listTasks,
} from "@/lib/task-api";
import type {
  EligibleAssignee,
  PaginatedResponse,
  Task,
  TaskLabel,
  TaskPriority,
  TaskProject,
  TaskState,
} from "@/lib/task-types";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import {
  TaskListFilters,
  type TaskListFilterValues,
  type TaskScopeFilter,
} from "@/components/tasks/task-list-filters";
import { TaskListTable } from "@/components/tasks/task-list-table";
import { TaskDialog } from "@/components/tasks/task-dialog";
import { TaskDetailPanel } from "@/components/tasks/task-detail-panel";

// Wrap Kanban with `next/dynamic({ ssr: false })` per Next.js 16 guidance — DnD-kit
// reads pointer events on mount and would otherwise mismatch SSR markup.
const TaskKanban = dynamic(
  () => import("@/components/tasks/task-kanban"),
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
  }
);

const DEFAULT_PAGE_SIZE = 20;
// Kanban fetches as many tasks as the API allows in a single page so the
// board doesn't paginate. The API caps page_size at 100 (`Query(le=100)`
// in `app/routers/tasks.py`); requesting more returns 422.
const KANBAN_PAGE_SIZE = 100;
const PRIORITY_VALUES: ReadonlySet<string> = new Set([
  "none",
  "low",
  "medium",
  "high",
  "urgent",
]);
const SCOPE_VALUES: ReadonlySet<string> = new Set([
  "all",
  "workspace",
  "department",
]);
type ViewMode = "list" | "kanban";

function parsePositiveInt(value: string | null, fallback: number): number {
  if (!value) return fallback;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 1) return fallback;
  return parsed;
}

function parseScope(value: string | null): TaskScopeFilter {
  if (!value) return "";
  return SCOPE_VALUES.has(value) ? (value as TaskScopeFilter) : "";
}

function parseDateParam(value: string | null): string {
  if (!value) return "";
  // Accept ISO date (YYYY-MM-DD); native <input type="date"> uses this format.
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : "";
}

function projectMatchesScope(
  project: TaskProject,
  scope: TaskScopeFilter
): boolean {
  if (scope === "" || scope === "all") return true;
  if (scope === "workspace") return project.workspace_id !== null;
  if (scope === "department") return project.department_id !== null;
  return true;
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}

export default function TaskListPage() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { hasPermission, loading: authLoading } = useAuth();

  const canRead =
    hasPermission("task:read:own_dept") || hasPermission("task:read:all");
  const canCreate =
    hasPermission("task:create:own_dept") ||
    hasPermission("task:create:all");
  const canEdit =
    hasPermission("task:edit:own_dept") || hasPermission("task:edit:all");
  const canDelete =
    hasPermission("task:delete:own_dept") ||
    hasPermission("task:delete:all");
  const canCrossScope = hasPermission("task:read:all");

  const taskProjectId = searchParams.get("task_project_id") ?? "";
  const stateId = searchParams.get("state_id") ?? "";
  const priorityParam = searchParams.get("priority") ?? "";
  const assigneeId = searchParams.get("assignee_id") ?? "";
  const reporterId = searchParams.get("reporter_id") ?? "";
  const labelId = searchParams.get("label_id") ?? "";
  const dueAfter = parseDateParam(searchParams.get("due_after"));
  const dueBefore = parseDateParam(searchParams.get("due_before"));
  const overdueParam = searchParams.get("overdue");
  const overdue = overdueParam === "true";
  const scope = parseScope(searchParams.get("scope"));
  const search = searchParams.get("search") ?? "";
  const page = parsePositiveInt(searchParams.get("page"), 1);
  const pageSize = parsePositiveInt(searchParams.get("page_size"), DEFAULT_PAGE_SIZE);
  const viewParam = searchParams.get("view");
  const view: ViewMode = viewParam === "kanban" ? "kanban" : "list";
  const isKanbanView = view === "kanban";
  const effectivePage = isKanbanView ? 1 : page;
  const effectivePageSize = isKanbanView ? KANBAN_PAGE_SIZE : pageSize;
  const taskParam = searchParams.get("task") ?? "";

  const filterValues: TaskListFilterValues = {
    task_project_id: taskProjectId,
    state_id: stateId,
    priority: PRIORITY_VALUES.has(priorityParam) ? priorityParam : "",
    assignee_id: assigneeId,
    reporter_id: reporterId,
    label_id: labelId,
    due_after: dueAfter,
    due_before: dueBefore,
    overdue,
    scope,
    search,
  };

  const [projects, setProjects] = useState<TaskProject[]>([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [projectError, setProjectError] = useState("");

  const [states, setStates] = useState<TaskState[]>([]);
  const [assignees, setAssignees] = useState<EligibleAssignee[]>([]);
  const [labels, setLabels] = useState<TaskLabel[]>([]);
  const [parentCandidates, setParentCandidates] = useState<Task[]>([]);

  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskTotal, setTaskTotal] = useState(0);
  const [taskTotalPages, setTaskTotalPages] = useState(0);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [taskError, setTaskError] = useState("");

  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  const projectMap = useMemo(
    () => Object.fromEntries(projects.map((p) => [p.id, p])),
    [projects]
  );
  const stateMap = useMemo(
    () => Object.fromEntries(states.map((s) => [s.id, s])),
    [states]
  );
  const visibleProjects = useMemo(
    () =>
      filterValues.scope === "" || filterValues.scope === "all"
        ? projects
        : projects.filter((p) => projectMatchesScope(p, filterValues.scope)),
    [projects, filterValues.scope]
  );
  const selectedAssignee =
    assignees.find((a) => a.id === filterValues.assignee_id) ?? null;
  const hasProjectSelected = filterValues.task_project_id !== "";

  const updateUrl = useCallback(
    (updates: Record<string, string>) => {
      // Filter changes are URL-only — no need for server round-trip. Using
      // window.history.replaceState + searchParams refresh avoids a bug
      // where Next 16 + React Compiler memoizes router.replace into a no-op
      // after rapid filter changes (observed when scope=department is set
      // and the user then picks a state). The `next/navigation` router still
      // re-renders the tree because useSearchParams subscribes to popstate
      // and Next's internal history patches.
      const currentSearch = typeof window !== "undefined"
        ? window.location.search.replace(/^\?/, "")
        : searchParams.toString();
      const next = new URLSearchParams(currentSearch);
      for (const [key, value] of Object.entries(updates)) {
        if (value === "") {
          next.delete(key);
        } else {
          next.set(key, value);
        }
      }
      const query = next.toString();
      const target = query ? `${pathname}?${query}` : pathname;
      if (typeof window !== "undefined") {
        window.history.replaceState(null, "", target);
      } else {
        router.replace(target);
      }
    },
    [pathname, router, searchParams]
  );

  // Reset page when any non-page filter changes.
  const updateFilter = useCallback(
    (updates: Record<string, string>) => {
      updateUrl({ ...updates, page: "" });
    },
    [updateUrl]
  );

  // Load accessible projects on mount (and when permission changes).
  const loadProjects = useCallback(async () => {
    if (!canRead) {
      setProjects([]);
      setProjectsLoaded(true);
      return;
    }
    setProjectError("");
    try {
      const data = await listTaskProjects({ include_archived: false });
      setProjects(data);
    } catch (err) {
      setProjects([]);
      setProjectError(getErrorMessage(err, "Không tải được danh sách dự án"));
    } finally {
      setProjectsLoaded(true);
    }
  }, [canRead]);

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadProjects();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadProjects]);

  // Default project selection is "Tất cả dự án" (empty task_project_id).
  // User explicitly opts into a specific project by picking from the dropdown.

  // If the selected project disappears (archived) or no longer matches scope,
  // clear scoped filters so the picker re-selects a valid project.
  useEffect(() => {
    if (!projectsLoaded) return;
    if (filterValues.task_project_id === "") return;
    const current = projectMap[filterValues.task_project_id];
    const stillVisible =
      current && projectMatchesScope(current, filterValues.scope);
    if (stillVisible) return;
    const timerId = window.setTimeout(() => {
      updateUrl({
        task_project_id: "",
        state_id: "",
        assignee_id: "",
        reporter_id: "",
        label_id: "",
        page: "",
      });
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [
    projectsLoaded,
    projectMap,
    filterValues.task_project_id,
    filterValues.scope,
    updateUrl,
  ]);

  // Load states + assignees + labels whenever project changes.
  const loadProjectScopedData = useCallback(async (projectId: string) => {
    if (!projectId) {
      setStates([]);
      setAssignees([]);
      setLabels([]);
      return;
    }
    try {
      const [statesData, assigneesData, labelsData] = await Promise.all([
        listTaskStates(projectId).catch(() => [] as TaskState[]),
        listEligibleAssignees(projectId).catch(() => [] as EligibleAssignee[]),
        listTaskLabels(projectId).catch(() => [] as TaskLabel[]),
      ]);
      setStates(statesData);
      setAssignees(assigneesData);
      setLabels(labelsData);
    } catch {
      setStates([]);
      setAssignees([]);
      setLabels([]);
    }
  }, []);

  useEffect(() => {
    const projectId = filterValues.task_project_id;
    const timerId = window.setTimeout(() => {
      void loadProjectScopedData(projectId);
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [filterValues.task_project_id, loadProjectScopedData]);

  // Load top-level tasks (parent candidates) for the parent picker. Backend
  // doesn't expose a parent_task_id filter, so we fetch up to 100 tasks and
  // filter client-side. Refetched after each mutation via reloadAfterMutation.
  const loadParentCandidates = useCallback(async (projectId: string) => {
    if (!projectId) {
      setParentCandidates([]);
      return;
    }
    try {
      const res = await listTasks({
        task_project_id: projectId,
        page: 1,
        page_size: 100,
      });
      setParentCandidates(
        res.items.filter((t) => t.parent_task_id === null)
      );
    } catch {
      setParentCandidates([]);
    }
  }, []);

  useEffect(() => {
    const projectId = filterValues.task_project_id;
    const timerId = window.setTimeout(() => {
      void loadParentCandidates(projectId);
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [filterValues.task_project_id, loadParentCandidates]);

  // Load tasks whenever any filter (or page) changes.
  const loadTasks = useCallback(async () => {
    if (!canRead) {
      setTasks([]);
      setTaskTotal(0);
      setTaskTotalPages(0);
      setTasksLoading(false);
      return;
    }
    if (!filterValues.task_project_id) {
      setTasks([]);
      setTaskTotal(0);
      setTaskTotalPages(0);
      setTasksLoading(false);
      return;
    }
    setTasksLoading(true);
    setTaskError("");
    try {
      const data: PaginatedResponse<Task> = await listTasks({
        task_project_id: filterValues.task_project_id,
        state_id: filterValues.state_id || undefined,
        priority: (filterValues.priority || undefined) as TaskPriority | undefined,
        assignee_id: filterValues.assignee_id || undefined,
        reporter_id: filterValues.reporter_id || undefined,
        label_id: filterValues.label_id || undefined,
        due_from: filterValues.due_after || undefined,
        due_to: filterValues.due_before || undefined,
        overdue: filterValues.overdue ? true : undefined,
        search: filterValues.search || undefined,
        page: effectivePage,
        page_size: effectivePageSize,
      });
      setTasks(data.items);
      setTaskTotal(data.total);
      setTaskTotalPages(data.total_pages);
    } catch (err) {
      setTasks([]);
      setTaskTotal(0);
      setTaskTotalPages(0);
      setTaskError(getErrorMessage(err, "Không tải được danh sách công việc"));
    } finally {
      setTasksLoading(false);
    }
  }, [
    canRead,
    filterValues.task_project_id,
    filterValues.state_id,
    filterValues.priority,
    filterValues.assignee_id,
    filterValues.reporter_id,
    filterValues.label_id,
    filterValues.due_after,
    filterValues.due_before,
    filterValues.overdue,
    filterValues.search,
    effectivePage,
    effectivePageSize,
  ]);

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadTasks();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadTasks]);

  // Auto-open the task detail panel when the URL contains `?task=<id>`. Used
  // by the notification dropdown to deep-link from a notification click.
  useEffect(() => {
    if (!taskParam) return;
    if (selectedTask?.id === taskParam) return;
    let cancelled = false;
    const timerId = window.setTimeout(() => {
      void (async () => {
        try {
          const fetched = await getTask(taskParam);
          if (cancelled) return;
          setSelectedTask(fetched);
        } catch {
          // Task may have been deleted; silently strip the query param so we
          // don't keep retrying on subsequent renders.
          if (cancelled) return;
          updateUrl({ task: "" });
        }
      })();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [taskParam, selectedTask?.id, updateUrl]);

  // --- Filter handlers (reset page to 1) ---
  const handleProjectChange = (nextProjectId: string) => {
    updateFilter({
      task_project_id: nextProjectId,
      // Clear scoped filters when switching project.
      state_id: "",
      assignee_id: "",
      reporter_id: "",
      label_id: "",
    });
  };

  const handleStateChange = (nextStateId: string) => {
    updateFilter({ state_id: nextStateId });
  };

  const handlePriorityChange = (nextPriority: string) => {
    updateFilter({ priority: nextPriority });
  };

  const handleAssigneeChange = (nextAssigneeId: string) => {
    updateFilter({ assignee_id: nextAssigneeId });
  };

  const handleReporterChange = (nextReporterId: string) => {
    updateFilter({ reporter_id: nextReporterId });
  };

  const handleLabelChange = (nextLabelId: string) => {
    updateFilter({ label_id: nextLabelId });
  };

  const handleDueAfterChange = (nextDate: string) => {
    updateFilter({ due_after: nextDate });
  };

  const handleDueBeforeChange = (nextDate: string) => {
    updateFilter({ due_before: nextDate });
  };

  const handleOverdueChange = (nextOverdue: boolean) => {
    updateFilter({ overdue: nextOverdue ? "true" : "" });
  };

  const handleScopeChange = (nextScope: TaskScopeFilter) => {
    updateFilter({ scope: nextScope });
  };

  const handleSearchSubmit = (query: string) => {
    updateFilter({ search: query });
  };

  const handlePageChange = (nextPage: number) => {
    updateUrl({ page: nextPage > 1 ? String(nextPage) : "" });
  };

  const handleViewChange = (nextView: ViewMode) => {
    // Clear page when switching to kanban (kanban shows all in-window tasks).
    updateUrl({ view: nextView === "kanban" ? "kanban" : "", page: "" });
  };

  // Refresh tasks + parent picker after a successful create/edit/delete.
  const reloadAfterMutation = useCallback(() => {
    void loadTasks();
    void loadParentCandidates(filterValues.task_project_id);
  }, [loadTasks, loadParentCandidates, filterValues.task_project_id]);

  const handleRowClick = (task: Task) => {
    setSelectedTask(task);
  };

  const handleDetailPanelOpenChange = (open: boolean) => {
    if (!open) {
      setSelectedTask(null);
      // Strip `?task=` so the panel doesn't immediately reopen via the
      // deep-link effect above.
      if (taskParam) updateUrl({ task: "" });
    }
  };

  const currentProject =
    projectMap[filterValues.task_project_id] ?? null;

  // --- Render ---
  if (authLoading) {
    return (
      <div className="text-sm text-muted-foreground">Đang xác thực…</div>
    );
  }

  if (!canRead) {
    return (
      <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
        Bạn không có quyền truy cập danh sách công việc.
      </div>
    );
  }

  const showNoProjectsState =
    projectsLoaded && projects.length === 0 && !projectError;
  const showSelectProjectState =
    projectsLoaded && visibleProjects.length > 0 && !hasProjectSelected;
  const showScopeEmptyState =
    projectsLoaded &&
    projects.length > 0 &&
    visibleProjects.length === 0 &&
    !projectError;

  let emptyTitle = "Chưa có công việc nào";
  let emptyDescription =
    "Chưa có công việc trong dự án này. Tạo công việc đầu tiên để bắt đầu phối hợp.";
  let emptyIcon = "checklist";

  const hasActiveFilter =
    filterValues.search !== "" ||
    filterValues.state_id !== "" ||
    filterValues.priority !== "" ||
    filterValues.assignee_id !== "" ||
    filterValues.reporter_id !== "" ||
    filterValues.label_id !== "" ||
    filterValues.due_after !== "" ||
    filterValues.due_before !== "" ||
    filterValues.overdue;

  if (hasActiveFilter) {
    emptyTitle = "Không tìm thấy công việc phù hợp";
    emptyDescription =
      "Thử bỏ bớt bộ lọc hoặc điều chỉnh từ khoá tìm kiếm để xem thêm kết quả.";
    emptyIcon = "filter_list_off";
  }

  return (
    <>
      <PageHeader
        title="Quản lý công việc"
        description="Tra cứu và lọc công việc trong các dự án bạn có quyền truy cập. Lọc theo dự án, trạng thái, người nhận và mức ưu tiên."
        action={
          canCreate && currentProject ? (
            <Button
              onClick={() => setCreateDialogOpen(true)}
              data-testid="task-create-btn"
              className="bg-primary text-primary-foreground hover:bg-primary/90"
            >
              <span className="material-symbols-outlined text-sm">add</span>
              Tạo công việc
            </Button>
          ) : null
        }
      />

      <div className="flex flex-col gap-5">
        {projectError && (
          <div
            className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive flex items-center gap-2"
            role="alert"
            data-testid="task-list-projects-error"
          >
            <span className="material-symbols-outlined text-base">error</span>
            {projectError}
          </div>
        )}

        {taskError && (
          <div
            className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive flex items-center gap-2"
            role="alert"
            data-testid="task-list-tasks-error"
          >
            <span className="material-symbols-outlined text-base">error</span>
            {taskError}
          </div>
        )}

        <TaskListFilters
          projects={visibleProjects}
          states={states}
          assignees={assignees}
          labels={labels}
          values={filterValues}
          scopedFiltersDisabled={!hasProjectSelected}
          showScopeFilter={canCrossScope}
          onProjectChange={handleProjectChange}
          onStateChange={handleStateChange}
          onPriorityChange={handlePriorityChange}
          onAssigneeChange={handleAssigneeChange}
          onReporterChange={handleReporterChange}
          onLabelChange={handleLabelChange}
          onDueAfterChange={handleDueAfterChange}
          onDueBeforeChange={handleDueBeforeChange}
          onOverdueChange={handleOverdueChange}
          onScopeChange={handleScopeChange}
          onSearchSubmit={handleSearchSubmit}
        />

        <div
          className="flex items-center justify-end"
          data-testid="task-view-toggle"
        >
          <div
            className="inline-flex rounded-lg border border-border bg-card p-0.5 shadow-sm"
            role="group"
            aria-label="Chế độ hiển thị"
          >
            <button
              type="button"
              onClick={() => handleViewChange("list")}
              data-testid="task-view-list-btn"
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
              data-testid="task-view-kanban-btn"
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

        {showNoProjectsState ? (
          <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
            <EmptyState
              icon="folder_off"
              title="Chưa có dự án công việc nào"
              description="Tạo dự án công việc trước để bắt đầu quản lý và giao việc cho các thành viên."
            />
          </div>
        ) : showScopeEmptyState ? (
          <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
            <EmptyState
              icon="filter_list_off"
              title="Không có dự án phù hợp với phạm vi đã chọn"
              description="Thử đổi sang phạm vi khác hoặc bỏ lọc phạm vi để xem tất cả dự án."
            />
          </div>
        ) : showSelectProjectState ? (
          <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
            <EmptyState
              icon="folder_open"
              title="Chọn một dự án để xem công việc"
              description="Vui lòng chọn dự án ở bộ lọc phía trên để hiển thị danh sách công việc tương ứng."
            />
          </div>
        ) : isKanbanView ? (
          <div data-testid="task-kanban-wrapper">
            {tasksLoading ? (
              <div className="flex items-center justify-center rounded-xl border border-border bg-card py-16 text-sm text-muted-foreground">
                <span className="material-symbols-outlined mr-2 animate-spin text-base">
                  progress_activity
                </span>
                Đang tải công việc…
              </div>
            ) : tasks.length === 0 ? (
              <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
                <EmptyState
                  icon={emptyIcon}
                  title={emptyTitle}
                  description={emptyDescription}
                />
              </div>
            ) : (
              <TaskKanban
                key={filterValues.task_project_id}
                initialTasks={tasks}
                states={states}
                onTaskClick={handleRowClick}
              />
            )}
          </div>
        ) : (
          <TaskListTable
            tasks={tasks}
            loading={tasksLoading}
            page={page}
            pageSize={pageSize}
            total={taskTotal}
            totalPages={taskTotalPages}
            onPageChange={handlePageChange}
            projectMap={projectMap}
            stateMap={stateMap}
            selectedAssignee={selectedAssignee}
            emptyTitle={emptyTitle}
            emptyDescription={emptyDescription}
            emptyIcon={emptyIcon}
            onRowClick={handleRowClick}
          />
        )}
      </div>

      {createDialogOpen && currentProject && (
        <TaskDialog
          key="new"
          open={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          task={null}
          project={currentProject}
          states={states}
          labels={labels}
          eligibleAssignees={assignees}
          parentCandidates={parentCandidates}
          onSaved={() => {
            setCreateDialogOpen(false);
            reloadAfterMutation();
          }}
        />
      )}

      {selectedTask && currentProject && (
        <TaskDetailPanel
          key={selectedTask.id}
          open={selectedTask !== null}
          onOpenChange={handleDetailPanelOpenChange}
          task={selectedTask}
          project={currentProject}
          states={states}
          labels={labels}
          eligibleAssignees={assignees}
          parentCandidates={parentCandidates}
          canEdit={canEdit}
          canDelete={canDelete}
          onChanged={reloadAfterMutation}
        />
      )}
    </>
  );
}
