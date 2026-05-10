"""Task project dashboard aggregation service.

Computes per-project dashboard summaries using SQL aggregations (no in-memory
counting). All queries respect soft-delete (`Task.deleted_at IS NULL`) and only
operate on the supplied task project, which the caller must have already
authorized for the employee.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Employee, Task, TaskAssignee, TaskProject, TaskState
from app.schemas.tasks import (
    DashboardAssigneeItem,
    DashboardOut,
    DashboardStateItem,
    DueSoonItem,
)

_DUE_SOON_LIMIT: int = 20
_TERMINAL_GROUPS: tuple[str, ...] = ("done", "cancelled")


async def get_dashboard(
    db: AsyncSession,
    employee: Employee,  # accepted for parity / future scope-narrowing; access is enforced upstream
    task_project: TaskProject,
) -> DashboardOut:
    """Aggregate dashboard metrics for a single task project."""
    now = datetime.now(timezone.utc)
    week_end = now + timedelta(days=7)
    project_id = task_project.id

    by_state = await _aggregate_by_state(db, project_id)
    by_assignee = await _aggregate_by_assignee(db, project_id)
    overdue_count = await _count_overdue(db, project_id, now)
    due_this_week = await _list_due_this_week(db, project_id, now, week_end)
    total_tasks = await _count_total(db, project_id)

    return DashboardOut(
        by_state=by_state,
        by_assignee=by_assignee,
        overdue_count=overdue_count,
        due_this_week=due_this_week,
        total_tasks=total_tasks,
    )


async def _aggregate_by_state(
    db: AsyncSession, project_id
) -> list[DashboardStateItem]:
    """Count non-deleted tasks per state, including states with zero tasks."""
    stmt = (
        select(
            TaskState.id,
            TaskState.name,
            TaskState.group,
            func.count(Task.id),
        )
        .select_from(TaskState)
        .outerjoin(
            Task,
            (Task.state_id == TaskState.id) & (Task.deleted_at.is_(None)),
        )
        .where(TaskState.task_project_id == project_id)
        .group_by(TaskState.id, TaskState.name, TaskState.group, TaskState.position)
        .order_by(TaskState.position, TaskState.created_at)
    )
    result = await db.execute(stmt)
    return [
        DashboardStateItem(
            state_id=row[0],
            state_name=row[1],
            group=row[2],
            count=int(row[3] or 0),
        )
        for row in result.all()
    ]


async def _aggregate_by_assignee(
    db: AsyncSession, project_id
) -> list[DashboardAssigneeItem]:
    """Count non-deleted tasks per assignee within the project."""
    stmt = (
        select(
            Employee.id,
            Employee.name,
            func.count(Task.id),
        )
        .select_from(TaskAssignee)
        .join(Task, Task.id == TaskAssignee.task_id)
        .join(Employee, Employee.id == TaskAssignee.employee_id)
        .where(
            Task.task_project_id == project_id,
            Task.deleted_at.is_(None),
        )
        .group_by(Employee.id, Employee.name)
        .order_by(func.count(Task.id).desc(), Employee.name)
    )
    result = await db.execute(stmt)
    return [
        DashboardAssigneeItem(
            employee_id=row[0],
            employee_name=row[1],
            count=int(row[2] or 0),
        )
        for row in result.all()
    ]


async def _count_overdue(db: AsyncSession, project_id, now: datetime) -> int:
    stmt = (
        select(func.count(Task.id))
        .select_from(Task)
        .join(TaskState, TaskState.id == Task.state_id)
        .where(
            Task.task_project_id == project_id,
            Task.deleted_at.is_(None),
            Task.due_date.is_not(None),
            Task.due_date < now,
            TaskState.group.not_in(_TERMINAL_GROUPS),
        )
    )
    return int(await db.scalar(stmt) or 0)


async def _list_due_this_week(
    db: AsyncSession,
    project_id,
    now: datetime,
    week_end: datetime,
) -> list[DueSoonItem]:
    stmt = (
        select(
            Task.id,
            Task.title,
            Task.priority,
            Task.due_date,
            TaskState.name,
        )
        .select_from(Task)
        .join(TaskState, TaskState.id == Task.state_id)
        .where(
            Task.task_project_id == project_id,
            Task.deleted_at.is_(None),
            Task.due_date.is_not(None),
            Task.due_date >= now,
            Task.due_date <= week_end,
            TaskState.group.not_in(_TERMINAL_GROUPS),
        )
        .order_by(Task.due_date.asc(), Task.id.asc())
        .limit(_DUE_SOON_LIMIT)
    )
    result = await db.execute(stmt)
    return [
        DueSoonItem(
            id=row[0],
            title=row[1],
            priority=row[2],
            due_date=row[3],
            state_name=row[4],
        )
        for row in result.all()
    ]


async def _count_total(db: AsyncSession, project_id) -> int:
    stmt = select(func.count(Task.id)).where(
        Task.task_project_id == project_id,
        Task.deleted_at.is_(None),
    )
    return int(await db.scalar(stmt) or 0)
