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

// Phase 1 (FEATURE_AGILE_PHASE_1): three additive, nullable WIP / aging
// columns on TaskState. The backend always returns them — they are `null`
// when the column has no limit / policy configured. Keep these typed as
// `number | null` (not `number | undefined`) to match the JSON the backend
// actually emits (see `app/schemas/tasks.py::TaskStateOut`).
export type WipPolicy = "off" | "warn" | "enforce";

export type TaskState = {
  id: string;
  task_project_id: string;
  name: string;
  group: string;
  color: string | null;
  position: number;
  is_default: boolean;
  wip_limit: number | null;
  wip_policy: WipPolicy | null;
  aging_warn_days: number | null;
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

// Phase 2 (FEATURE_AGILE_PHASE_2) — Vietnamese task semantics. The backend
// emits these fields on every TaskOut payload (null until set), so the type
// matches the wire and does not need a separate "extended task" alias.
export type TaskType = "story" | "task" | "bug" | "epic" | "spike";
export type EstimateSize = "xs" | "s" | "m" | "l" | "xl";

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
  // Phase 2 Agile semantics. Always present on TaskOut; `null`/`undefined`
  // means "not set" — keep optional in the type so legacy callers that
  // accept a `Task` (e.g. unit fixtures) do not break.
  task_type?: TaskType | null;
  estimate?: EstimateSize | null;
  story_points?: number | null;
  acceptance_criteria?: string | null;
  dor_checklist?: unknown[] | null;
  dod_checklist?: unknown[] | null;
  blocked_reason?: string | null;
  blocked_at?: string | null;
  blocked_by_id?: string | null;
  sprint_id?: string | null;
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
  // Phase 1 (FEATURE_AGILE_PHASE_1). The backend gates these fields: when the
  // flag is OFF, sending them yields 403 FEATURE_DISABLED. Keep them optional
  // so legacy callers stay backward compatible.
  wip_limit?: number | null;
  wip_policy?: WipPolicy | null;
  aging_warn_days?: number | null;
};

export type TaskStateUpdate = {
  name?: string | null;
  color?: string | null;
  position?: number | null;
  wip_limit?: number | null;
  wip_policy?: WipPolicy | null;
  aging_warn_days?: number | null;
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
  // Phase 2 Agile semantics. All optional — only fields the caller passes
  // are mutated server-side (the backend uses `model_dump(exclude_unset=True)`).
  // `blocked_reason: null` is an explicit unblock signal, NOT "leave unchanged".
  task_type?: TaskType | null;
  estimate?: EstimateSize | null;
  story_points?: number | null;
  acceptance_criteria?: string | null;
  dor_checklist?: unknown[] | null;
  dod_checklist?: unknown[] | null;
  blocked_reason?: string | null;
  blocked_by_id?: string | null;
  sprint_id?: string | null;
  version: number;
};

export type TaskMoveRequest = {
  state_id: string;
  position: number;
  version: number;
};

// Phase 1 advisory contract. Backend returns this in the move response when
// the target state has `wip_policy='warn'` and the move would exceed
// `wip_limit`. The move still succeeds — the toast is purely informational.
// `policy='enforce'` is a hard reject and surfaces as a 409 (see ApiError),
// NOT as an advisory.
export type TaskMoveAdvisory = {
  code: "WIP_EXCEEDED";
  policy: "warn";
  state_id: string;
  wip_limit: number;
  current_count: number;
};

export type TaskMoveResult = {
  task: Task;
  advisory: TaskMoveAdvisory | null;
  // Phase 5 (FEATURE_AGILE_PHASE_5) — zero or more governance advisories
  // emitted when the actor lacks an `agile.*` permission. Always an array
  // (possibly empty) so call sites can iterate without null checks.
  governance_advisories: TaskGovernanceAdvisory[];
};

export type TaskForwardRequest = {
  /** Null => same-unit forward; server infers source department. */
  target_department_id: string | null;
  new_assignee_id: string;
  /** Required by backend, min 10 non-whitespace chars. */
  reason: string;
  keep_previous_assignees?: boolean;
  version: number;
};

export type DepartmentSummary = {
  id: string;
  name: string;
  unit_type?: string;
  is_archived?: boolean;
};

