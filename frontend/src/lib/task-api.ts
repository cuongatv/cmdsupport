import { api, apiUpload } from "@/lib/api";
import type {
  AdminDashboardFlowSummaryResponse,
  DashboardAssigneeItem,
  DashboardStateItem,
  DepartmentMember,
  DepartmentSummary,
  DueSoonItem,
  EligibleAssignee,
  FlowThroughput,
  KnowledgeLinkType,
  Notification,
  NotificationListOptions,
  PaginatedResponse,
  SquadMemberCapacity,
  Sprint,
  SprintCreate,
  SprintUpdate,
  Task,
  TaskActivity,
  TaskAssignee,
  TaskAssigneeRequest,
  TaskAttachment,
  TaskAttachmentWithPresignedUrl,
  TaskComment,
  TaskCommentCreate,
  TaskCommentUpdate,
  TaskCreate,
  TaskDashboard,
  TaskDependency,
  TaskDependencyType,
  TaskFilters,
  TaskFlowSnapshot,
  TaskForwardRequest,
  TaskGovernanceAdvisory,
  TaskKnowledgeLink,
  TaskLabel,
  TaskLabelCreate,
  TaskLabelUpdate,
  TaskMoveAdvisory,
  TaskMoveRequest,
  TaskMoveResult,
  TaskPriority,
  TaskProject,
  TaskProjectCreate,
  TaskProjectTemplate,
  TaskProjectUpdate,
  TaskScope,
  TaskState,
  TaskStateCreate,
  TaskStateUpdate,
  TaskStatus,
  TaskUpdate,
} from "@/lib/task-types";

function appendQuery(params: URLSearchParams, key: string, value: string | number | boolean | null | undefined) {
  if (value === undefined || value === null) return;
  params.set(key, String(value));
}

export type AdminDashboardQueryParams = {
  start_date?: string | null;
  end_date?: string | null;
  department_id?: string | null;
  workspace_id?: string | null;
  project_id?: string | null;
  sprint_id?: string | null;
};

function withQuery(path: string, params: URLSearchParams): string {
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}

export function getTaskStatus(): Promise<TaskStatus> {
  return api<TaskStatus>("/api/tasks/status");
}

export function listTaskProjects(options: {
  workspace_id?: string;
  department_id?: string;
  include_archived?: boolean;
} = {}): Promise<TaskProject[]> {
  const params = new URLSearchParams();
  appendQuery(params, "workspace_id", options.workspace_id);
  appendQuery(params, "department_id", options.department_id);
  appendQuery(params, "include_archived", options.include_archived);
  return api<TaskProject[]>(withQuery("/api/tasks/projects", params));
}

export function createTaskProject(body: TaskProjectCreate): Promise<TaskProject> {
  return api<TaskProject>("/api/tasks/projects", { method: "POST", body });
}

// Resolve (lazy-create) the hidden default project for a scope. Used by the
// scope-based create flow so we can preload states/eligible-assignees just
// like the explicit-project flow.
export function resolveTaskProject(scope: TaskScope): Promise<TaskProject> {
  const params = new URLSearchParams();
  if ("workspace_id" in scope) {
    params.set("workspace_id", scope.workspace_id);
  } else {
    params.set("department_id", scope.department_id);
  }
  return api<TaskProject>(`/api/tasks/projects/resolve?${params.toString()}`);
}

export function getTaskProject(projectId: string): Promise<TaskProject> {
  return api<TaskProject>(`/api/tasks/projects/${projectId}`);
}

export function updateTaskProject(projectId: string, body: TaskProjectUpdate): Promise<TaskProject> {
  return api<TaskProject>(`/api/tasks/projects/${projectId}`, { method: "PATCH", body });
}

export function archiveTaskProject(projectId: string): Promise<TaskProject> {
  return api<TaskProject>(`/api/tasks/projects/${projectId}/archive`, { method: "DELETE" });
}

export function listTaskStates(projectId: string): Promise<TaskState[]> {
  return api<TaskState[]>(`/api/tasks/projects/${projectId}/states`);
}

export function createTaskState(projectId: string, body: TaskStateCreate): Promise<TaskState> {
  return api<TaskState>(`/api/tasks/projects/${projectId}/states`, { method: "POST", body });
}

export function updateTaskState(projectId: string, stateId: string, body: TaskStateUpdate): Promise<TaskState> {
  return api<TaskState>(`/api/tasks/projects/${projectId}/states/${stateId}`, { method: "PATCH", body });
}

