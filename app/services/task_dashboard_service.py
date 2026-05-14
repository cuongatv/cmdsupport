"""Task project dashboard aggregation service.

Computes per-project dashboard summaries using SQL aggregations (no in-memory
counting). All queries respect soft-delete (`Task.deleted_at IS NULL`) and only
operate on the supplied task project, which the caller must have already
authorized for the employee.

Also exposes ``get_personal_dashboard_overview`` — the per-employee aggregate
view used by ``GET /api/me/dashboard``. It returns the employee's personal
bucket counts plus one ``UnitDashboardAggregate`` per active department
membership, with all counts produced server-side via ``func.count(...)``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    Task,
    TaskAssignee,
    TaskProject,
    TaskState,
)
from app.schemas.habits import (
    DashboardBuckets,
    DashboardOverviewResponse,
    UnitDashboardAggregate,
)
from app.schemas.tasks import (
    DashboardAssigneeItem,
    DashboardOut,
    DashboardStateItem,
    DueSoonItem,
)
from app.services.task_project_service import get_or_create_personal_project

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


async def _aggregate_by_state(db: AsyncSession, project_id) -> list[DashboardStateItem]:
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


# ---------------------------------------------------------------------------
# Personal dashboard overview — drives GET /api/me/dashboard
# ---------------------------------------------------------------------------


async def get_personal_dashboard_overview(
    db: AsyncSession,
    employee: Employee,
    due_soon_days: int = 7,
) -> DashboardOverviewResponse:
    """Return per-bucket task counts for ``employee`` and each unit they belong to.

    The ``personal`` bucket is scoped to the employee's canonical personal
    ``TaskProject`` (lazy-created on first call via
    :func:`get_or_create_personal_project`). One ``UnitDashboardAggregate`` is
    appended per active department membership. ``due_soon_days`` controls the
    look-ahead window for the ``due_soon`` bucket (default 7).
    """
    now = datetime.now(timezone.utc)
    soon_threshold = now + timedelta(days=due_soon_days)

    # Lazy-create the canonical personal project so first-time users see a
    # zero-state dashboard backed by a real container instead of an empty IN.
    personal_project = await get_or_create_personal_project(db, employee)
    personal_filter = Task.task_project_id == personal_project.id
    personal_buckets = await _compute_buckets_for_filter(
        db, personal_filter, now, soon_threshold
    )

    units = await list_user_units(db, employee, due_soon_days=due_soon_days)

    return DashboardOverviewResponse(
        personal=personal_buckets,
        units=units,
        due_soon_days=due_soon_days,
    )


async def list_user_units(
    db: AsyncSession,
    employee: Employee,
    due_soon_days: int = 7,
) -> list[UnitDashboardAggregate]:
    """Return one ``UnitDashboardAggregate`` per active department membership.

    Mirrors the unit-aggregation half of
    :func:`get_personal_dashboard_overview` so the standalone ``/api/me/units``
    endpoint can reuse the same bucketing logic without computing the personal
    bucket. ``due_soon_days`` controls the look-ahead window for the
    ``due_soon`` bucket (default 7), matching the dashboard endpoint default.
    """
    now = datetime.now(timezone.utc)
    soon_threshold = now + timedelta(days=due_soon_days)

    departments_stmt = select(Department).where(
        or_(
            Department.id == employee.department_id,
            Department.id.in_(
                select(EmployeeDepartmentMembership.department_id).where(
                    EmployeeDepartmentMembership.employee_id == employee.id,
                    EmployeeDepartmentMembership.is_active.is_(True),
                )
            ),
        ),
        Department.is_archived.is_(False),
    )
    departments_stmt = departments_stmt.order_by(Department.name)
    departments = (await db.execute(departments_stmt)).scalars().all()

    units: list[UnitDashboardAggregate] = []
    for dept in departments:
        unit_filter = Task.task_project_id.in_(
            select(TaskProject.id).where(TaskProject.department_id == dept.id)
        )
        buckets = await _compute_buckets_for_filter(
            db, unit_filter, now, soon_threshold
        )
        units.append(
            UnitDashboardAggregate(
                unit_id=dept.id,
                unit_name=dept.name,
                unit_type=_enum_str(dept.unit_type),
                buckets=buckets,
            )
        )
    return units


async def _compute_buckets_for_filter(
    db: AsyncSession,
    project_filter: ColumnElement[bool],
    now: datetime,
    soon_threshold: datetime,
) -> DashboardBuckets:
    """Count not-done / not-deleted tasks by due-date bucket under ``project_filter``."""
    base_filters = [
        project_filter,
        Task.deleted_at.is_(None),
        Task.completed_at.is_(None),
    ]
    total = (
        await db.execute(select(func.count()).select_from(Task).where(*base_filters))
    ).scalar_one()
    overdue = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .where(*base_filters, Task.due_date.is_not(None), Task.due_date < now)
        )
    ).scalar_one()
    due_soon = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                *base_filters,
                Task.due_date.is_not(None),
                Task.due_date >= now,
                Task.due_date <= soon_threshold,
            )
        )
    ).scalar_one()
    not_due_yet = (
        await db.execute(
            select(func.count())
            .select_from(Task)
            .where(
                *base_filters,
                or_(Task.due_date.is_(None), Task.due_date > soon_threshold),
            )
        )
    ).scalar_one()
    return DashboardBuckets(
        total=int(total or 0),
        not_due_yet=int(not_due_yet or 0),
        due_soon=int(due_soon or 0),
        overdue=int(overdue or 0),
    )


def _enum_str(value: object) -> str:
    """Return the ``.value`` of an Enum, or ``str(value)`` for plain strings."""
    raw = getattr(value, "value", value)
    return str(raw)
