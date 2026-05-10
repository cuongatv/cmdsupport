"""Pydantic DTOs for the native task management module."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.task_constants import (
    DEFAULT_STATE_GROUPS,
    MAX_DESCRIPTION_BYTES,
    PRIORITY_LEVELS,
)

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

    @field_validator("group")
    @classmethod
    def group_valid(cls, v: str) -> str:
        if v not in DEFAULT_STATE_GROUPS:
            raise ValueError(f"group must be one of {DEFAULT_STATE_GROUPS}")
        return v


class TaskStateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = None
    position: Optional[float] = None


class TaskStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_project_id: uuid.UUID
    name: str
    group: str
    color: Optional[str]
    position: float
    is_default: bool
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    priority: str = "none"
    state_id: uuid.UUID
    parent_task_id: Optional[uuid.UUID] = None
    reporter_id: Optional[uuid.UUID] = None
    due_date: Optional[datetime] = None
    assignee_ids: list[uuid.UUID] = Field(default_factory=list)
    label_ids: list[uuid.UUID] = Field(default_factory=list)

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


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    priority: Optional[str] = None
    state_id: Optional[uuid.UUID] = None
    parent_task_id: Optional[uuid.UUID] = None
    reporter_id: Optional[uuid.UUID] = None
    due_date: Optional[datetime] = None
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


class TaskMoveRequest(BaseModel):
    state_id: uuid.UUID
    position: float
    version: int


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
    completed_at: Optional[datetime]
    deleted_at: Optional[datetime]
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