export function deleteTaskState(projectId: string, stateId: string, reassignStateId?: string): Promise<void> {
  const params = new URLSearchParams();
  appendQuery(params, "reassign_state_id", reassignStateId);
  return api<void>(withQuery(`/api/tasks/projects/${projectId}/states/${stateId}`, params), {
    method: "DELETE",
  });
}

export function listTaskLabels(projectId: string): Promise<TaskLabel[]> {
  return api<TaskLabel[]>(`/api/tasks/projects/${projectId}/labels`);
}

export function createTaskLabel(projectId: string, body: TaskLabelCreate): Promise<TaskLabel> {
  return api<TaskLabel>(`/api/tasks/projects/${projectId}/labels`, { method: "POST", body });
}

export function updateTaskLabel(projectId: string, labelId: string, body: TaskLabelUpdate): Promise<TaskLabel> {
  return api<TaskLabel>(`/api/tasks/projects/${projectId}/labels/${labelId}`, { method: "PATCH", body });
}

export function deleteTaskLabel(projectId: string, labelId: string): Promise<void> {
  return api<void>(`/api/tasks/projects/${projectId}/labels/${labelId}`, { method: "DELETE" });
}

export function listTasks(filters: TaskFilters): Promise<PaginatedResponse<Task>> {
  const params = new URLSearchParams();
  appendQuery(params, "task_project_id", filters.task_project_id);
  appendQuery(params, "workspace_id", filters.workspace_id);
  appendQuery(params, "department_id", filters.department_id);
  appendQuery(params, "search", filters.search);
  appendQuery(params, "state_id", filters.state_id);
  appendQuery(params, "assignee_id", filters.assignee_id);
  appendQuery(params, "reporter_id", filters.reporter_id);
  appendQuery(params, "priority", filters.priority);
  appendQuery(params, "label_id", filters.label_id);
  appendQuery(params, "due_from", filters.due_from);
  appendQuery(params, "due_to", filters.due_to);
  appendQuery(params, "overdue", filters.overdue);
  appendQuery(params, "is_blocked", filters.is_blocked);
  appendQuery(params, "completed_from", filters.completed_from);
  appendQuery(params, "completed_to", filters.completed_to);
  appendQuery(params, "include_deleted", filters.include_deleted);
  appendQuery(params, "page", filters.page);
  appendQuery(params, "page_size", filters.page_size);
  appendQuery(params, "sort_by", filters.sort_by);
  appendQuery(params, "sort_dir", filters.sort_dir);
  return api<PaginatedResponse<Task>>(withQuery("/api/tasks", params));
}

export function createTask(taskProjectId: string, body: TaskCreate): Promise<Task> {
  return api<Task>(`/api/tasks?task_project_id=${encodeURIComponent(taskProjectId)}`, {
    method: "POST",
    body,
  });
}

// Scope-based create: the user only picks a scope (Không gian làm việc / Phòng
// ban) and the backend resolves or creates the hidden default project. Body's
// state_id may be omitted; the backend fills it with the project's default
// state so the UI does not need to know the project's workflow upfront.
export function createTaskInScope(scope: TaskScope, body: TaskCreate): Promise<Task> {
  const params = new URLSearchParams();
  if ("workspace_id" in scope) {
    params.set("workspace_id", scope.workspace_id);
  } else {
    params.set("department_id", scope.department_id);
  }
  return api<Task>(`/api/tasks?${params.toString()}`, {
    method: "POST",
    body,
  });
}

export function getTask(taskId: string): Promise<Task> {
  return api<Task>(`/api/tasks/${taskId}`);
}

export function updateTask(taskId: string, body: TaskUpdate): Promise<Task> {
  return api<Task>(`/api/tasks/${taskId}`, { method: "PATCH", body });
}

