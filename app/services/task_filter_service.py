"""Advanced task filtering service for the native task module."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    Employee,
    Task,
    TaskAssignee,
    TaskLabelLink,
    TaskProject,
    TaskState,
)
from app.services.task_access_service import can_access_task_project

TaskSortField = Literal["created_at", "updated_at", "due_date", "priority", "title", "position"]
TaskSortDirection = Literal["asc", "desc"]


@dataclass(frozen=True)
class TaskFilters:
    search: str | None = None
    state_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = None
    reporter_id: uuid.UUID | None = None
    priority: str | None = None
    label_id: uuid.UUID | None = None
    due_from: datetime | None = None
    due_to: datetime | None = None
    overdue: bool = False
    include_deleted: bool = False
    page: int = 1
    page_size: int = 20
    sort_by: TaskSortField = "created_at"
    sort_dir: TaskSortDirection = "desc"


async def filter_tasks(
    db: AsyncSession,
    employee: Employee,
    task_project: TaskProject,
    filters: TaskFilters,
) -> tuple[list[Task], int]:
    """Return tasks and total count matching additive filters within an accessible project."""
    if not await can_access_task_project(db, employee, task_project):
        return [], 0

    return await _filter_tasks_in_projects(
        db, [task_project.id], filters
    )


async def filter_tasks_in_projects(
    db: AsyncSession,
    project_ids: list[uuid.UUID],
    filters: TaskFilters,
) -> tuple[list[Task], int]:
    """Return tasks/total across a set of already-authorized project ids.

    Used by scope-based listing (Phòng ban / Không gian làm việc) so the caller
    can resolve scope → list of TaskProject ids upstream, then defer all
    additive filter / pagination logic here. The caller is responsible for
    permission checks; this function does NOT re-validate access.
    """
    if not project_ids:
        return [], 0
    return await _filter_tasks_in_projects(db, project_ids, filters)


async def _filter_tasks_in_projects(
    db: AsyncSession,
    project_ids: list[uuid.UUID],
    filters: TaskFilters,
) -> tuple[list[Task], int]:
    stmt = _base_task_select(project_ids, filters.include_deleted)
    count_stmt = _base_count_select(project_ids, filters.include_deleted)

    stmt, count_stmt = _apply_filters(stmt, count_stmt, filters)

    total = await db.scalar(count_stmt) or 0
    result = await db.execute(
        stmt.order_by(*_sort_columns(filters.sort_by, filters.sort_dir))
        .limit(filters.page_size)
        .offset((filters.page - 1) * filters.page_size)
    )
    return list(result.scalars().unique().all()), total


def _base_task_select(
    project_ids: list[uuid.UUID], include_deleted: bool
) -> Select[tuple[Task]]:
    stmt = (
        select(Task)
        .options(
            selectinload(Task.assignees),
            selectinload(Task.label_links),
            selectinload(Task.subtasks),
        )
        .where(Task.task_project_id.in_(project_ids))
    )
    if not include_deleted:
        stmt = stmt.where(Task.deleted_at.is_(None))
    return stmt


def _base_count_select(
    project_ids: list[uuid.UUID], include_deleted: bool
) -> Select[tuple[int]]:
    stmt = select(func.count(Task.id)).where(Task.task_project_id.in_(project_ids))
    if not include_deleted:
        stmt = stmt.where(Task.deleted_at.is_(None))
    return stmt


def _apply_filters(
    stmt: Select[tuple[Task]],
    count_stmt: Select[tuple[int]],
    filters: TaskFilters,
) -> tuple[Select[tuple[Task]], Select[tuple[int]]]:
    if filters.search:
        pattern = f"%{filters.search}%"
        search_clause = or_(Task.title.ilike(pattern), Task.description.ilike(pattern))
        stmt = stmt.where(search_clause)
        count_stmt = count_stmt.where(search_clause)

    if filters.state_id is not None:
        stmt = stmt.where(Task.state_id == filters.state_id)
        count_stmt = count_stmt.where(Task.state_id == filters.state_id)

    if filters.assignee_id is not None:
        stmt = stmt.join(TaskAssignee, TaskAssignee.task_id == Task.id).where(
            TaskAssignee.employee_id == filters.assignee_id
        )
        count_stmt = count_stmt.join(TaskAssignee, TaskAssignee.task_id == Task.id).where(
            TaskAssignee.employee_id == filters.assignee_id
        )

    if filters.reporter_id is not None:
        stmt = stmt.where(Task.reporter_id == filters.reporter_id)
        count_stmt = count_stmt.where(Task.reporter_id == filters.reporter_id)

    if filters.priority is not None:
        stmt = stmt.where(Task.priority == filters.priority)
        count_stmt = count_stmt.where(Task.priority == filters.priority)

    if filters.label_id is not None:
        stmt = stmt.join(TaskLabelLink, TaskLabelLink.task_id == Task.id).where(
            TaskLabelLink.label_id == filters.label_id
        )
        count_stmt = count_stmt.join(TaskLabelLink, TaskLabelLink.task_id == Task.id).where(
            TaskLabelLink.label_id == filters.label_id
        )

    if filters.due_from is not None:
        stmt = stmt.where(Task.due_date >= filters.due_from)
        count_stmt = count_stmt.where(Task.due_date >= filters.due_from)

    if filters.due_to is not None:
        stmt = stmt.where(Task.due_date <= filters.due_to)
        count_stmt = count_stmt.where(Task.due_date <= filters.due_to)

    if filters.overdue:
        stmt = stmt.join(TaskState, TaskState.id == Task.state_id).where(
            Task.due_date < func.now(),
            TaskState.group.not_in(("done", "cancelled")),
        )
        count_stmt = count_stmt.join(TaskState, TaskState.id == Task.state_id).where(
            Task.due_date < func.now(),
            TaskState.group.not_in(("done", "cancelled")),
        )

    return stmt, count_stmt


def _sort_columns(sort_by: TaskSortField, sort_dir: TaskSortDirection):
    sort_column = {
        "created_at": Task.created_at,
        "updated_at": Task.updated_at,
        "due_date": Task.due_date,
        "priority": Task.priority,
        "title": Task.title,
        "position": Task.position,
    }[sort_by]

    primary = sort_column.asc() if sort_dir == "asc" else sort_column.desc()
    return primary, Task.id.asc()
