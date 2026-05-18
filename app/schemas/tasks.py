"""Pydantic DTOs for the native task management module."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.habits import (
    CalendarWeekResponse as HabitCalendarWeekResponse,
)
from app.schemas.habits import (
    DashboardOverviewResponse as HabitDashboardOverviewResponse,
)
from app.services.task_constants import (
    DEFAULT_STATE_GROUPS,
    ESTIMATE_SIZES,
    KNOWLEDGE_LINK_TYPES,
    MAX_DESCRIPTION_BYTES,
    PRIORITY_LEVELS,
    SPRINT_STATUSES,
    TASK_TYPES,
    WIP_POLICIES,
)

CalendarWeekResponse = HabitCalendarWeekResponse
DashboardOverviewResponse = HabitDashboardOverviewResponse

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class TaskProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    identifier: str = Field(..., min_length=1, max_length=10, pattern=r"^[A-Z0-9_]+$")
    workspace_id: Optional[uuid.UUID] = None
    department_id: Optional[uuid.UUID] = None
    allow_any_employee: bool = False

    @field_validator("identifier", mode="before")
    @classmethod
    def identifier_uppercase(cls, v: str) -> str:
        return v.upper()


class TaskProjectUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    allow_any_employee: Optional[bool] = None
    is_archived: Optional[bool] = None


class TaskProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str]
    identifier: str
    workspace_id: Optional[uuid.UUID]
    department_id: Optional[uuid.UUID]
    allow_any_employee: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class TaskStateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    group: str
    color: Optional[str] = None
    position: float = 0.0
    wip_limit: Optional[int] = Field(None, ge=0)
    wip_policy: Optional[str] = None
    aging_warn_days: Optional[int] = Field(None, ge=0)

    @field_validator("group")
    @classmethod
    def group_valid(cls, v: str) -> str:
        if v not in DEFAULT_STATE_GROUPS:
            raise ValueError(f"group must be one of {DEFAULT_STATE_GROUPS}")
        return v

    @field_validator("wip_policy")
    @classmethod
    def wip_policy_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in WIP_POLICIES:
            raise ValueError(f"wip_policy must be one of {WIP_POLICIES}")
        return v


class TaskStateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = None
    position: Optional[float] = None
    wip_limit: Optional[int] = Field(None, ge=0)
    wip_policy: Optional[str] = None
    aging_warn_days: Optional[int] = Field(None, ge=0)

    @field_validator("wip_policy")
    @classmethod
    def wip_policy_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in WIP_POLICIES:
            raise ValueError(f"wip_policy must be one of {WIP_POLICIES}")
        return v


class TaskStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_project_id: uuid.UUID
    name: str
    group: str
    color: Optional[str]
    position: float
    wip_limit: Optional[int] = None
    wip_policy: Optional[str] = None
    aging_warn_days: Optional[int] = None
    is_default: bool
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    priority: str = "none"
    # Optional: if omitted, the router fills it with the project's first
    # (default) state. This is what makes scope-based task creation work — the
    # user does not need to know the project's states in advance.
    state_id: Optional[uuid.UUID] = None
    parent_task_id: Optional[uuid.UUID] = None
    reporter_id: Optional[uuid.UUID] = None
    due_date: Optional[datetime] = None
    scheduled_start_at: Optional[datetime] = None
    scheduled_end_at: Optional[datetime] = None
    schedule_locked: bool = False
    assignee_ids: list[uuid.UUID] = Field(default_factory=list)
    label_ids: list[uuid.UUID] = Field(default_factory=list)
    # --- Phase 2 Agile semantics (optional; gated by FEATURE_AGILE_PHASE_2). ---
    task_type: Optional[str] = None
    estimate: Optional[str] = None
    story_points: Optional[int] = Field(default=None, ge=0)
    acceptance_criteria: Optional[str] = None
    # DoR/DoD: omit to snapshot from the project template; pass to override.
    dor_checklist: Optional[list[Any]] = None
    dod_checklist: Optional[list[Any]] = None
    sprint_id: Optional[uuid.UUID] = None

    @field_validator("priority")
    @classmethod
    def priority_valid(cls, v: str) -> str:
        if v not in PRIORITY_LEVELS:
            raise ValueError(f"priority must be one of {PRIORITY_LEVELS}")
        return v

    @field_validator("description")
    @classmethod
    def description_size(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
            raise ValueError(f"description exceeds {MAX_DESCRIPTION_BYTES} bytes")
        return v

    @field_validator("task_type")
    @classmethod
    def task_type_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in TASK_TYPES:
            raise ValueError(f"task_type must be one of {TASK_TYPES}")
        return v

    @field_validator("estimate")
    @classmethod
    def estimate_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ESTIMATE_SIZES:
            raise ValueError(f"estimate must be one of {ESTIMATE_SIZES}")
        return v


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    priority: Optional[str] = None
    task_project_id: Optional[uuid.UUID] = None
    state_id: Optional[uuid.UUID] = None
    parent_task_id: Optional[uuid.UUID] = None
    reporter_id: Optional[uuid.UUID] = None
    due_date: Optional[datetime] = None
    scheduled_start_at: Optional[datetime] = None
    scheduled_end_at: Optional[datetime] = None
    schedule_locked: Optional[bool] = None
    # --- Phase 2 Agile semantics. ---
    task_type: Optional[str] = None
    estimate: Optional[str] = None
    story_points: Optional[int] = Field(default=None, ge=0)
    acceptance_criteria: Optional[str] = None
    dor_checklist: Optional[list[Any]] = None
    dod_checklist: Optional[list[Any]] = None
    blocked_reason: Optional[str] = None
    blocked_by_id: Optional[uuid.UUID] = None
    sprint_id: Optional[uuid.UUID] = None
    version: int

    @field_validator("priority")
    @classmethod
    def priority_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in PRIORITY_LEVELS:
            raise ValueError(f"priority must be one of {PRIORITY_LEVELS}")
        return v

    @field_validator("description")
    @classmethod
    def description_size(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
            raise ValueError(f"description exceeds {MAX_DESCRIPTION_BYTES} bytes")
        return v

    @field_validator("task_type")
    @classmethod
    def task_type_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in TASK_TYPES:
            raise ValueError(f"task_type must be one of {TASK_TYPES}")
        return v

    @field_validator("estimate")
    @classmethod
    def estimate_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ESTIMATE_SIZES:
            raise ValueError(f"estimate must be one of {ESTIMATE_SIZES}")
        return v


class TaskMoveRequest(BaseModel):
    state_id: uuid.UUID
    position: float
    version: int


class TaskForwardRequest(BaseModel):
    """Forward (chuyển tiếp) a task to another assignee, optionally in another department."""

    target_department_id: Optional[uuid.UUID] = None
    new_assignee_id: uuid.UUID
    reason: str = Field(..., min_length=10)
    keep_previous_assignees: bool = False
    version: int

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, v: str) -> str:
        if len(v.strip()) < 10:
            raise ValueError("reason must be at least 10 non-whitespace characters")
        return v


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_project_id: uuid.UUID
    state_id: uuid.UUID
    title: str
    description: Optional[str]
    priority: str
    parent_task_id: Optional[uuid.UUID]
    reporter_id: Optional[uuid.UUID]
    created_by_id: Optional[uuid.UUID]
    position: float
    version: int
    due_date: Optional[datetime]
    scheduled_start_at: Optional[datetime]
    scheduled_end_at: Optional[datetime]
    schedule_locked: bool
    completed_at: Optional[datetime]
    deleted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    # --- Phase 2 Agile semantics (always emitted; null until set). ---
    task_type: Optional[str] = None
    estimate: Optional[str] = None
    story_points: Optional[int] = None
    acceptance_criteria: Optional[str] = None
    dor_checklist: Optional[list[Any]] = None
    dod_checklist: Optional[list[Any]] = None
    blocked_reason: Optional[str] = None
    blocked_at: Optional[datetime] = None
    blocked_by_id: Optional[uuid.UUID] = None
    sprint_id: Optional[uuid.UUID] = None


TaskRead = TaskOut


class SprintCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    goal: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: str = "planned"

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str) -> str:
        if v not in SPRINT_STATUSES:
            raise ValueError(f"status must be one of {SPRINT_STATUSES}")
        return v


class SprintUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    goal: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SPRINT_STATUSES:
            raise ValueError(f"status must be one of {SPRINT_STATUSES}")
        return v


class SprintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_project_id: uuid.UUID
    name: str
    goal: Optional[str]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    status: str
    created_at: datetime
    updated_at: datetime


class TaskDependencyCreate(BaseModel):
    """Request payload for ``POST /tasks/{task_id}/dependencies``.

    ``from_task_id`` is implied by the URL path on the router; we still
    accept it in the body so the service layer (and direct callers) stay
    URL-agnostic. The router cross-checks the two before delegating.
    """

    from_task_id: uuid.UUID
    to_task_id: uuid.UUID
    dep_type: str = "blocks"

    @field_validator("dep_type")
    @classmethod
    def dep_type_valid(cls, v: str) -> str:
        # Phase 2 only knows "blocks"; reject anything else explicitly so the
        # column never grows a verb that the cycle-check logic does not
        # understand. Later phases can widen this set.
        if v != "blocks":
            raise ValueError("dep_type must be 'blocks' in Phase 2")
        return v


class TaskDependencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_task_id: uuid.UUID
    to_task_id: uuid.UUID
    dep_type: str
    created_by_id: Optional[uuid.UUID]
    created_at: datetime


class TaskKnowledgeLinkCreate(BaseModel):
    """Request payload for ``POST /tasks/{task_id}/knowledge-links``.

    ``task_id`` is implied by the URL path; the body must reference exactly one
    knowledge target: either a compiled wiki page or a raw source document.
    ``link_type`` defaults to ``reference`` so the simplest "this is relevant"
    flow stays a one-field POST.
    """

    wiki_page_id: Optional[uuid.UUID] = None
    source_id: Optional[uuid.UUID] = None
    link_type: str = "reference"

    @field_validator("link_type")
    @classmethod
    def link_type_valid(cls, v: str) -> str:
        if v not in KNOWLEDGE_LINK_TYPES:
            raise ValueError(f"link_type must be one of {KNOWLEDGE_LINK_TYPES}")
        return v

    @model_validator(mode="after")
    def exactly_one_target(self) -> "TaskKnowledgeLinkCreate":
        if (self.wiki_page_id is None) == (self.source_id is None):
            raise ValueError("exactly one of wiki_page_id or source_id must be set")
        return self


class TaskKnowledgeLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    wiki_page_id: Optional[uuid.UUID]
    source_id: Optional[uuid.UUID]
    link_type: str
    created_by_id: Optional[uuid.UUID]
    created_at: datetime


class TaskFlowSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_project_id: uuid.UUID
    snapshot_date: date
    state_id: Optional[uuid.UUID]
    task_count: int
    story_points_sum: Optional[int]
    blocked_count: int
    created_at: datetime


class ThroughputOut(BaseModel):
    tasks_completed: int
    story_points_completed: int


class TaskProjectTemplateUpdate(BaseModel):
    dor_template: Optional[list[Any]] = None
    dod_template: Optional[list[Any]] = None


class TaskProjectTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_project_id: uuid.UUID
    dor_template: list[Any]
    dod_template: list[Any]
    created_at: datetime
    updated_at: datetime


class TaskLabelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = None
    description: Optional[str] = None


class TaskLabelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_project_id: uuid.UUID
    name: str
    color: Optional[str]
    description: Optional[str]
    created_at: datetime


class TaskCommentCreate(BaseModel):
    body: str = Field(..., min_length=1)


class TaskCommentUpdate(BaseModel):
    body: str = Field(..., min_length=1)


class TaskCommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    author_id: Optional[uuid.UUID]
    body: str
    is_edited: bool
    deleted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class TaskAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    uploaded_by_id: Optional[uuid.UUID]
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime
    # NOTE: storage_key is NOT included — use presigned URL endpoint
    presigned_url: Optional[str] = None  # populated by router, not ORM


class TaskActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_id: uuid.UUID
    actor_id: Optional[uuid.UUID]
    verb: str
    field_name: Optional[str]
    old_value: Optional[str]
    new_value: Optional[str]
    meta: Optional[dict[str, Any]]
    created_at: datetime


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipient_id: uuid.UUID
    actor_id: Optional[uuid.UUID]
    notification_type: str
    task_id: Optional[uuid.UUID]
    title: str
    body: Optional[str]
    is_read: bool
    read_at: Optional[datetime]
    created_at: datetime


class TaskAssigneeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: uuid.UUID
    employee_id: uuid.UUID
    assigned_at: datetime


class DashboardStateItem(BaseModel):
    state_id: uuid.UUID
    state_name: str
    group: str
    count: int


class DashboardAssigneeItem(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    count: int


class DueSoonItem(BaseModel):
    id: uuid.UUID
    title: str
    priority: str
    due_date: Optional[datetime]
    state_name: str


class DashboardOut(BaseModel):
    by_state: list[DashboardStateItem]
    by_assignee: list[DashboardAssigneeItem]
    overdue_count: int
    due_this_week: list[DueSoonItem]
    total_tasks: int


class AdminDashboardCfdPoint(BaseModel):
    snapshot_date: date
    state_counts: dict[str, int] = Field(default_factory=dict)
    blocked_count: int = 0


class AdminDashboardAgingTaskItem(BaseModel):
    task_id: Optional[uuid.UUID] = None
    title: str
    state_name: str
    aging_days: int
    priority: Optional[str] = None
    assignee_names: list[str] = Field(default_factory=list)


class AdminDashboardThroughputPoint(BaseModel):
    period_start: date
    period_end: date
    tasks_completed: int = 0
    story_points_completed: int = 0


class AdminDashboardChartSeries(BaseModel):
    cfd_series: list[AdminDashboardCfdPoint] = Field(default_factory=list)
    aging_tasks: list[AdminDashboardAgingTaskItem] = Field(default_factory=list)
    throughput_series: list[AdminDashboardThroughputPoint] = Field(default_factory=list)


class AdminDashboardRiskItem(BaseModel):
    id: str
    title: str
    severity: str
    count: int = 0
    description: Optional[str] = None


class AdminDashboardCapacityItem(BaseModel):
    id: str
    label: str
    capacity_percent: Optional[int] = None
    open_task_count: int = 0
    story_points_sum: Optional[int] = None
    is_overloaded: bool = False


class AdminDashboardFlowSummaryResponse(BaseModel):
    feature_enabled: bool
    as_of: datetime
    approximation_used: bool
    scoped_project_count: int
    wip_count: int
    blocked_count: int
    aging_count: int
    throughput_count: int
    cycle_time_p50: float
    lead_time_p50: float
    chart_series: AdminDashboardChartSeries = Field(
        default_factory=AdminDashboardChartSeries
    )
    risk_items: list[AdminDashboardRiskItem] = Field(default_factory=list)
    capacity_items: list[AdminDashboardCapacityItem] = Field(default_factory=list)


class SquadMemberCapacityOut(BaseModel):
    """Wire format for Phase 3 squad capacity rows.

    Mirrors :class:`app.services.task_dashboard_service.SquadMemberCapacity`.
    One row per (employee, squad). Multi-squad users yield independent rows
    per squad and are never aggregated.
    """

    model_config = ConfigDict(from_attributes=True)

    employee_id: uuid.UUID
    employee_name: str
    department_id: uuid.UUID
    squad_name: str
    capacity_percent: Optional[int] = None
    open_task_count: int
    story_points_sum: Optional[int] = None
    is_overloaded: bool


TaskCreate = TaskCreate
TaskUpdate = TaskUpdate