function pickGovernanceAdvisories(raw: unknown): TaskGovernanceAdvisory[] {
  // Phase 5 (FEATURE_AGILE_PHASE_5): the backend may surface zero or more
  // Stage A governance advisories on the move response. Two shapes are
  // tolerated so older deployments that only emit a single advisory still
  // light up the UI:
  //   - ``"permission_advisories": [{code, permission}, ...]`` (preferred)
  //   - ``"advisory": {code: "PERMISSION_DENIED_ADVISORY", ...}`` (legacy)
  // The WIP advisory (``code: "WIP_EXCEEDED"``) is intentionally skipped
  // here — it has its own dedicated channel in TaskMoveResult.advisory.
  if (!raw || typeof raw !== "object") return [];
  const obj = raw as Record<string, unknown>;
  const advisories: TaskGovernanceAdvisory[] = [];
  if (Array.isArray(obj.permission_advisories)) {
    for (const entry of obj.permission_advisories) {
      if (entry && typeof entry === "object") {
        const e = entry as Record<string, unknown>;
        if (e.code === "PERMISSION_DENIED_ADVISORY" && typeof e.permission === "string") {
          advisories.push({
            code: "PERMISSION_DENIED_ADVISORY",
            permission: e.permission,
          });
        }
      }
    }
  }
  if (
    advisories.length === 0 &&
    obj.advisory &&
    typeof obj.advisory === "object"
  ) {
    const adv = obj.advisory as Record<string, unknown>;
    if (
      adv.code === "PERMISSION_DENIED_ADVISORY" &&
      typeof adv.permission === "string"
    ) {
      advisories.push({
        code: "PERMISSION_DENIED_ADVISORY",
        permission: adv.permission,
      });
    }
  }
  return advisories;
}

export async function moveTask(
  taskId: string,
  body: TaskMoveRequest,
): Promise<TaskMoveResult> {
  // Forward-compatible parse. The Phase 1 router still returns a bare
  // ``TaskOut`` body today (`response_model=TaskOut`). Once the move endpoint
  // is refactored to surface the WIP `warn` advisory it will return either
  //   - ``{"task": TaskOut, "advisory": {...} | null}``  (wrapped), or
  //   - ``TaskOut`` with an extra top-level ``advisory`` field             .
  // Both shapes are accepted; legacy bare-Task responses produce
  // ``{task, advisory: null}`` so existing callers can keep using the result.
  const raw = await api<Record<string, unknown>>(`/api/tasks/${taskId}/move`, {
    method: "POST",
    body,
  });
  const governance_advisories = pickGovernanceAdvisories(raw);
  if (raw && typeof raw === "object" && "task" in raw) {
    const wrapper = raw as { task: Task; advisory?: TaskMoveAdvisory | null };
    // The wrapped shape's `advisory` field carries the WIP advisory; skip it
    // when it's actually a governance advisory (already extracted above).
    const wipAdvisory =
      wrapper.advisory && wrapper.advisory.code === "WIP_EXCEEDED"
        ? wrapper.advisory
        : null;
    return { task: wrapper.task, advisory: wipAdvisory, governance_advisories };
  }
  const task = raw as unknown as Task;
  const advisory =
    raw && typeof raw === "object" && "advisory" in raw
      ? (() => {
          const a = (raw as { advisory?: unknown }).advisory;
          if (a && typeof a === "object" && (a as { code?: unknown }).code === "WIP_EXCEEDED") {
            return a as TaskMoveAdvisory;
          }
          return null;
        })()
      : null;
  return { task, advisory, governance_advisories };
}

export function forwardTask(taskId: string, body: TaskForwardRequest): Promise<Task> {
  return api<Task>(`/api/tasks/${taskId}/forward`, { method: "POST", body });
}

export function listDepartments(): Promise<DepartmentSummary[]> {
  return api<DepartmentSummary[]>("/api/departments");
}

export function listDepartmentMembers(departmentId: string): Promise<DepartmentMember[]> {
  return api<DepartmentMember[]>(`/api/departments/${departmentId}/members`);
}

export function deleteTask(taskId: string): Promise<void> {
  return api<void>(`/api/tasks/${taskId}`, { method: "DELETE" });
}

export function listEligibleAssignees(projectId: string): Promise<EligibleAssignee[]> {
  return api<EligibleAssignee[]>(`/api/tasks/projects/${projectId}/eligible-assignees`);
}

export function getTaskDashboard(projectId: string): Promise<TaskDashboard> {
  return api<TaskDashboard>(`/api/tasks/projects/${projectId}/dashboard`);
}

