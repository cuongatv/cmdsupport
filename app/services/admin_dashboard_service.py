"""RBAC-scoped aggregation for the Agile admin dashboard."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.database.models import (
    Employee,
    ProjectMember,
    Role,
    Task,
    TaskActivity,
    TaskProject,
    TaskState,
)
from app.schemas.tasks import AdminDashboardFlowSummaryResponse
from app.services.permission_engine import get_user_department_ids
from app.services.permissions import EMPLOYEE_DEFAULT_PERMISSIONS

_TERMINAL_GROUPS: tuple[str, ...] = ("done", "cancelled")


async def compute_admin_dashboard_summary(
    db: AsyncSession,
    current_user: Employee,
    start_date: date,
    end_date: date,
    *,
    department_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    sprint_id: uuid.UUID | None = None,
) -> AdminDashboardFlowSummaryResponse:
    """Return dashboard flow metrics scoped to projects readable by ``current_user``.

    Access mirrors ``task_access_service.can_access_task_project`` but is expressed
    as SQL predicates so the dashboard can aggregate across all visible projects
    without N+1 project loops.
    """
    start = _normalise_date(start_date)
    end = _normalise_date(end_date)
    if start > end:
        start, end = end, start

    start_dt = _start_of_day(start)
    end_dt = _end_of_day(end)
    now = datetime.now(timezone.utc)

    project_filter = await _build_accessible_project_filter(
        db,
        current_user,
        department_id=department_id,
        workspace_id=workspace_id,
        project_id=project_id,
    )
    if project_filter is None:
        return _summary_response(
            as_of=now,
            scoped_project_count=0,
            wip_count=0,
            blocked_count=0,
            aging_count=0,
            throughput_count=0,
            cycle_time_p50=0.0,
            lead_time_p50=0.0,
            approximation_used=False,
        )

    scoped_project_count = await _count_scoped_projects(db, project_filter)
    if scoped_project_count == 0:
        return _summary_response(
            as_of=now,
            scoped_project_count=0,
            wip_count=0,
            blocked_count=0,
            aging_count=0,
            throughput_count=0,
            cycle_time_p50=0.0,
            lead_time_p50=0.0,
            approximation_used=False,
        )

    active_row = await _aggregate_active_tasks(
        db,
        project_filter,
        now=now,
        sprint_id=sprint_id,
    )
    durations = await _list_completed_durations(
        db,
        project_filter,
        start_dt=start_dt,
        end_dt=end_dt,
        sprint_id=sprint_id,
    )

    throughput_count = len(durations)
    approximation_used = any(item.approximation_used for item in durations)

    return _summary_response(
        as_of=now,
        scoped_project_count=scoped_project_count,
        wip_count=active_row.wip_count,
        blocked_count=active_row.blocked_count,
        aging_count=active_row.aging_count,
        throughput_count=throughput_count,
        cycle_time_p50=_median([item.cycle_time_days for item in durations]),
        lead_time_p50=_median([item.lead_time_days for item in durations]),
        approximation_used=approximation_used,
    )


@dataclass(frozen=True)
class _ActiveAggregate:
    wip_count: int
    blocked_count: int
    aging_count: int


@dataclass(frozen=True)
class _DurationAggregate:
    cycle_time_days: float
    lead_time_days: float
    approximation_used: bool


async def _aggregate_active_tasks(
    db: AsyncSession,
    project_filter: ColumnElement[bool],
    *,
    now: datetime,
    sprint_id: uuid.UUID | None,
) -> _ActiveAggregate:
    filters = [
        project_filter,
        Task.deleted_at.is_(None),
        TaskState.group.not_in(_TERMINAL_GROUPS),
    ]
    if sprint_id is not None:
        filters.append(Task.sprint_id == sprint_id)

    age_days = _age_days_expr(now, Task.updated_at)
    blocked_expr = case((Task.blocked_reason.is_not(None), 1), else_=0)
    aging_expr = case(
        (
            TaskState.aging_warn_days.is_not(None)
            & (TaskState.aging_warn_days > 0)
            & (age_days >= TaskState.aging_warn_days),
            1,
        ),
        else_=0,
    )

    stmt = (
        select(
            func.count(Task.id).label("wip_count"),
            func.coalesce(func.sum(blocked_expr), 0).label("blocked_count"),
            func.coalesce(func.sum(aging_expr), 0).label("aging_count"),
        )
        .select_from(Task)
        .join(TaskState, TaskState.id == Task.state_id)
        .join(TaskProject, TaskProject.id == Task.task_project_id)
        .where(*filters)
    )
    row = (await db.execute(stmt)).one()
    return _ActiveAggregate(
        wip_count=int(row.wip_count or 0),
        blocked_count=int(row.blocked_count or 0),
        aging_count=int(row.aging_count or 0),
    )


async def _list_completed_durations(
    db: AsyncSession,
    project_filter: ColumnElement[bool],
    *,
    start_dt: datetime,
    end_dt: datetime,
    sprint_id: uuid.UUID | None,
) -> list[_DurationAggregate]:
    filters = [
        project_filter,
        Task.deleted_at.is_(None),
        TaskState.group.in_(_TERMINAL_GROUPS),
        Task.updated_at >= start_dt,
        Task.updated_at <= end_dt,
    ]
    if sprint_id is not None:
        filters.append(Task.sprint_id == sprint_id)

    has_activity = (
        select(TaskActivity.id)
        .where(TaskActivity.task_id == Task.id)
        .limit(1)
        .exists()
    )

    stmt = (
        select(
            Task.created_at,
            Task.updated_at,
            has_activity.label("has_activity"),
        )
        .select_from(Task)
        .join(TaskState, TaskState.id == Task.state_id)
        .join(TaskProject, TaskProject.id == Task.task_project_id)
        .where(*filters)
    )
    rows = (await db.execute(stmt)).all()

    durations: list[_DurationAggregate] = []
    for row in rows:
        lead_start = row.created_at
        cycle_start = row.created_at
        completed_at = row.updated_at
        if lead_start is None or cycle_start is None or completed_at is None:
            continue
        durations.append(
            _DurationAggregate(
                cycle_time_days=_days_between(cycle_start, completed_at),
                lead_time_days=_days_between(lead_start, completed_at),
                approximation_used=not bool(row.has_activity),
            )
        )
    return durations


async def _count_scoped_projects(
    db: AsyncSession, project_filter: ColumnElement[bool]
) -> int:
    stmt = select(func.count(TaskProject.id)).where(project_filter)
    return int(await db.scalar(stmt) or 0)


async def _build_accessible_project_filter(
    db: AsyncSession,
    current_user: Employee,
    *,
    department_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
) -> ColumnElement[bool] | None:
    filters: list[ColumnElement[bool]] = [TaskProject.is_archived.is_(False)]
    if department_id is not None:
        filters.append(TaskProject.department_id == department_id)
    if workspace_id is not None:
        filters.append(TaskProject.workspace_id == workspace_id)
    if project_id is not None:
        filters.append(TaskProject.id == project_id)

    access_filter = await _build_task_access_filter(db, current_user)
    if access_filter is None:
        return None
    filters.append(access_filter)
    return _and_all(filters)


async def _build_task_access_filter(
    db: AsyncSession, current_user: Employee
) -> ColumnElement[bool] | None:
    if current_user.role == "admin":
        return literal(True)

    permissions = await _resolve_user_permissions(db, current_user)
    dept_ids = await get_user_department_ids(db, current_user)

    clauses: list[ColumnElement[bool]] = [
        TaskProject.owner_employee_id == current_user.id
    ]
    if "task:read:all" in permissions or "task_project:manage:all" in permissions:
        clauses.extend(
            [
                TaskProject.owner_employee_id.is_(None),
                TaskProject.workspace_id.in_(
                    _workspace_membership_subquery(current_user.id)
                ),
            ]
        )
    else:
        if (
            "task:read:own_dept" in permissions
            or "task_project:manage:own_dept" in permissions
        ):
            if dept_ids:
                clauses.append(TaskProject.department_id.in_(dept_ids))
        clauses.append(
            TaskProject.workspace_id.in_(_workspace_membership_subquery(current_user.id))
        )

    if not clauses:
        return None
    return or_(*clauses)


async def _resolve_user_permissions(
    db: AsyncSession,
    current_user: Employee,
) -> set[str]:
    if current_user.custom_role_id is None:
        return set(EMPLOYEE_DEFAULT_PERMISSIONS)
    role = await db.get(Role, current_user.custom_role_id)
    if role is None:
        return set(EMPLOYEE_DEFAULT_PERMISSIONS)
    return set(role.permissions or [])


def _workspace_membership_subquery(employee_id: uuid.UUID):
    return select(ProjectMember.project_id).where(ProjectMember.employee_id == employee_id)


def _summary_response(
    *,
    as_of: datetime,
    scoped_project_count: int,
    wip_count: int,
    blocked_count: int,
    aging_count: int,
    throughput_count: int,
    cycle_time_p50: float,
    lead_time_p50: float,
    approximation_used: bool,
) -> AdminDashboardFlowSummaryResponse:
    return AdminDashboardFlowSummaryResponse(
        feature_enabled=True,
        as_of=as_of,
        approximation_used=approximation_used,
        scoped_project_count=scoped_project_count,
        wip_count=wip_count,
        blocked_count=blocked_count,
        aging_count=aging_count,
        throughput_count=throughput_count,
        cycle_time_p50=cycle_time_p50,
        lead_time_p50=lead_time_p50,
    )


def _normalise_date(value: date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min)


def _end_of_day(value: date) -> datetime:
    return datetime.combine(value, time.max)


def _age_days_expr(now: datetime, since_column) -> ColumnElement[float]:
    seconds = func.extract("epoch", literal(now) - since_column)
    return seconds / 86400.0


def _days_between(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds()) / 86400.0


def _median(values: Iterable[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return round(ordered[midpoint], 2)
    return round((ordered[midpoint - 1] + ordered[midpoint]) / 2, 2)


def _and_all(filters: list[ColumnElement[bool]]) -> ColumnElement[bool]:
    if len(filters) == 1:
        return filters[0]
    return and_(*filters)
