import { api, apiUpload } from "@/lib/api";
import type {
  DashboardAssigneeItem,
  DashboardStateItem,
  DepartmentMember,
  DepartmentSummary,
  DueSoonItem,
  EligibleAssignee,
  Notification,
  NotificationListOptions,
  PaginatedResponse,
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
  TaskFilters,
  TaskForwardRequest,
  TaskLabel,
  TaskLabelCreate,
  TaskLabelUpdate,
  TaskMoveRequest,
  TaskPriority,
  TaskProject,
  TaskProjectCreate,
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

export function moveTask(taskId: string, body: TaskMoveRequest): Promise<Task> {
  return api<Task>(`/api/tasks/${taskId}/move`, { method: "POST", body });
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

export type {
  DashboardAssigneeItem,
  DashboardStateItem,
  DueSoonItem,
  EligibleAssignee,
  Notification,
  PaginatedResponse,
  Task,
  TaskActivity,
  TaskAssignee,
  TaskAttachment,
  TaskAttachmentWithPresignedUrl,
  TaskComment,
  TaskDashboard,
  TaskLabel,
  TaskPriority,
  TaskProject,
  TaskState,
};