export function getAdminDashboardFlowSummary(
  params: AdminDashboardQueryParams = {},
): Promise<AdminDashboardFlowSummaryResponse> {
  const searchParams = new URLSearchParams();
  appendQuery(searchParams, "start_date", params.start_date);
  appendQuery(searchParams, "end_date", params.end_date);
  appendQuery(searchParams, "department_id", params.department_id);
  appendQuery(searchParams, "workspace_id", params.workspace_id);
  appendQuery(searchParams, "project_id", params.project_id);
  appendQuery(searchParams, "sprint_id", params.sprint_id);
  return api<AdminDashboardFlowSummaryResponse>(withQuery("/api/admin/dashboard/flow-summary", searchParams));
}

export function addTaskAssignees(taskId: string, body: TaskAssigneeRequest): Promise<TaskAssignee[]> {
  return api<TaskAssignee[]>(`/api/tasks/${taskId}/assignees`, { method: "POST", body });
}

export function removeTaskAssignee(taskId: string, employeeId: string): Promise<void> {
  return api<void>(`/api/tasks/${taskId}/assignees/${employeeId}`, { method: "DELETE" });
}

export function createTaskComment(taskId: string, body: TaskCommentCreate): Promise<TaskComment> {
  return api<TaskComment>(`/api/tasks/${taskId}/comments`, { method: "POST", body });
}

export function listTaskComments(taskId: string): Promise<TaskComment[]> {
  return api<TaskComment[]>(`/api/tasks/${taskId}/comments`);
}

export function updateTaskComment(taskId: string, commentId: string, body: TaskCommentUpdate): Promise<TaskComment> {
  return api<TaskComment>(`/api/tasks/${taskId}/comments/${commentId}`, { method: "PATCH", body });
}

export function deleteTaskComment(taskId: string, commentId: string): Promise<void> {
  return api<void>(`/api/tasks/${taskId}/comments/${commentId}`, { method: "DELETE" });
}

export function listTaskActivities(taskId: string): Promise<TaskActivity[]> {
  return api<TaskActivity[]>(`/api/tasks/${taskId}/activities`);
}

export function listTaskAttachments(taskId: string): Promise<TaskAttachment[]> {
  return api<TaskAttachment[]>(`/api/tasks/${taskId}/attachments`);
}

export async function uploadTaskAttachment(taskId: string, file: File): Promise<TaskAttachment> {
  const formData = new FormData();
  formData.append("file", file);
  return apiUpload<TaskAttachment>(`/api/tasks/${taskId}/attachments`, formData);
}

export function downloadTaskAttachment(taskId: string, attachmentId: string): Promise<TaskAttachmentWithPresignedUrl> {
  return api<TaskAttachmentWithPresignedUrl>(`/api/tasks/${taskId}/attachments/${attachmentId}/download`);
}

export function deleteTaskAttachment(taskId: string, attachmentId: string): Promise<void> {
  return api<void>(`/api/tasks/${taskId}/attachments/${attachmentId}`, { method: "DELETE" });
}

export function listNotifications(options: NotificationListOptions = {}): Promise<Notification[]> {
  const params = new URLSearchParams();
  appendQuery(params, "unread_only", options.unread_only);
  appendQuery(params, "limit", options.limit);
  return api<Notification[]>(withQuery("/api/notifications", params));
}

export function getUnreadNotificationCount(): Promise<{ count: number }> {
  return api<{ count: number }>("/api/notifications/unread-count");
}

export function markNotificationRead(notificationId: string): Promise<Notification> {
  return api<Notification>(`/api/notifications/${notificationId}/read`, { method: "POST" });
}

export function markAllNotificationsRead(): Promise<{ updated: number }> {
  return api<{ updated: number }>("/api/notifications/read-all", { method: "POST" });
}

// --- Phase 2 Agile (FEATURE_AGILE_PHASE_2) — Sprint lifecycle. ---
// Mirror of `app/routers/sprint_router.py`. Writes require `task_project:manage`
// permission and the backend feature flag; reads stay open so a partial-rollout
// UI can probe without drowning observability in 403s.

export function createSprint(projectId: string, body: SprintCreate): Promise<Sprint> {
  return api<Sprint>(`/api/task-projects/${projectId}/sprints`, {
    method: "POST",
    body,
  });
}

export function listSprints(projectId: string): Promise<Sprint[]> {
  return api<Sprint[]>(`/api/task-projects/${projectId}/sprints`);
}

export function getSprint(sprintId: string): Promise<Sprint> {
  return api<Sprint>(`/api/sprints/${sprintId}`);
}

export function updateSprint(sprintId: string, body: SprintUpdate): Promise<Sprint> {
  return api<Sprint>(`/api/sprints/${sprintId}`, { method: "PATCH", body });
}

