"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import {
  getTask,
  getTaskProject,
  listEligibleAssignees,
  listTaskLabels,
  listTaskProjects,
  listTaskStates,
  listTasks,
  resolveTaskProject,
} from "@/lib/task-api";
import type {
  EligibleAssignee,
  PaginatedResponse,
  Task,
  TaskLabel,
  TaskPriority,
  TaskProject,
  TaskScope,
  TaskState,
} from "@/lib/task-types";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/shared/page-header";
import { EmptyState } from "@/components/shared/empty-state";
import {
  TaskListFilters,
  type ScopeOption,
  type TaskListFilterValues,
  type TaskScopeFilter,
} from "@/components/tasks/task-list-filters";
import { TaskListTable } from "@/components/tasks/task-list-table";
import { TaskDialog } from "@/components/tasks/task-dialog";
import { TaskDetailPanel } from "@/components/tasks/task-detail-panel";
import { TaskScopeSwitcher } from "@/components/tasks/task-scope-switcher";

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

function parseIsoDateTimeParam(value: string | null): string {
  if (!value) return "";
  return Number.isFinite(Date.parse(value)) ? value : "";
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

// Canonical workflow groups. Matches `task_states.group` comment in
// app/database/models.py:1635 — keep these in sync.
const CANONICAL_GROUPS: ReadonlyArray<{ group: string; name: string }> = [
  { group: "backlog", name: "Backlog" },
  { group: "todo", name: "To Do" },
  { group: "in_progress", name: "In Progress" },
  { group: "review", name: "Review" },
  { group: "done", name: "Done" },
  { group: "cancelled", name: "Cancelled" },
];

/**
 * Build virtual TaskState rows — one per canonical workflow group — for the
 * multi-project Kanban. Each virtual state carries:
 *   - `id`: a synthetic sentinel `group:<group>` so React keys and the column
 *           droppable id stay unique without colliding with any real UUID.
 *   - `task_project_id`: an empty string (never used in this mode; drag is
 *           disabled so the server-side move endpoint is never hit).
 *   - `name`: English canonical name; the Kanban runs it through
 *           `translateStateName()` so the user sees "Chờ xử lý (Backlog)".
 *   - `color`: the first real color seen for that group (best-effort accent).
 * Only groups that actually appear in `realStates` are returned, so projects
 * with a truncated workflow don't get empty placeholder columns.
 */
function buildCanonicalGroupStates(realStates: TaskState[]): TaskState[] {
  const presentGroups = new Set(realStates.map((s) => s.group));
  const colorByGroup: Record<string, string | null> = {};
  for (const s of realStates) {
    if (s.color && !colorByGroup[s.group]) {
      colorByGroup[s.group] = s.color;
    }
  }
  const now = new Date(0).toISOString(); // synthetic — never displayed
  const result: TaskState[] = [];
  CANONICAL_GROUPS.forEach((g, i) => {
    if (!presentGroups.has(g.group)) return;
    result.push({
      id: `group:${g.group}`,
      task_project_id: "",
      name: g.name,
      group: g.group,
      color: colorByGroup[g.group] ?? null,
      position: i,
      wip_limit: null,
      wip_policy: "off",
      aging_warn_days: null,
      is_default: false,
      created_at: now,
      updated_at: now,
    });
  });
  return result;
}

const MS_PER_DAY = 24 * 60 * 60 * 1000;

type TaskDrilldownFilters = {
  blocked: boolean;
  aging: boolean;
  completed_from: string;
  completed_to: string;
};

function parseBooleanParam(value: string | null): boolean {
  return value === "true";
}

function taskMatchesCompletedRange(
  task: Task,
  completedFrom: string,
  completedTo: string
): boolean {
  if (!completedFrom && !completedTo) return true;
  if (!task.completed_at) return false;
  const completedAt = Date.parse(task.completed_at);
  if (!Number.isFinite(completedAt)) return false;
  if (completedFrom) {
    const fromAt = Date.parse(completedFrom);
    if (Number.isFinite(fromAt) && completedAt < fromAt) return false;
  }
  if (completedTo) {
    const toAt = Date.parse(completedTo);
    if (Number.isFinite(toAt) && completedAt > toAt + MS_PER_DAY - 1) {
      return false;
    }
  }
  return true;
}

function taskMatchesAging(
  task: Task,
  stateMap: Record<string, TaskState>,
  nowMs: number
): boolean {
  const warningDays = stateMap[task.state_id]?.aging_warn_days;
  if (warningDays === null || warningDays === undefined) return false;
  const updatedAt = Date.parse(task.updated_at);
  if (!Number.isFinite(updatedAt)) return false;
  const ageDays = Math.floor((nowMs - updatedAt) / MS_PER_DAY);
  return ageDays > warningDays;
}

function filterTasksByDrilldown(
  tasks: Task[],
  filters: TaskDrilldownFilters,
  stateMap: Record<string, TaskState>,
  nowMs: number
): Task[] {
  return tasks.filter((task) => {
    if (filters.blocked && task.is_blocked !== true) return false;
    if (
      !taskMatchesCompletedRange(
        task,
        filters.completed_from,
        filters.completed_to
      )
    ) {
      return false;
    }
    if (filters.aging && !taskMatchesAging(task, stateMap, nowMs)) return false;
    return true;
  });
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

  const taskProjectId = searchParams.get("task_project_id") ?? "";
  const workspaceParam = searchParams.get("workspace_id") ?? "";
  const departmentParam = searchParams.get("department_id") ?? "";
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
    workspace_id: workspaceParam,
    department_id: departmentParam,
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
  const [workspaces, setWorkspaces] = useState<ScopeOption[]>([]);
  const [departments, setDepartments] = useState<ScopeOption[]>([]);

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
  // The resolved hidden default project for the currently selected scope. Used
  // by the scope-create flow so the dialog can load real states/labels/eligible
  // assignees instead of showing empty pickers.
  const [scopeResolvedProject, setScopeResolvedProject] =
    useState<TaskProject | null>(null);
  const [scopeResolveError, setScopeResolveError] = useState("");
  const [scopeResolving, setScopeResolving] = useState(false);
  const [scopeStates, setScopeStates] = useState<TaskState[]>([]);
  const [scopeLabels, setScopeLabels] = useState<TaskLabel[]>([]);
  const [scopeAssignees, setScopeAssignees] = useState<EligibleAssignee[]>([]);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  // Per-project context for the detail panel. When viewing tasks by scope
  // (Đơn vị / Không gian làm việc), tasks can span multiple TaskProjects,
  // so we lazy-load each task's project + states/labels/eligible assignees on
  // demand instead of relying on the single-project effect.
  const [detailProject, setDetailProject] = useState<TaskProject | null>(null);
  const [detailStates, setDetailStates] = useState<TaskState[]>([]);
  const [detailLabels, setDetailLabels] = useState<TaskLabel[]>([]);
  const [detailAssignees, setDetailAssignees] = useState<EligibleAssignee[]>(
    []
  );
  const [detailParentCandidates, setDetailParentCandidates] = useState<Task[]>(
    []
  );

  // Kanban states for scope mode: union of states across every project_id that
  // shows up in the current task list. Without this, Kanban has no columns to
  // render and tasks look "missing".
  const [kanbanStates, setKanbanStates] = useState<TaskState[]>([]);
  // Multi-project Kanban: id → real TaskState (any project). Used so the
  // grouped board can route a task to its canonical column via
  // `realStateMap[task.state_id].group`.
  const [kanbanRealStateMap, setKanbanRealStateMap] = useState<
    Record<string, TaskState>
  >({});
  // True when `kanbanStates` are virtual canonical-group columns (multi-project
  // scope view). Drag-and-drop is meaningless across projects (state_id is per
  // project), so the Kanban component switches to read-only mode.
  const [kanbanGrouped, setKanbanGrouped] = useState(false);
  // Scope-aware filter options: assignees + labels unioned across every
  // project_id that appears in `tasks`. Drives the "Người phụ trách" and
  // "Nhãn" dropdowns when the user is filtering by scope (Đơn vị / Không
  // gian làm việc) instead of a single project.
  const [filterAssignees, setFilterAssignees] = useState<EligibleAssignee[]>(
    []
  );
  const [filterLabels, setFilterLabels] = useState<TaskLabel[]>([]);

  const projectMap = useMemo(
    () => Object.fromEntries(projects.map((p) => [p.id, p])),
    [projects]
  );
  // Merge project-scoped states (single-project mode) with kanbanStates
  // (scope mode union). Without the union, scope mode leaves stateMap empty
  // and the "Trạng thái" column renders "—" even though every task has a
  // valid state_id in the DB. kanbanStates is populated lazily after tasks
  // arrive — fall back to `states` until it loads.
  const stateMap = useMemo(() => {
    const merged: Record<string, TaskState> = {};
    for (const s of states) merged[s.id] = s;
    for (const s of kanbanStates) {
      if (!merged[s.id]) merged[s.id] = s;
    }
    return merged;
  }, [states, kanbanStates]);
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

  // Load workspace and department options so the filter bar can offer
  // concrete scope pickers (Không gian làm việc / Đơn vị) — these drive
  // scope-based task creation when the user does not pick a specific project.
  const loadScopes = useCallback(async () => {
    if (!canRead) {
      setWorkspaces([]);
      setDepartments([]);
      return;
    }
    try {
      const [workspacesData, departmentsData] = await Promise.all([
        api<Array<{ id: string; name: string }>>("/api/projects").catch(
          () => [] as Array<{ id: string; name: string }>
        ),
        api<Array<{ id: string; name: string }>>("/api/departments").catch(
          () => [] as Array<{ id: string; name: string }>
        ),
      ]);
      setWorkspaces(
        workspacesData.map((w) => ({ id: w.id, name: w.name }))
      );
      setDepartments(
        departmentsData.map((d) => ({ id: d.id, name: d.name }))
      );
    } catch {
      setWorkspaces([]);
      setDepartments([]);
    }
  }, [canRead]);

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadScopes();
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [loadScopes]);

  // Default project selection is "Tất cả dự án" (empty task_project_id).
  // User explicitly opts into a specific project by picking from the dropdown.

  // Stale-project cleanup: only relevant for the legacy deep-link path where a
  // task_project_id may be in the URL but the project has been archived or
  // become invisible. Skip when the URL is using scope mode (workspace_id /
  // department_id) — those scopes don't depend on the projects cache.
  useEffect(() => {
    if (!projectsLoaded) return;
    if (filterValues.task_project_id === "") return;
    if (filterValues.workspace_id !== "" || filterValues.department_id !== "")
      return;
    const current = projectMap[filterValues.task_project_id];
    if (current && projectMatchesScope(current, filterValues.scope)) return;
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
    filterValues.workspace_id,
    filterValues.department_id,
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

  // Load full project context for the task currently selected in the detail
  // panel. Works in both addressing modes:
  //   - project-mode (legacy): just reuses the existing states/labels caches.
  //   - scope-mode: tasks can belong to any project under the scope, so we
  //     fetch this task's owning project on demand.
  const loadDetailContext = useCallback(
    async (task: Task | null) => {
      if (task === null) {
        setDetailProject(null);
        setDetailStates([]);
        setDetailLabels([]);
        setDetailAssignees([]);
        setDetailParentCandidates([]);
        return;
      }
      const projectId = task.task_project_id;
      try {
        const cached = projects.find((p) => p.id === projectId) ?? null;
        const project = cached ?? (await getTaskProject(projectId));
        const [statesData, assigneesData, labelsData, parentRes] =
          await Promise.all([
            listTaskStates(projectId).catch(() => [] as TaskState[]),
            listEligibleAssignees(projectId).catch(
              () => [] as EligibleAssignee[]
            ),
            listTaskLabels(projectId).catch(() => [] as TaskLabel[]),
            listTasks({
              task_project_id: projectId,
              page: 1,
              page_size: 100,
            }).catch(() => ({
              items: [] as Task[],
              total: 0,
              page: 1,
              page_size: 100,
              total_pages: 0,
            })),
          ]);
        setDetailProject(project);
        setDetailStates(statesData);
        setDetailAssignees(assigneesData);
        setDetailLabels(labelsData);
        setDetailParentCandidates(
          parentRes.items.filter((t) => t.parent_task_id === null)
        );
      } catch {
        setDetailProject(null);
        setDetailStates([]);
        setDetailLabels([]);
        setDetailAssignees([]);
        setDetailParentCandidates([]);
      }
    },
    [projects]
  );

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadDetailContext(selectedTask);
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [selectedTask, loadDetailContext]);

  // Kanban + filter dropdowns need data even when the list spans multiple
  // projects. Union states/labels/eligible-assignees over every project_id
  // that appears in `tasks`. One fetch per distinct project, deduped by id.
  //
  // For Kanban specifically: when tasks span MULTIPLE projects (scope view
  // = Đơn vị / Workspace), every project owns its own `task_states` row per
  // workflow column ("Backlog", "In Progress", …). The rows share names but
  // not UUIDs, so a naive id-dedup leaves N×6 columns on the board (one
  // "Chờ xử lý" per project). Collapse them into 6 canonical group columns
  // ("backlog", "todo", "in_progress", "review", "done", "cancelled") and
  // build a `realStateMap` so the Kanban can route each task to the right
  // virtual column via its real `state_id → group`. Drag-drop is disabled
  // in this mode because `state_id` is per-project, so cross-project move
  // has no meaningful target id.
  const loadScopeOptions = useCallback(
    async (currentTasks: Task[]) => {
      const ids = Array.from(
        new Set(currentTasks.map((t) => t.task_project_id))
      );
      if (ids.length === 0) {
        setKanbanStates([]);
        setKanbanRealStateMap({});
        setKanbanGrouped(false);
        setFilterAssignees([]);
        setFilterLabels([]);
        return;
      }
      // Project-mode shortcut: if the URL pins one project and we already
      // have its caches, reuse them — saves three network calls.
      if (
        ids.length === 1 &&
        filterValues.task_project_id === ids[0] &&
        states.length > 0
      ) {
        setKanbanStates(states);
        setKanbanRealStateMap({});
        setKanbanGrouped(false);
        setFilterAssignees(assignees);
        setFilterLabels(labels);
        return;
      }
      const triples = await Promise.all(
        ids.map(async (id) => {
          const [s, a, l] = await Promise.all([
            listTaskStates(id).catch(() => [] as TaskState[]),
            listEligibleAssignees(id).catch(
              () => [] as EligibleAssignee[]
            ),
            listTaskLabels(id).catch(() => [] as TaskLabel[]),
          ]);
          return { s, a, l };
        })
      );
      const allStates: TaskState[] = [];
      const seenA = new Set<string>();
      const mergedA: EligibleAssignee[] = [];
      const seenL = new Set<string>();
      const mergedL: TaskLabel[] = [];
      for (const { s, a, l } of triples) {
        for (const item of s) allStates.push(item);
        for (const item of a) {
          if (seenA.has(item.id)) continue;
          seenA.add(item.id);
          mergedA.push(item);
        }
        for (const item of l) {
          if (seenL.has(item.id)) continue;
          seenL.add(item.id);
          mergedL.push(item);
        }
      }
      mergedA.sort((a, b) => a.name.localeCompare(b.name));
      mergedL.sort((a, b) => a.name.localeCompare(b.name));
      setFilterAssignees(mergedA);
      setFilterLabels(mergedL);

      const isMultiProject =
        ids.length > 1 || filterValues.task_project_id === "";

      if (!isMultiProject) {
        // Single project (e.g. the URL pinned `task_project_id` but the
        // local `states` cache was empty). Reuse the per-project state list
        // straight from the merged fetch.
        const projectStates = allStates.filter(
          (s) => s.task_project_id === ids[0]
        );
        projectStates.sort((a, b) => {
          if (a.group !== b.group) return a.group.localeCompare(b.group);
          if (a.position !== b.position) return a.position - b.position;
          return a.name.localeCompare(b.name);
        });
        setKanbanStates(projectStates);
        setKanbanRealStateMap({});
        setKanbanGrouped(false);
        return;
      }

      // Multi-project: collapse to canonical group columns.
      const realStateMap: Record<string, TaskState> = {};
      for (const s of allStates) realStateMap[s.id] = s;
      const virtual = buildCanonicalGroupStates(allStates);
      setKanbanStates(virtual);
      setKanbanRealStateMap(realStateMap);
      setKanbanGrouped(true);
    },
    [filterValues.task_project_id, states, assignees, labels]
  );

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadScopeOptions(tasks);
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [tasks, loadScopeOptions]);

  // Load tasks whenever any filter (or page) changes.
  const loadTasks = useCallback(async () => {
    if (!canRead) {
      setTasks([]);
      setTaskTotal(0);
      setTaskTotalPages(0);
      setTasksLoading(false);
      return;
    }
    // List view supports two addressing modes: explicit project (legacy /
    // deep-link), or scope (Đơn vị / Không gian làm việc). Both come from
    // URL filters so reload/back-button keeps the same view.
    const hasProject = filterValues.task_project_id !== "";
    const hasScope =
      filterValues.workspace_id !== "" || filterValues.department_id !== "";
    if (!hasProject && !hasScope) {
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
        task_project_id: hasProject ? filterValues.task_project_id : undefined,
        workspace_id:
          !hasProject && filterValues.workspace_id
            ? filterValues.workspace_id
            : undefined,
        department_id:
          !hasProject && filterValues.department_id
            ? filterValues.department_id
            : undefined,
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
    filterValues.workspace_id,
    filterValues.department_id,
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
      // Selecting a specific project takes precedence over scope-only mode;
      // clear the scope pickers so create resolves to this project.
      workspace_id: nextProjectId ? "" : workspaceParam,
      department_id: nextProjectId ? "" : departmentParam,
      // Clear scoped filters when switching project.
      state_id: "",
      assignee_id: "",
      reporter_id: "",
      label_id: "",
    });
  };

  const handleWorkspaceChange = (nextWorkspaceId: string) => {
    updateFilter({
      workspace_id: nextWorkspaceId,
      // Workspace and department are mutually exclusive concrete scopes.
      department_id: nextWorkspaceId ? "" : departmentParam,
      // Drop project-scoped filters so the user is not stuck viewing stale
      // states/labels from a previously-selected project in a different scope.
      task_project_id: nextWorkspaceId ? "" : taskProjectId,
      state_id: "",
      assignee_id: "",
      reporter_id: "",
      label_id: "",
    });
  };

  const handleDepartmentChange = (nextDepartmentId: string) => {
    updateFilter({
      department_id: nextDepartmentId,
      workspace_id: nextDepartmentId ? "" : workspaceParam,
      task_project_id: nextDepartmentId ? "" : taskProjectId,
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

  // Scope-based create eligibility: when the user has picked a concrete
  // workspace OR department (but no specific project), we can still create a
  // task — the backend resolves a hidden default project for that scope.
  const createScope: TaskScope | null = filterValues.workspace_id
    ? { workspace_id: filterValues.workspace_id }
    : filterValues.department_id
      ? { department_id: filterValues.department_id }
      : null;
  const createScopeLabel = filterValues.workspace_id
    ? workspaces.find((w) => w.id === filterValues.workspace_id)?.name ??
      "Không gian làm việc"
    : filterValues.department_id
      ? departments.find((d) => d.id === filterValues.department_id)?.name ??
        "Đơn vị"
      : undefined;
  const canCreateTask = currentProject !== null || createScope !== null;

  // Open the create dialog. When the user has a concrete project, we already
  // have everything in state. When they only have a scope, resolve the hidden
  // default project first so we can load its real states/labels/eligible
  // assignees — otherwise the "Người báo cáo" picker would be empty.
  const handleOpenCreateDialog = async () => {
    setScopeResolveError("");
    if (currentProject) {
      setCreateDialogOpen(true);
      return;
    }
    if (!createScope) return;
    setScopeResolving(true);
    try {
      const resolved = await resolveTaskProject(createScope);
      const [statesData, assigneesData, labelsData] = await Promise.all([
        listTaskStates(resolved.id).catch(() => [] as TaskState[]),
        listEligibleAssignees(resolved.id).catch(
          () => [] as EligibleAssignee[]
        ),
        listTaskLabels(resolved.id).catch(() => [] as TaskLabel[]),
      ]);
      // Merge the resolved project into the cached projects list. Without
      // this, a later updateFilter({ task_project_id: resolved.id }) would
      // race the stale-cleanup effect (sees projectMap[id] === undefined,
      // assumes the project disappeared, and clears task_project_id back to
      // empty — which is exactly why the newly-created task appeared lost).
      setProjects((prev) =>
        prev.some((p) => p.id === resolved.id) ? prev : [...prev, resolved]
      );
      setScopeResolvedProject(resolved);
      setScopeStates(statesData);
      setScopeAssignees(assigneesData);
      setScopeLabels(labelsData);
      setCreateDialogOpen(true);
    } catch (err) {
      setScopeResolveError(
        getErrorMessage(err, "Không khởi tạo được phạm vi để tạo công việc")
      );
    } finally {
      setScopeResolving(false);
    }
  };

  // When the dialog closes after a scope-create, drop the resolved-project
  // cache so the next open re-fetches (the resolved project, assignees, or
  // states may change between sessions).
  const handleCreateDialogOpenChange = (open: boolean) => {
    setCreateDialogOpen(open);
    if (!open) {
      setScopeResolvedProject(null);
      setScopeStates([]);
      setScopeAssignees([]);
      setScopeLabels([]);
    }
  };

  // After a scope-create succeeds, the list view already filters by the same
  // workspace_id/department_id, so the freshly-created task shows up the next
  // time loadTasks runs. Just close the dialog and trigger a reload. No need
  // to pin a project_id — that addressing mode is no longer required to list.
  const handleScopeTaskCreated = (_saved: Task) => {
    setCreateDialogOpen(false);
    setScopeResolvedProject(null);
    setScopeStates([]);
    setScopeAssignees([]);
    setScopeLabels([]);
    void loadTasks();
    void loadProjects();
  };

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

  // List view drives off scope now, not project. "No selection" means user
  // hasn't picked Đơn vị or Không gian làm việc yet AND there's no legacy
  // project filter pinned via deep-link.
  const noSelection =
    !hasProjectSelected &&
    filterValues.workspace_id === "" &&
    filterValues.department_id === "";
  const showSelectProjectState = projectsLoaded && noSelection;
  const showNoProjectsState = false;
  const showScopeEmptyState = false;

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
        description="Tra cứu và tạo công việc theo đơn vị hoặc không gian làm việc. Lọc thêm theo trạng thái, người nhận và mức ưu tiên khi cần."
        action={
          canCreate ? (
            <Button
              onClick={() => {
                void handleOpenCreateDialog();
              }}
              data-testid="task-create-btn"
              className="bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={!canCreateTask || scopeResolving}
              title={
                canCreateTask
                  ? undefined
                  : "Chọn một đơn vị hoặc không gian làm việc để tạo công việc"
              }
            >
              <span className="material-symbols-outlined text-sm">add</span>
              {scopeResolving ? "Đang chuẩn bị…" : "Tạo công việc"}
            </Button>
          ) : null
        }
      />

      <TaskScopeSwitcher current="team" />

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

        {scopeResolveError && (
          <div
            className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive flex items-center gap-2"
            role="alert"
            data-testid="task-list-scope-error"
          >
            <span className="material-symbols-outlined text-base">error</span>
            {scopeResolveError}
          </div>
        )}

        <TaskListFilters
          projects={visibleProjects}
          workspaces={workspaces}
          departments={departments}
          states={kanbanStates}
          assignees={filterAssignees}
          labels={filterLabels}
          values={filterValues}
          // Filter dropdowns now have a populated option set regardless of
          // whether the user picked a single project — they're driven by the
          // scope (Đơn vị / Không gian làm việc) state cache.
          scopedFiltersDisabled={false}
          onProjectChange={handleProjectChange}
          onWorkspaceChange={handleWorkspaceChange}
          onDepartmentChange={handleDepartmentChange}
          onStateChange={handleStateChange}
          onPriorityChange={handlePriorityChange}
          onAssigneeChange={handleAssigneeChange}
          onLabelChange={handleLabelChange}
          onDueAfterChange={handleDueAfterChange}
          onDueBeforeChange={handleDueBeforeChange}
          onOverdueChange={handleOverdueChange}
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

        {showSelectProjectState ? (
          <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
            <EmptyState
              icon="folder_open"
              title="Chọn phạm vi để xem công việc"
              description="Chọn một đơn vị hoặc không gian làm việc ở bộ lọc phía trên để hiển thị danh sách công việc tương ứng."
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
            ) : kanbanStates.length === 0 ? (
              <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sahara">
                <EmptyState
                  icon="view_kanban"
                  title="Đang chuẩn bị các cột Kanban…"
                  description="Hệ thống đang tải trạng thái công việc cho phạm vi đã chọn."
                />
              </div>
            ) : (
              <TaskKanban
                key={
                  filterValues.task_project_id ||
                  filterValues.department_id ||
                  filterValues.workspace_id ||
                  "scope"
                }
                initialTasks={tasks}
                states={kanbanStates}
                groupedView={kanbanGrouped}
                realStateMap={kanbanRealStateMap}
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
          onOpenChange={handleCreateDialogOpenChange}
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

      {/* Scope-create flow: we resolved the hidden default project before
          opening the dialog, so it behaves identically to the project flow
          — same pickers, same eligibility rules (Đơn vị members for a
          department, ProjectMember roster for a workspace) — but the saved
          handler also pins the list filter to the resolved project so the
          new task is visible immediately. */}
      {createDialogOpen && !currentProject && scopeResolvedProject && (
        <TaskDialog
          key={`new-scope-${scopeResolvedProject.id}`}
          open={createDialogOpen}
          onOpenChange={handleCreateDialogOpenChange}
          task={null}
          project={scopeResolvedProject}
          scopeLabel={createScopeLabel}
          states={scopeStates}
          labels={scopeLabels}
          eligibleAssignees={scopeAssignees}
          parentCandidates={[]}
          onSaved={handleScopeTaskCreated}
        />
      )}

      {selectedTask && detailProject && (
        <TaskDetailPanel
          key={selectedTask.id}
          open={selectedTask !== null}
          onOpenChange={handleDetailPanelOpenChange}
          task={selectedTask}
          project={detailProject}
          states={detailStates}
          labels={detailLabels}
          eligibleAssignees={detailAssignees}
          parentCandidates={detailParentCandidates}
          canEdit={canEdit}
          canDelete={canDelete}
          onChanged={() => {
            reloadAfterMutation();
            void loadDetailContext(selectedTask);
          }}
        />
      )}
    </>
  );
}
