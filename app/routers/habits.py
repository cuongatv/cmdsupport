"""Personal habit planning, weekly calendar, and dashboard router.

All endpoints live under ``/api/me/*`` and require an authenticated employee.
Habit CRUD and per-date occurrence-state upserts are thin pass-throughs over
``app.services.habit_service``; the calendar and dashboard endpoints continue
to compose multiple services (task project, task dashboard, habit) inside the
HTTP boundary.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone
from math import ceil
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import (
    Employee,
    EmployeeDepartmentMembership,
    HabitOccurrenceState,
    HabitOccurrenceStatus,
    PersonalHabit,
    Task,
    TaskAssignee,
    TaskPriority,
    TaskProject,
    TaskState,
)
from app.schemas.habits import (
    CalendarEventType,
    CalendarHabitEvent,
    CalendarTaskEvent,
    CalendarWeekResponse,
    DashboardOverviewResponse,
    HabitCreate,
    HabitOccurrenceStateRead,
    HabitRead,
    HabitUpdate,
    UnitDashboardAggregate,
)
from app.schemas.tasks import PaginatedResponse, TaskOut
from app.services import habit_service
from app.services.auth_service import get_current_user
from app.services.task_constants import PRIORITY_LEVELS
from app.services.task_dashboard_service import (
    get_personal_dashboard_overview,
    list_user_units,
)
from app.services.task_project_service import get_or_create_personal_project

router = APIRouter(prefix="/me")

# Tasks at or above this priority displace habit blocks in the calendar view.
_HIGH_PRIORITY_VALUES: frozenset[str] = frozenset(
    {TaskPriority.HIGH.value, TaskPriority.URGENT.value}
)


# ---------------------------------------------------------------------------
# Habit CRUD — owner-scoped (delegates to app.services.habit_service)
# ---------------------------------------------------------------------------


@router.get("/habits", response_model=list[HabitRead])
async def list_my_habits(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> list[PersonalHabit]:
    """List habits owned by the current user, ordered by preferred time."""
    return await habit_service.list_habits(
        db, current_user.id, include_inactive=include_inactive
    )


@router.post(
    "/habits",
    response_model=HabitRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_habit(
    body: HabitCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> PersonalHabit:
    """Create a new personal habit owned by the current user."""
    return await habit_service.create_habit(db, current_user.id, body)


@router.get("/habits/{habit_id}", response_model=HabitRead)
async def get_my_habit(
    habit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> PersonalHabit:
    """Fetch a single habit owned by the current user."""
    return await _call_owner_scoped(
        habit_service.get_habit, db, habit_id, current_user.id
    )


@router.patch("/habits/{habit_id}", response_model=HabitRead)
async def update_my_habit(
    habit_id: uuid.UUID,
    body: HabitUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> PersonalHabit:
    """Patch fields on an existing habit owned by the current user."""
    return await _call_owner_scoped(
        habit_service.update_habit, db, habit_id, current_user.id, body
    )


@router.delete("/habits/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_habit(
    habit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> None:
    """Soft-delete a habit by flipping ``is_active`` off."""
    await _call_owner_scoped(habit_service.delete_habit, db, habit_id, current_user.id)


# ---------------------------------------------------------------------------
# Habit occurrence state — upsert per (habit, date)
# ---------------------------------------------------------------------------


class HabitOccurrenceUpsert(BaseModel):
    """Inline body for the per-date occurrence upsert endpoint."""

    state: HabitOccurrenceStatus
    actual_start: Optional[time] = None
    shift_reason: Optional[str] = None


@router.post(
    "/habits/{habit_id}/occurrences/{occurrence_date}",
    response_model=HabitOccurrenceStateRead,
    status_code=status.HTTP_200_OK,
)
async def upsert_habit_occurrence(
    habit_id: uuid.UUID,
    occurrence_date: date,
    body: HabitOccurrenceUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> HabitOccurrenceState:
    """Upsert the per-date state (completed / skipped / shifted) for a habit."""
    return await _call_owner_scoped(
        habit_service.upsert_occurrence,
        db,
        habit_id,
        current_user.id,
        occurrence_date,
        body.state,
        body.actual_start,
        body.shift_reason,
    )


# ---------------------------------------------------------------------------
# Calendar — week view (personal merges tasks + habits, department is tasks-only)
# ---------------------------------------------------------------------------


@router.get("/calendar", response_model=CalendarWeekResponse)
async def get_calendar_week(
    week_start: date = Query(...),
    scope: Literal["personal", "department"] = Query("personal"),
    dept_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> CalendarWeekResponse:
    """Return the calendar events for a given week and scope.

    For ``scope=personal`` we merge the user's scheduled tasks with their
    active habits (one event per active weekday in the week). When a
    high/urgent task overlaps a habit slot, the habit event is shifted to
    just after the task and ``shift_reason`` is populated.
    """
    if scope == "department":
        if dept_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="dept_id is required when scope=department",
            )
        await _ensure_user_in_department(db, current_user, dept_id)
    elif dept_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="dept_id is only allowed when scope=department",
        )

    week_end = week_start + timedelta(days=6)
    window_start = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    window_end = datetime.combine(
        week_end + timedelta(days=1), time.min, tzinfo=timezone.utc
    )

    # Personal scope lazily materialises the user's canonical TaskProject so
    # the calendar always has a container to point at on first visit.
    personal_project_id: Optional[uuid.UUID] = None
    if scope == "personal":
        personal_project = await get_or_create_personal_project(db, current_user)
        personal_project_id = personal_project.id

    tasks = await _list_scope_tasks(
        db,
        scope,
        dept_id,
        personal_project_id,
        window_start,
        window_end,
    )
    task_events: list[CalendarTaskEvent] = [
        CalendarTaskEvent(
            event_type=CalendarEventType.TASK,
            task_id=t.id,
            title=t.title,
            priority=_coerce_priority(t.priority),
            scheduled_start_at=t.scheduled_start_at,
            scheduled_end_at=t.scheduled_end_at,
            schedule_locked=t.schedule_locked,
        )
        for t in tasks
        if t.scheduled_start_at is not None and t.scheduled_end_at is not None
    ]

    habit_events: list[CalendarHabitEvent] = []
    if scope == "personal":
        habits = await _list_active_habits(db, current_user.id)
        states_by_key = await _occurrence_states_for_range(
            db, [h.id for h in habits], week_start, week_end
        )
        habit_events = _build_habit_events(
            habits, task_events, week_start, states_by_key
        )

    events: list[CalendarTaskEvent | CalendarHabitEvent] = [*task_events, *habit_events]
    events.sort(key=_event_start_key)

    return CalendarWeekResponse(
        scope=scope,
        week_start=week_start,
        week_end=week_end,
        events=events,
    )


# ---------------------------------------------------------------------------
# Dashboard overview — personal + units the user belongs to
# ---------------------------------------------------------------------------


@router.get("/dashboard", response_model=DashboardOverviewResponse)
async def get_dashboard_overview(
    due_soon_days: int = Query(7, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> DashboardOverviewResponse:
    """Return per-bucket task counts for the user and each unit they belong to.

    Pure pass-through to ``task_dashboard_service.get_personal_dashboard_overview``;
    the router stays HTTP-only and the aggregation lives in the service layer.
    """
    return await get_personal_dashboard_overview(
        db, current_user, due_soon_days=due_soon_days
    )


# ---------------------------------------------------------------------------
# Unit switcher — the standalone list of departments the user belongs to
# ---------------------------------------------------------------------------


@router.get("/units", response_model=list[UnitDashboardAggregate])
async def list_my_units(
    due_soon_days: int = Query(7, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> list[UnitDashboardAggregate]:
    """Return one aggregate per active department membership.

    Powers the unit workspace switcher in the frontend portal. Shares the same
    bucketing logic as ``/api/me/dashboard`` — see
    :func:`app.services.task_dashboard_service.list_user_units` for the SQL.
    """
    return await list_user_units(db, current_user, due_soon_days=due_soon_days)


# ---------------------------------------------------------------------------
# My tasks — paginated list of every task assigned to the current user
# ---------------------------------------------------------------------------


_TASKS_TERMINAL_GROUPS: tuple[str, ...] = ("done", "cancelled")


@router.get("/tasks", response_model=PaginatedResponse[TaskOut])
async def list_my_tasks(
    state_id: Optional[uuid.UUID] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    due_from: Optional[datetime] = Query(default=None),
    due_to: Optional[datetime] = Query(default=None),
    overdue: bool = Query(default=False),
    search: Optional[str] = Query(default=None),
    sort_by: Literal["due_date", "priority", "created_at"] = Query(default="due_date"),
    sort_dir: Literal["asc", "desc"] = Query(default="asc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> PaginatedResponse[TaskOut]:
    """List every active (non-deleted) task assigned to the current user.

    Spans every scope — personal, department, and workspace task projects —
    by joining ``Task`` to ``TaskAssignee`` on the caller's employee id. Being
    assigned to a task is implicit access; we do NOT re-run the project-level
    visibility filter here.
    """
    if priority is not None and priority not in PRIORITY_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid priority",
        )

    base_clauses = [
        TaskAssignee.employee_id == current_user.id,
        Task.deleted_at.is_(None),
    ]
    stmt = (
        select(Task)
        .join(TaskAssignee, TaskAssignee.task_id == Task.id)
        .where(*base_clauses)
    )
    # TaskAssignee.(task_id, employee_id) is a composite PK so each task
    # contributes at most one row for the current user — count(Task.id) is
    # safe without a DISTINCT.
    count_stmt = (
        select(func.count(Task.id))
        .select_from(Task)
        .join(TaskAssignee, TaskAssignee.task_id == Task.id)
        .where(*base_clauses)
    )

    if state_id is not None:
        stmt = stmt.where(Task.state_id == state_id)
        count_stmt = count_stmt.where(Task.state_id == state_id)

    if priority is not None:
        stmt = stmt.where(Task.priority == priority)
        count_stmt = count_stmt.where(Task.priority == priority)

    if due_from is not None:
        stmt = stmt.where(Task.due_date >= due_from)
        count_stmt = count_stmt.where(Task.due_date >= due_from)

    if due_to is not None:
        stmt = stmt.where(Task.due_date <= due_to)
        count_stmt = count_stmt.where(Task.due_date <= due_to)

    if overdue:
        stmt = stmt.join(TaskState, TaskState.id == Task.state_id).where(
            Task.due_date.is_not(None),
            Task.due_date < func.now(),
            TaskState.group.not_in(_TASKS_TERMINAL_GROUPS),
        )
        count_stmt = count_stmt.join(TaskState, TaskState.id == Task.state_id).where(
            Task.due_date.is_not(None),
            Task.due_date < func.now(),
            TaskState.group.not_in(_TASKS_TERMINAL_GROUPS),
        )

    if search:
        pattern = f"%{search}%"
        search_clause = or_(Task.title.ilike(pattern), Task.description.ilike(pattern))
        stmt = stmt.where(search_clause)
        count_stmt = count_stmt.where(search_clause)

    sort_column = {
        "due_date": Task.due_date,
        "priority": Task.priority,
        "created_at": Task.created_at,
    }[sort_by]
    primary = sort_column.asc() if sort_dir == "asc" else sort_column.desc()
    stmt = stmt.order_by(primary, Task.id.asc())

    total = int(await db.scalar(count_stmt) or 0)
    result = await db.execute(stmt.limit(page_size).offset((page - 1) * page_size))
    items = list(result.scalars().unique().all())
    return PaginatedResponse[TaskOut](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
    )


# ---------------------------------------------------------------------------
# Helpers (private to this router)
# ---------------------------------------------------------------------------


async def _call_owner_scoped(func, *args, **kwargs):
    """Run a habit_service call and translate owner errors to HTTP responses.

    Missing habit rows and cross-owner access are both reported as ``404`` for
    existing habit resources so callers cannot distinguish "does not exist" from
    "belongs to someone else". Non-ownership is still raised as
    ``PermissionError`` in the service layer for reuse outside HTTP.
    """
    try:
        return await func(*args, **kwargs)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="habit not found",
        ) from exc


async def _ensure_user_in_department(
    db: AsyncSession,
    user: Employee,
    dept_id: uuid.UUID,
) -> None:
    """Verify the caller has any membership in ``dept_id`` (admins bypass)."""
    if user.role == "admin":
        return
    if user.department_id == dept_id:
        return
    membership = (
        await db.execute(
            select(EmployeeDepartmentMembership.id).where(
                EmployeeDepartmentMembership.employee_id == user.id,
                EmployeeDepartmentMembership.department_id == dept_id,
                EmployeeDepartmentMembership.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not a member of this department",
        )


async def _list_scope_tasks(
    db: AsyncSession,
    scope: str,
    dept_id: Optional[uuid.UUID],
    personal_project_id: Optional[uuid.UUID],
    window_start: datetime,
    window_end: datetime,
) -> list[Task]:
    if scope == "personal":
        # personal_project_id is materialised by the caller via
        # get_or_create_personal_project, so this branch always has a target.
        project_filter = Task.task_project_id == personal_project_id
    else:
        project_filter = Task.task_project_id.in_(
            select(TaskProject.id).where(TaskProject.department_id == dept_id)
        )
    stmt = (
        select(Task)
        .where(
            project_filter,
            Task.deleted_at.is_(None),
            Task.scheduled_start_at.is_not(None),
            Task.scheduled_end_at.is_not(None),
            Task.scheduled_start_at < window_end,
            Task.scheduled_end_at > window_start,
        )
        .order_by(Task.scheduled_start_at)
    )
    return list((await db.execute(stmt)).scalars().all())


async def _list_active_habits(
    db: AsyncSession,
    owner_id: uuid.UUID,
) -> list[PersonalHabit]:
    stmt = select(PersonalHabit).where(
        PersonalHabit.owner_employee_id == owner_id,
        PersonalHabit.is_active.is_(True),
    )
    return list((await db.execute(stmt)).scalars().all())


async def _occurrence_states_for_range(
    db: AsyncSession,
    habit_ids: list[uuid.UUID],
    week_start: date,
    week_end: date,
) -> dict[tuple[uuid.UUID, date], HabitOccurrenceState]:
    if not habit_ids:
        return {}
    stmt = select(HabitOccurrenceState).where(
        HabitOccurrenceState.habit_id.in_(habit_ids),
        HabitOccurrenceState.occurrence_date >= week_start,
        HabitOccurrenceState.occurrence_date <= week_end,
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {(row.habit_id, row.occurrence_date): row for row in rows}


def _build_habit_events(
    habits: list[PersonalHabit],
    task_events: list[CalendarTaskEvent],
    week_start: date,
    states_by_key: dict[tuple[uuid.UUID, date], HabitOccurrenceState],
) -> list[CalendarHabitEvent]:
    """Materialise one CalendarHabitEvent per active-day occurrence in the week.

    Conflict policy: if any high/urgent task overlaps the habit slot, the
    habit is shifted to start at the task's scheduled end. ``original_start``
    and ``shift_reason`` are populated so the UI can render both the planned
    and shifted positions.
    """
    events: list[CalendarHabitEvent] = []
    for habit in habits:
        active_set = {int(d) for d in (habit.active_days or [])}
        if not active_set:
            continue
        duration = timedelta(minutes=habit.duration_minutes)
        for offset in range(7):
            occurrence_date = week_start + timedelta(days=offset)
            if occurrence_date.weekday() not in active_set:
                continue
            original_start = datetime.combine(
                occurrence_date, habit.preferred_time, tzinfo=timezone.utc
            )
            original_end = original_start + duration

            shift_reason: Optional[str] = None
            shifted = False
            start = original_start
            end = original_end
            for task in task_events:
                task_pri = _enum_value(task.priority)
                if task_pri not in _HIGH_PRIORITY_VALUES:
                    continue
                if task.scheduled_end_at <= original_start:
                    continue
                if task.scheduled_start_at >= original_end:
                    continue
                # First overlapping high/urgent task wins; shift the habit
                # past the task's end.  If multiple tasks overlap the user
                # will see the shift relative to the earliest conflict.
                shift_reason = f"conflicts with {task_pri} task '{task.title}'"
                shifted = True
                start = task.scheduled_end_at
                end = start + duration
                break

            state_row = states_by_key.get((habit.id, occurrence_date))
            events.append(
                CalendarHabitEvent(
                    event_type=CalendarEventType.HABIT,
                    habit_id=habit.id,
                    title=habit.title,
                    priority=habit.priority,
                    start=start,
                    end=end,
                    original_start=original_start if shifted else None,
                    shift_reason=shift_reason,
                    state=state_row.state if state_row is not None else None,
                )
            )
    return events


def _coerce_priority(value: str | TaskPriority) -> TaskPriority:
    if isinstance(value, TaskPriority):
        return value
    try:
        return TaskPriority(value)
    except ValueError:
        return TaskPriority.NONE


def _enum_value(value: object) -> str:
    """Return the string value of an Enum, or ``str(value)`` for plain strings."""
    raw = getattr(value, "value", value)
    return str(raw)


def _event_start_key(
    event: CalendarTaskEvent | CalendarHabitEvent,
) -> datetime:
    if isinstance(event, CalendarTaskEvent):
        return event.scheduled_start_at
    return event.start