export function startSprint(sprintId: string): Promise<Sprint> {
  return api<Sprint>(`/api/sprints/${sprintId}/start`, { method: "POST" });
}

// Phase 5 (FEATURE_AGILE_PHASE_5) — close sprint may now carry a Stage A
// governance advisory in the response body when the actor lacks
// `agile.sprint.close`. The sprint itself is always returned and the close
// is NEVER blocked; the advisory is purely informational.
export type CloseSprintResult = {
  sprint: Sprint;
  governance_advisories: TaskGovernanceAdvisory[];
};

export async function closeSprint(sprintId: string): Promise<CloseSprintResult> {
  const raw = await api<Record<string, unknown>>(
    `/api/sprints/${sprintId}/close`,
    { method: "POST" },
  );
  const governance_advisories = pickGovernanceAdvisories(raw);
  // The backend dumps the SprintOut shape and tacks on `advisory` when one
  // fires. The advisory field is harmless to leave on the Sprint object —
  // callers can still read `sprint.id`, `sprint.status`, etc.
  const sprint = raw as unknown as Sprint;
  return { sprint, governance_advisories };
}

export function cancelSprint(sprintId: string): Promise<Sprint> {
  return api<Sprint>(`/api/sprints/${sprintId}/cancel`, { method: "POST" });
}

export function deleteSprint(sprintId: string): Promise<void> {
  return api<void>(`/api/sprints/${sprintId}`, { method: "DELETE" });
}

// --- Phase 2 Agile (FEATURE_AGILE_PHASE_2) — Task dependency edges. ---
// Mirror of `app/routers/tasks.py` dependency endpoints. The POST endpoint
// requires `body.from_task_id === task_id` on the server side; the wrapper
// fills it from the URL for callers.

export function addTaskDependency(
  taskId: string,
  toTaskId: string,
  depType: TaskDependencyType = "blocks",
): Promise<TaskDependency> {
  return api<TaskDependency>(`/api/tasks/${taskId}/dependencies`, {
    method: "POST",
    body: {
      from_task_id: taskId,
      to_task_id: toTaskId,
      dep_type: depType,
    },
  });
}

export function removeTaskDependency(taskId: string, toTaskId: string): Promise<void> {
  return api<void>(`/api/tasks/${taskId}/dependencies/${toTaskId}`, {
    method: "DELETE",
  });
}

export function listTaskDependencies(taskId: string): Promise<TaskDependency[]> {
  return api<TaskDependency[]>(`/api/tasks/${taskId}/dependencies`);
}

// --- Phase 2 Agile (FEATURE_AGILE_PHASE_2) — task semantics PATCH wrapper. ---
// Thin convenience over `updateTask` so the call sites that only touch
// Phase 2 fields read naturally. The backend always requires `version` for
// optimistic concurrency; we widen the body type to make all Phase 2 fields
// optional alongside `version`.

export type TaskSemanticsUpdate = Omit<TaskUpdate, "title" | "description" | "priority" | "state_id" | "parent_task_id" | "reporter_id" | "due_date">;

export function updateTaskSemantics(
  taskId: string,
  body: TaskSemanticsUpdate,
): Promise<Task> {
  return api<Task>(`/api/tasks/${taskId}`, { method: "PATCH", body });
}

// --- Phase 3 Agile (FEATURE_AGILE_PHASE_3) — Squad capacity overview. ---
// Mirror of `app/routers/agile_capacity_router.py`. Read-only projection of
// the per-(employee, squad) workload snapshot for a department. Requires
// `org:departments:read` server-side; the feature flag gate lives in the
// router so the wrapper stays a thin pass-through.

export function getSquadCapacity(departmentId: string): Promise<SquadMemberCapacity[]> {
  return api<SquadMemberCapacity[]>(
    `/api/departments/${departmentId}/agile/capacity`,
  );
}

// --- Phase 4 Agile (FEATURE_AGILE_PHASE_4) — task ↔ wiki knowledge links. ---
// Mirror of `app/routers/tasks.py` knowledge-link endpoints. Writes are gated
// server-side on `FEATURE_AGILE_PHASE_4` and yield 403 FEATURE_DISABLED when
// the flag is OFF; reads stay open under the OFF flag so dashboards can
// pre-fetch the link set during a partial rollout without flooding 403s.