export type DepartmentMember = {
  id: string;
  employee_id: string;
  department_id: string;
  role: string;
  capacity_percent: number | null;
  is_primary: boolean;
  is_active: boolean;
  employee_name: string | null;
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

// Phase 2 (FEATURE_AGILE_PHASE_2) — lightweight Sprint entity. Mirrors
// `app/schemas/tasks.py::SprintOut`. `start_date` / `end_date` are emitted as
// ISO strings (the backend column is `date`, but the schema is `datetime`).
export type SprintStatus = "planned" | "active" | "completed" | "cancelled";

export type Sprint = {
  id: string;
  task_project_id: string;
  name: string;
  goal: string | null;
  start_date: string | null;
  end_date: string | null;
  status: SprintStatus;
  created_at: string;
  updated_at: string;
};

export type SprintCreate = {
  name: string;
  goal?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status?: SprintStatus;
};

export type SprintUpdate = {
  name?: string | null;
  goal?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  status?: SprintStatus | null;
};

// Phase 2 (FEATURE_AGILE_PHASE_2) — task dependency edges. Phase 2 only
// understands `"blocks"`; future phases may widen the set.
export type TaskDependencyType = "blocks" | "relates_to" | "duplicates";

export type TaskDependency = {
  id: string;
  from_task_id: string;
  to_task_id: string;
  dep_type: TaskDependencyType;
  created_by_id: string | null;
  created_at: string;
};

// Phase 3 (FEATURE_AGILE_PHASE_3) — per-(employee, squad) capacity snapshot
// surfaced by `GET /api/departments/{department_id}/agile/capacity`. Mirror
// of `app/schemas/tasks.py::SquadMemberCapacityOut`. `story_points_sum` is
// `null` when none of the member's open tasks carry a story-point estimate;
// the backend deliberately distinguishes "no estimates" from "estimated 0".
export type SquadMemberCapacity = {
  employee_id: string;
  employee_name: string;
  department_id: string;
  squad_name: string;
  capacity_percent: number;
  open_task_count: number;
  story_points_sum: number | null;
  is_overloaded: boolean;
};

// Phase 4 (FEATURE_AGILE_PHASE_4) — task ↔ wiki/source knowledge links.
// Mirror of `app/schemas/tasks.py::TaskKnowledgeLinkOut`. `link_type`
// is open-ended on the wire (`str` in the schema) but the backend
// `KNOWLEDGE_LINK_TYPES` constant restricts it to these four values;
// keep the UI type narrow so callers get exhaustiveness checks.
export type KnowledgeLinkType = "reference" | "solution" | "blocker" | "related";

export type TaskKnowledgeLink = {
  id: string;
  task_id: string;
  wiki_page_id: string | null;
  source_id: string | null;
  link_type: KnowledgeLinkType;
  created_by_id: string | null;
  created_at: string;
};

// Phase 4 (FEATURE_AGILE_PHASE_4) — DoR/DoD checklist template for a
// task project. Mirror of `app/schemas/tasks.py::TaskProjectTemplateOut`.
// The backend declares the arrays as `list[Any]` (each entry is a free-form
// checklist item), but the Phase 4 UI authors them as Vietnamese strings,
// so the frontend type narrows to `string[]` for ergonomics.
export type TaskProjectTemplate = {
  task_project_id: string;
  dor_template: string[];
  dod_template: string[];
  created_at: string;
  updated_at: string;
};

// Phase 5 (FEATURE_AGILE_PHASE_5) — flow snapshot row returned by
// `GET /api/task-projects/{id}/flow-metrics`. Mirror of
// `app/schemas/tasks.py::TaskFlowSnapshotOut`. `state_id` is nullable for
// rows that aggregate across all states (the current capture path never
// emits null, but keep the type permissive to match the schema).
export type TaskFlowSnapshot = {
  id: string;
  task_project_id: string;
  snapshot_date: string;
  state_id: string | null;
  task_count: number;
  story_points_sum: number | null;
  blocked_count: number;
  created_at: string;
};

// Phase 5 (FEATURE_AGILE_PHASE_5) — throughput projection returned by
// `GET /api/task-projects/{id}/throughput`. Mirror of
// `app/schemas/tasks.py::ThroughputOut`. Both counters are integer totals
// for the requested date range; the backend zero-fills when nothing closed.
export type FlowThroughput = {
  tasks_completed: number;
  story_points_completed: number;
};

// Phase 5 (FEATURE_AGILE_PHASE_5) — admin dashboard flow summary chart series.
// Mirrors `app/schemas/tasks.py` so the frontend can render the dashboard
// without hand-written shape conversions.
export type CfdDataPoint = {
  snapshot_date: string;
  state_counts: Record<string, number>;
  blocked_count: number;
};

export type AgingTaskItem = {
  task_id: string | null;
  title: string;
  state_name: string;
  aging_days: number;
  priority: string | null;
  assignee_names: string[];
};

export type ThroughputDataPoint = {
  period_start: string;
  period_end: string;
  tasks_completed: number;
  story_points_completed: number;
};

export type RiskItem = {
  id: string;
  title: string;
  severity: string;
  count: number;
  description: string | null;
};

export type CapacityItem = {
  id: string;
  label: string;
  capacity_percent: number | null;
  open_task_count: number;
  story_points_sum: number | null;
  is_overloaded: boolean;
};

export type AdminDashboardChartSeries = {
  cfd_series: CfdDataPoint[];
  aging_tasks: AgingTaskItem[];
  throughput_series: ThroughputDataPoint[];
};

export type AdminDashboardRiskItem = RiskItem;
export type AdminDashboardCapacityItem = CapacityItem;
export type AdminDashboardCfdPoint = CfdDataPoint;
export type AdminDashboardAgingTaskItem = AgingTaskItem;
export type AdminDashboardThroughputPoint = ThroughputDataPoint;

export type AdminDashboardKPI = {
  wip_count: number;
  blocked_count: number;
  aging_count: number;
  throughput_count: number;
  cycle_time_p50: number;
  lead_time_p50: number;
};

export type AdminDashboardFlowSummaryResponse = AdminDashboardKPI & {
  feature_enabled: boolean;
  as_of: string;
  approximation_used: boolean;
  scoped_project_count: number;
  chart_series: AdminDashboardChartSeries;
  risk_items: AdminDashboardRiskItem[];
  capacity_items: AdminDashboardCapacityItem[];
};

// Phase 5 (FEATURE_AGILE_PHASE_5) — Stage A governance advisory. Surfaces
// in task move + sprint close response bodies when the actor lacks the
// relevant `agile.*` permission. The mutation is NEVER blocked — the toast
// is purely informational ("thao tác vẫn được ghi nhận"). Mirrors the
// `{"code", "permission"}` shape produced by
// `app/services/agile_governance.maybe_record_permission_advisory`.
export type TaskGovernanceAdvisory = {
  code: "PERMISSION_DENIED_ADVISORY";
  permission: string;
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
