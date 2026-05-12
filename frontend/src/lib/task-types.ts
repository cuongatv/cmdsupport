export type TaskPriority = "none" | "low" | "medium" | "high" | "urgent";

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type TaskProject = {
  id: string;
  name: string;
  description: string | null;
  identifier: string;
  workspace_id: string | null;
  department_id: string | null;
  allow_any_employee: boolean;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
};

export type TaskState = {
  id: string;
  task_project_id: string;
  name: string;
  group: string;
  color: string | null;
  position: number;
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

export type TaskLabel = {
  id: string;
  task_project_id: string;
  name: string;
  color: string | null;
  description: string | null;
  created_at: string;
};

export type Task = {
  id: string;
  task_project_id: string;
  state_id: string;
  title: string;
  description: string | null;
  priority: TaskPriority;
  parent_task_id: string | null;
  reporter_id: string | null;
  created_by_id: string | null;
  position: number;
  version: number;
  due_date: string | null;
  completed_at: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TaskAssignee = {
  task_id: string;
  employee_id: string;
  assigned_at: string;
};

export type TaskComment = {
  id: string;
  task_id: string;
  author_id: string | null;
  body: string;
  is_edited: boolean;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TaskAttachment = {
  id: string;
  task_id: string;
  uploaded_by_id: string | null;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  presigned_url: string | null;
};

export type TaskAttachmentWithPresignedUrl = Omit<TaskAttachment, "presigned_url"> & {
  presigned_url: string;
};

export type TaskActivity = {
  id: string;
  task_id: string;
  actor_id: string | null;
  verb: string;
  field_name: string | null;
  old_value: string | null;
  new_value: string | null;
  meta: Record<string, unknown> | null;
  created_at: string;
};

export type Notification = {
  id: string;
  recipient_id: string;
  actor_id: string | null;
  notification_type: string;
  task_id: string | null;
  title: string;
  body: string | null;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
};

export type EligibleAssignee = {
  id: string;
  name: string;
  email: string;
  department_id: string | null;
};

export type DashboardStateItem = {
  state_id: string;
  state_name: string;
  group: string;
  count: number;
};

export type DashboardAssigneeItem = {
  employee_id: string;
  employee_name: string;
  count: number;
};

export type DueSoonItem = {
  id: string;
  title: string;
  priority: TaskPriority;
  due_date: string | null;
  state_name: string;
};

export type TaskDashboard = {
  by_state: DashboardStateItem[];
  by_assignee: DashboardAssigneeItem[];
  overdue_count: number;
  due_this_week: DueSoonItem[];
  total_tasks: number;
};

export type TaskStatus = {
  native: boolean;
};

export type TaskProjectCreate = {
  name: string;
  description?: string | null;
  identifier: string;
  workspace_id?: string | null;
  department_id?: string | null;
  allow_any_employee?: boolean;
};

export type TaskProjectUpdate = {
  name?: string | null;
  description?: string | null;
  allow_any_employee?: boolean;
  is_archived?: boolean;
};

export type TaskStateCreate = {
  name: string;
  group: string;
  color?: string | null;
  position?: number;
};

export type TaskStateUpdate = {
  name?: string | null;
  color?: string | null;
  position?: number | null;
};

export type TaskLabelCreate = {
  name: string;
  color?: string | null;
  description?: string | null;
};

export type TaskLabelUpdate = {
  name?: string | null;
  color?: string | null;
  description?: string | null;
};

export type TaskCreate = {
  title: string;
  description?: string | null;
  priority?: TaskPriority;
  // Optional: when omitted (scope-based create flow) the backend fills it with
  // the resolved project's default state.
  state_id?: string | null;
  parent_task_id?: string | null;
  reporter_id?: string | null;
  due_date?: string | null;
  assignee_ids?: string[];
  label_ids?: string[];
};

export type TaskScope =
  | { workspace_id: string }
  | { department_id: string };

export type TaskUpdate = {
  title?: string | null;
  description?: string | null;
  priority?: TaskPriority | null;
  state_id?: string | null;
  parent_task_id?: string | null;
  reporter_id?: string | null;
  due_date?: string | null;
  version: number;
};

export type TaskMoveRequest = {
  state_id: string;
  position: number;
  version: number;
};

export type TaskCommentCreate = {
  body: string;
};

export type TaskCommentUpdate = {
  body: string;
};

export type TaskAssigneeRequest = {
  employee_ids: string[];
};

export type TaskFilters = {
  // Exactly one of task_project_id OR (workspace_id xor department_id) is
  // required. Scope mode lets the caller list tasks across every accessible
  // project in a Phòng ban / Không gian làm việc without picking a project.
  task_project_id?: string;
  workspace_id?: string;
  department_id?: string;
  search?: string;
  state_id?: string;
  assignee_id?: string;
  reporter_id?: string;
  priority?: TaskPriority;
  label_id?: string;
  due_from?: string;
  due_to?: string;
  overdue?: boolean;
  include_deleted?: boolean;
  page?: number;
  page_size?: number;
  sort_by?: "created_at" | "updated_at" | "due_date" | "priority" | "title" | "position";
  sort_dir?: "asc" | "desc";
};

export type NotificationListOptions = {
  unread_only?: boolean;
  limit?: number;
};

export function formatTaskDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium" }).format(date);
}

export function formatTaskDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