export function addKnowledgeLink(
  taskId: string,
  wikiPageId: string,
  linkType: KnowledgeLinkType = "reference",
): Promise<TaskKnowledgeLink> {
  return api<TaskKnowledgeLink>(`/api/tasks/${taskId}/knowledge-links`, {
    method: "POST",
    body: {
      wiki_page_id: wikiPageId,
      link_type: linkType,
    },
  });
}

export function addSourceKnowledgeLink(
  taskId: string,
  sourceId: string,
  linkType: KnowledgeLinkType = "reference",
): Promise<TaskKnowledgeLink> {
  return api<TaskKnowledgeLink>(`/api/tasks/${taskId}/knowledge-links`, {
    method: "POST",
    body: {
      source_id: sourceId,
      link_type: linkType,
    },
  });
}

export function removeKnowledgeLink(
  taskId: string,
  wikiPageId: string,
): Promise<void> {
  return api<void>(`/api/tasks/${taskId}/knowledge-links/${wikiPageId}`, {
    method: "DELETE",
  });
}

export function listKnowledgeLinks(taskId: string): Promise<TaskKnowledgeLink[]> {
  return api<TaskKnowledgeLink[]>(`/api/tasks/${taskId}/knowledge-links`);
}

// --- Phase 4 Agile (FEATURE_AGILE_PHASE_4) — DoR/DoD project templates. ---
// Mirror of `app/routers/tasks.py` template endpoints. The GET endpoint is
// always accessible (a fresh row is materialised on first read so the editor
// never sees `null` arrays); the PUT endpoint is gated and replaces either
// side independently — pass `null` to leave one side unchanged.

export function getProjectTemplate(
  projectId: string,
): Promise<TaskProjectTemplate> {
  return api<TaskProjectTemplate>(
    `/api/tasks/projects/${projectId}/template`,
  );
}

export function updateProjectTemplate(
  projectId: string,
  dorTemplate: string[] | null,
  dodTemplate: string[] | null,
): Promise<TaskProjectTemplate> {
  return api<TaskProjectTemplate>(
    `/api/tasks/projects/${projectId}/template`,
    {
      method: "PUT",
      body: {
        dor_template: dorTemplate,
        dod_template: dodTemplate,
      },
    },
  );
}

// --- Phase 5 Agile (FEATURE_AGILE_PHASE_5) — flow metrics + throughput. ---
// Mirror of `app/routers/flow_metrics_router.py`. Both endpoints are
// read-only and gated server-side on `FEATURE_AGILE_PHASE_5`. The flag is
// also OFF on the frontend by default, so the calls are made only from
// components that already check `FEATURE_AGILE_PHASE_5`.
//
// `start_date` / `end_date` are ISO date strings (`YYYY-MM-DD`); FastAPI
// parses them into `datetime.date`. Time-of-day is ignored on the wire.

export function getFlowMetrics(
  projectId: string,
  startDate: string,
  endDate: string,
): Promise<TaskFlowSnapshot[]> {
  const params = new URLSearchParams();
  params.set("start_date", startDate);
  params.set("end_date", endDate);
  return api<TaskFlowSnapshot[]>(
    `/api/task-projects/${projectId}/flow-metrics?${params.toString()}`,
  );
}

export function getThroughput(
  projectId: string,
  startDate: string,
  endDate: string,
): Promise<FlowThroughput> {
  const params = new URLSearchParams();
  params.set("start_date", startDate);
  params.set("end_date", endDate);
  return api<FlowThroughput>(
    `/api/task-projects/${projectId}/throughput?${params.toString()}`,
  );
}

export type {
  DashboardAssigneeItem,
  DashboardStateItem,
  DueSoonItem,
  EligibleAssignee,
  FlowThroughput,
  KnowledgeLinkType,
  Notification,
  PaginatedResponse,
  SquadMemberCapacity,
  Sprint,
  SprintCreate,
  SprintUpdate,
  Task,
  TaskActivity,
  TaskAssignee,
  TaskAttachment,
  TaskAttachmentWithPresignedUrl,
  TaskComment,
  TaskDashboard,
  TaskDependency,
  TaskDependencyType,
  TaskFlowSnapshot,
  TaskGovernanceAdvisory,
  TaskKnowledgeLink,
  TaskLabel,
  TaskMoveAdvisory,
  TaskMoveResult,
  TaskPriority,
  TaskProject,
  TaskProjectTemplate,
  TaskState,
};
