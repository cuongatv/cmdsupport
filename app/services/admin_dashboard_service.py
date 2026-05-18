"""RBAC-scoped aggregation for the Agile admin dashboard."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Date, Integer, and_, case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    ProjectMember,
    Role,
    Task,
    TaskActivity,
    TaskAssignee,
    TaskFlowSnapshot,
    TaskProject,
    TaskState,
)
from app.schemas.tasks import (
    AdminDashboardAgingTaskItem,
    AdminDashboardCapacityItem,
    AdminDashboardCfdPoint,
    AdminDashboardChartSeries,
    AdminDashboardFlowSummaryResponse,
    AdminDashboardRiskItem,
    AdminDashboardThroughputPoint,
)
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
    cfd_series = await _list_cfd_series(
        db,
        project_filter,
        start_date=start,
        end_date=end,
    )
    aging_risk_rows = await _list_aging_risk_rows(
        db,
        project_filter,
        now=now,
        sprint_id=sprint_id,
        limit=25,
    )
    aging_tasks = _aging_tasks_from_rows(aging_risk_rows)
    throughput_series = await _list_throughput_series(
        db,
        project_filter,
        start_dt=start_dt,
        end_dt=end_dt,
        sprint_id=sprint_id,
    )
    capacity_items = await _list_capacity_items(db, project_filter)
    risk_items = _risk_items_from_rows(aging_risk_rows)

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
        chart_series=AdminDashboardChartSeries(
            cfd_series=cfd_series,
            aging_tasks=aging_tasks,
            throughput_series=throughput_series,
        ),
        risk_items=risk_items,
        capacity_items=capacity_items,
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


@dataclass(frozen=True)
class _AgingRiskRow:
    task_id: uuid.UUID
    title: str
    state_name: str
    aging_days: int
    priority: str | None
    assignee_names: list[str]
    is_blocked: bool
    blocked_days: int


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
        TaskState.group == "done",
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


async def _list_cfd_series(
    db: AsyncSession,
    project_filter: ColumnElement[bool],
    *,
    start_date: date,
    end_date: date,
) -> list[AdminDashboardCfdPoint]:
    stmt = (
        select(
            TaskFlowSnapshot.snapshot_date,
            TaskState.group,
            func.coalesce(func.sum(TaskFlowSnapshot.task_count), 0).label(
                "task_count"
            ),
            func.coalesce(func.sum(TaskFlowSnapshot.blocked_count), 0).label(
                "blocked_count"
            ),
        )
        .select_from(TaskFlowSnapshot)
        .join(TaskProject, TaskProject.id == TaskFlowSnapshot.task_project_id)
        .outerjoin(TaskState, TaskState.id == TaskFlowSnapshot.state_id)
        .where(
            TaskFlowSnapshot.task_project_id == TaskProject.id,
            project_filter,
            TaskFlowSnapshot.snapshot_date >= start_date,
            TaskFlowSnapshot.snapshot_date <= end_date,
        )
        .group_by(TaskFlowSnapshot.snapshot_date, TaskState.group)
        .order_by(TaskFlowSnapshot.snapshot_date.asc(), TaskState.group.asc())
    )
    rows = (await db.execute(stmt)).all()

    points: dict[date, AdminDashboardCfdPoint] = {}
    for row in rows:
        snapshot_date = row.snapshot_date
        point = points.setdefault(
            snapshot_date,
            AdminDashboardCfdPoint(snapshot_date=snapshot_date),
        )
        state_group = row.group or "unknown"
        task_count = int(row.task_count or 0)
        point.state_counts[state_group] = point.state_counts.get(state_group, 0) + task_count
        point.blocked_count += int(row.blocked_count or 0)
    return list(points.values())


def _aging_tasks_from_rows(
    rows: list[_AgingRiskRow],
) -> list[AdminDashboardAgingTaskItem]:
    return [
        AdminDashboardAgingTaskItem(
            task_id=row.task_id,
            title=row.title,
            state_name=row.state_name,
            aging_days=row.aging_days,
            priority=row.priority,
            assignee_names=row.assignee_names,
        )
        for row in rows[:25]
    ]


async def _list_throughput_series(
    db: AsyncSession,
    project_filter: ColumnElement[bool],
    *,
    start_dt: datetime,
    end_dt: datetime,
    sprint_id: uuid.UUID | None,
) -> list[AdminDashboardThroughputPoint]:
    week_start = func.date_trunc("week", Task.updated_at).cast(Date)
    filters = [
        project_filter,
        Task.deleted_at.is_(None),
        TaskState.group == "done",
        Task.updated_at >= start_dt,
        Task.updated_at <= end_dt,
    ]
    if sprint_id is not None:
        filters.append(Task.sprint_id == sprint_id)

    stmt = (
        select(
            week_start.label("period_start"),
            func.count(Task.id).label("tasks_completed"),
            func.coalesce(func.sum(Task.story_points), 0).label(
                "story_points_completed"
            ),
        )
        .select_from(Task)
        .join(TaskState, TaskState.id == Task.state_id)
        .join(TaskProject, TaskProject.id == Task.task_project_id)
        .where(*filters)
        .group_by(week_start)
        .order_by(week_start.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        AdminDashboardThroughputPoint(
            period_start=row.period_start,
            period_end=row.period_start + timedelta(days=6),
            tasks_completed=int(row.tasks_completed or 0),
            story_points_completed=int(row.story_points_completed or 0),
        )
        for row in rows
    ]


def _risk_items_from_rows(rows: list[_AgingRiskRow]) -> list[AdminDashboardRiskItem]:
    risk_rows = [row for row in rows if row.is_blocked or row.aging_days >= 14]
    risk_rows.sort(key=lambda row: (_risk_rank(row), row.aging_days), reverse=True)
    return [
        AdminDashboardRiskItem(
            id=str(row.task_id),
            title=row.title,
            severity=_risk_severity(row),
            count=row.aging_days,
            description=_risk_description(row),
        )
        for row in risk_rows[:10]
    ]


async def _list_aging_risk_rows(
    db: AsyncSession,
    project_filter: ColumnElement[bool],
    *,
    now: datetime,
    sprint_id: uuid.UUID | None,
    limit: int,
) -> list[_AgingRiskRow]:
    age_days = func.floor(_age_days_expr(now, Task.updated_at)).cast(Integer)
    blocked_age_days = func.floor(
        _age_days_expr(now, func.coalesce(Task.blocked_at, Task.updated_at))
    ).cast(Integer)
    assignee_names = func.array_remove(func.array_agg(func.distinct(Employee.name)), None)
    blocked_filter = or_(Task.blocked_reason.is_not(None), Task.blocked_at.is_not(None))
    filters = [
        project_filter,
        Task.deleted_at.is_(None),
        TaskState.group.not_in(_TERMINAL_GROUPS),
    ]
    if sprint_id is not None:
        filters.append(Task.sprint_id == sprint_id)

    stmt = (
        select(
            Task.id,
            Task.title,
            TaskState.name,
            age_days.label("aging_days"),
            Task.priority,
            assignee_names.label("assignee_names"),
            blocked_filter.label("is_blocked"),
            blocked_age_days.label("blocked_days"),
        )
        .select_from(Task)
        .join(TaskState, TaskState.id == Task.state_id)
        .join(TaskProject, TaskProject.id == Task.task_project_id)
        .outerjoin(TaskAssignee, TaskAssignee.task_id == Task.id)
        .outerjoin(Employee, Employee.id == TaskAssignee.employee_id)
        .where(*filters)
        .group_by(
            Task.id,
            Task.title,
            TaskState.name,
            Task.updated_at,
            Task.priority,
            Task.blocked_reason,
            Task.blocked_at,
        )
        .order_by(age_days.desc(), Task.id.asc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        _AgingRiskRow(
            task_id=row.id,
            title=row.title,
            state_name=row.name,
            aging_days=int(row.aging_days or 0),
            priority=row.priority,
            assignee_names=list(row.assignee_names or []),
            is_blocked=bool(row.is_blocked),
            blocked_days=int(row.blocked_days or 0),
        )
        for row in rows
    ]


async def _list_capacity_items(
    db: AsyncSession,
    project_filter: ColumnElement[bool],
) -> list[AdminDashboardCapacityItem]:
    task_agg = (
        select(
            TaskAssignee.employee_id.label("employee_id"),
            TaskProject.department_id.label("department_id"),
            func.count(Task.id).label("task_count"),
            func.sum(Task.story_points).label("sp_sum"),
        )
        .select_from(TaskAssignee)
        .join(Task, Task.id == TaskAssignee.task_id)
        .join(TaskState, TaskState.id == Task.state_id)
        .join(TaskProject, TaskProject.id == Task.task_project_id)
        .where(
            project_filter,
            Task.deleted_at.is_(None),
            TaskState.group.not_in(_TERMINAL_GROUPS),
            TaskProject.department_id.is_not(None),
        )
        .group_by(TaskAssignee.employee_id, TaskProject.department_id)
        .subquery("admin_capacity_task_agg")
    )

    stmt = (
        select(
            EmployeeDepartmentMembership.employee_id,
            Employee.name.label("employee_name"),
            EmployeeDepartmentMembership.department_id,
            Department.name.label("department_name"),
            EmployeeDepartmentMembership.capacity_percent,
            func.coalesce(task_agg.c.task_count, 0).label("open_task_count"),
            task_agg.c.sp_sum,
        )
        .select_from(EmployeeDepartmentMembership)
        .join(Employee, Employee.id == EmployeeDepartmentMembership.employee_id)
        .join(Department, Department.id == EmployeeDepartmentMembership.department_id)
        .join(
            TaskProject,
            TaskProject.department_id == EmployeeDepartmentMembership.department_id,
        )
        .outerjoin(
            task_agg,
            (task_agg.c.employee_id == EmployeeDepartmentMembership.employee_id)
            & (task_agg.c.department_id == EmployeeDepartmentMembership.department_id),
        )
        .where(
            project_filter,
            EmployeeDepartmentMembership.is_active.is_(True),
            Department.is_archived.is_(False),
        )
        .group_by(
            EmployeeDepartmentMembership.employee_id,
            Employee.name,
            EmployeeDepartmentMembership.department_id,
            Department.name,
            EmployeeDepartmentMembership.capacity_percent,
            task_agg.c.task_count,
            task_agg.c.sp_sum,
        )
        .order_by(Department.name.asc(), Employee.name.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        AdminDashboardCapacityItem(
            id=f"{row.department_id}:{row.employee_id}",
            label=f"{row.department_name} - {row.employee_name}",
            capacity_percent=(
                int(row.capacity_percent) if row.capacity_percent is not None else None
            ),
            open_task_count=int(row.open_task_count or 0),
            story_points_sum=(int(row.sp_sum) if row.sp_sum is not None else None),
            is_overloaded=(
                row.capacity_percent is not None and int(row.capacity_percent) > 100
            ),
        )
        for row in rows
    ]


def _risk_severity(row: _AgingRiskRow) -> str:
    priority = row.priority or "none"
    if row.aging_days > 30 or priority in {"critical", "urgent"}:
        return "critical"
    if row.aging_days > 14 or priority == "high" or (row.is_blocked and row.blocked_days > 7):
        return "high"
    return "medium"


def _risk_rank(row: _AgingRiskRow) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(
        _risk_severity(row), 0
    )


def _risk_description(row: _AgingRiskRow) -> str:
    parts: list[str] = [f"{row.aging_days} days since last update"]
    if row.is_blocked:
        parts.append(f"blocked for {row.blocked_days} days")
    if row.priority:
        parts.append(f"priority: {row.priority}")
    return "; ".join(parts)


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
    chart_series: AdminDashboardChartSeries | None = None,
    risk_items: list[AdminDashboardRiskItem] | None = None,
    capacity_items: list[AdminDashboardCapacityItem] | None = None,
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
        chart_series=chart_series or AdminDashboardChartSeries(),
        risk_items=risk_items or [],
        capacity_items=capacity_items or [],
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
