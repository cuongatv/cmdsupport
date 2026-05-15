"""Personal habit planning, weekly calendar, and dashboard router.

All endpoints live under ``/api/me/*`` and require an authenticated employee.
Habit CRUD and per-date occurrence-state upserts are thin pass-throughs over
``app.services.habit_service``; the calendar and dashboard endpoints continue
to compose multiple services (task project, task dashboard, habit) inside the
HTTP boundary.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from math import ceil
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
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
from app.schemas.tasks import PaginatedResponse, TaskCreate, TaskOut, TaskUpdate
from app.services import habit_service
from app.services.auth_service import get_current_user
from app.services.task_constants import PRIORITY_LEVELS
from app.services.task_dashboard_service import (
    get_personal_dashboard_overview,
    list_user_units,
)
from app.services.task_project_service import get_or_create_personal_project
from app.services.task_service import create_task as create_task_record
from app.services.task_service import update_task as update_task_record

router = APIRouter(prefix="/me")

# Habits are personal-life events (eat lunch at 09:00, gym at 18:00). Users
# enter the time as a naive `time` in their own wall clock — for this product
# that is always Asia/Ho_Chi_Minh (BIDV is a Vietnam-only deployment). When
# we compose calendar events we anchor that wall-clock time to Hanoi tz so
# `09:00` shows up as `09:00` in the user's browser instead of being
# misinterpreted as UTC and shifted by +07:00.
HANOI_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Tasks at or above this priority displace habit blocks in the calendar view.
_HIGH_PRIORITY_VALUES: frozenset[str] = frozenset(
    {TaskPriority.HIGH.value, TaskPriority.URGENT.value}
)

# Habits at or below this priority auto-shift OUT of any task slot they
# happen to overlap. The intent: routine habits ("eat lunch at 12:00",
# "stretch at 15:00") should never block a real task — they slide to the
# next free 5-minute slot. High/urgent habits stay put (the user clearly
# meant that exact hour — show the conflict in the stack chip instead;
# urgent habits also get a warning icon on the calendar so the conflict is
# impossible to miss).
_LOW_PRIORITY_HABIT_VALUES: frozenset[str] = frozenset(
    {TaskPriority.NONE.value, TaskPriority.LOW.value, TaskPriority.MEDIUM.value}
)

# Habit auto-shift search bounds (Hanoi local hours). Search stops outside
# the work-day window so we don't push a 12:00 lunch habit to 23:30 just to
# clear a conflict.
_SHIFT_HOUR_START = 6
_SHIFT_HOUR_END = 22
_SHIFT_STEP = timedelta(minutes=5)


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
    # Anchor the week window in Hanoi local time so a task scheduled at
    # "Monday 09:00 Hanoi" lands inside the Monday..Sunday Hanoi week even
    # though it's stored as 02:00 UTC. Comparing against
    # `Task.scheduled_start_at` (DateTime(timezone=True)) works fine —
    # Postgres normalises both sides to UTC.
    window_start = datetime.combine(week_start, time.min, tzinfo=HANOI_TZ)
    window_end = datetime.combine(
        week_end + timedelta(days=1), time.min, tzinfo=HANOI_TZ
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
    # Build calendar events. Tasks with explicit scheduled_*  use those bounds;
    # tasks with only a due_date get rendered as a 30-minute marker ending at
    # the due time so the user still sees a block on the day they set as a
    # deadline. The fallback duration matches what the create-task dialog
    # would have set if the user had picked a start/end manually.
    #
    # Default-time rule: if the user did NOT pick an hour in the form, the
    # due_date is stored as midnight Hanoi (start of day). We display those
    # tasks at 09:00 Hanoi instead so they land in the visible work-hour band
    # rather than at the top of the calendar where 06:00 starts. Tasks with
    # any non-zero Hanoi-local time keep their picked time exactly.
    _DUE_BLOCK = timedelta(minutes=30)
    _DEFAULT_HOUR = 9  # 09:00 Hanoi when user only picks a date, no time
    task_events: list[CalendarTaskEvent] = []
    for t in tasks:
        if t.scheduled_start_at is not None and t.scheduled_end_at is not None:
            start = t.scheduled_start_at
            end = t.scheduled_end_at
        elif t.due_date is not None:
            local_due = t.due_date.astimezone(HANOI_TZ)
            if local_due.hour == 0 and local_due.minute == 0 and local_due.second == 0:
                end = local_due.replace(hour=_DEFAULT_HOUR, minute=30)
            else:
                end = t.due_date
            start = end - _DUE_BLOCK
        else:
            # Defensive: _list_scope_tasks already filters these out.
            continue
        task_events.append(
            CalendarTaskEvent(
                event_type=CalendarEventType.TASK,
                task_id=t.id,
                title=t.title,
                priority=_coerce_priority(t.priority),
                scheduled_start_at=start,
                scheduled_end_at=end,
                schedule_locked=t.schedule_locked,
            )
        )

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


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_my_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> Task:
    """Create a task in the caller's personal task project.

    The personal project (`TaskProject.owner_employee_id == current_user.id`)
    is lazy-materialised on first call. The caller is auto-added as the sole
    eligible assignee — assignee_ids defaults to [current_user.id] when the
    client doesn't supply one, so the task lands in "My Tasks" immediately.
    The state defaults to the project's first/default state if the body
    doesn't pick one.
    """
    project = await get_or_create_personal_project(db, current_user)

    # Personal project is owner-scoped; only the owner can be an assignee.
    # Reject any out-of-scope assignee at the router so the service error
    # ("employee is out of scope") doesn't leak as a 500.
    for assignee_id in body.assignee_ids:
        if assignee_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="personal tasks can only be assigned to yourself",
            )
    if not body.assignee_ids:
        body = body.model_copy(update={"assignee_ids": [current_user.id]})

    if body.state_id is None:
        result = await db.execute(
            select(TaskState)
            .where(TaskState.task_project_id == project.id)
            .order_by(
                TaskState.is_default.desc(),
                TaskState.position,
                TaskState.created_at,
            )
            .limit(1)
        )
        default_state = result.scalar_one_or_none()
        if default_state is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="personal project has no states",
            )
        body = body.model_copy(update={"state_id": default_state.id})

    try:
        task = await create_task_record(db, project.id, body, current_user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    await db.flush()
    await db.refresh(task)
    return task


class _MyTaskUpdate(BaseModel):
    """Personal-task PATCH body. Mirrors TaskUpdate except `version` is
    optional — the calendar drag-drop UX has no concept of a version field,
    so the router fills it in from the DB before delegating to the shared
    service. Concurrent-edit safety degrades to "last writer wins" for
    personal tasks, which is acceptable: only the owner can mutate them."""

    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    state_id: Optional[uuid.UUID] = None
    parent_task_id: Optional[uuid.UUID] = None
    reporter_id: Optional[uuid.UUID] = None
    due_date: Optional[datetime] = None
    scheduled_start_at: Optional[datetime] = None
    scheduled_end_at: Optional[datetime] = None
    schedule_locked: Optional[bool] = None
    version: Optional[int] = None


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_my_task(
    task_id: uuid.UUID,
    body: _MyTaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> Task:
    """Update a task in the caller's personal task project.

    Owner-only: returns 404 for tasks the caller doesn't own (no information
    leak about other users' personal projects). Wraps the shared
    `update_task` service so the same version-conflict + audit logic kicks in.
    Mostly used by the calendar drag-drop to push a new `due_date`, but
    accepts the full TaskUpdate body so future inline edits work too.
    """
    project = await get_or_create_personal_project(db, current_user)
    task = await db.get(Task, task_id)
    if task is None or task.deleted_at is not None or task.task_project_id != project.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="task not found",
        )
    # Fill in the current DB version when the client didn't supply one. Drag-
    # drop sends `{ due_date }` with no version; without this, TaskUpdate's
    # optimistic-lock check would reject every personal-task PATCH.
    update_payload = body.model_dump(exclude_unset=True)
    if "version" not in update_payload:
        update_payload["version"] = task.version
    service_body = TaskUpdate.model_validate(update_payload)
    try:
        updated = await update_task_record(db, task_id, service_body, current_user)
    except ValueError as exc:
        message = str(exc)
        if "version conflict" in message:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="version conflict"
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=message
        ) from exc
    await db.flush()
    await db.refresh(updated)
    return updated


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
    # Two ways a task lands on the calendar:
    #   1. It has an explicit (scheduled_start_at, scheduled_end_at) overlapping
    #      the visible week — the original "scheduled" lane.
    #   2. It only has a due_date inside the visible week. We surface those as
    #      a 30-minute marker ending at the due_date so a user who set "hạn
    #      15/05" sees a block at the right day even though they never picked
    #      a start/end time. Without this, personal tasks created via the
    #      simple due-date dialog would silently disappear from the calendar.
    scheduled_overlap = and_(
        Task.scheduled_start_at.is_not(None),
        Task.scheduled_end_at.is_not(None),
        Task.scheduled_start_at < window_end,
        Task.scheduled_end_at > window_start,
    )
    due_inside_window = and_(
        Task.scheduled_start_at.is_(None),
        Task.due_date.is_not(None),
        Task.due_date >= window_start,
        Task.due_date < window_end,
    )
    stmt = (
        select(Task)
        .where(
            project_filter,
            Task.deleted_at.is_(None),
            or_(scheduled_overlap, due_inside_window),
        )
        .order_by(Task.scheduled_start_at.nulls_last(), Task.due_date)
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

    Conflict policy:
    1. If a HIGH/URGENT task overlaps a habit, the habit shifts to the task's
       scheduled end (legacy behavior — keeps important tasks unblocked).
    2. If a habit's own priority is NONE/LOW and any task (any priority)
       overlaps it, search for the nearest free 5-minute slot — try AFTER
       first, then BEFORE, within work hours [_SHIFT_HOUR_START.._SHIFT_HOUR_END].
       Free = no overlap with any other task in `task_events`. If no free
       slot exists in the window, leave the habit at its original time and
       surface the conflict in the stack chip.
    3. Medium/high/urgent habits keep their preferred time when overlapped
       by a non-high task — the user clearly meant that hour.
    """
    events: list[CalendarHabitEvent] = []
    for habit in habits:
        active_set = {int(d) for d in (habit.active_days or [])}
        if not active_set:
            continue
        duration = timedelta(minutes=habit.duration_minutes)
        habit_pri = _enum_value(habit.priority)
        for offset in range(7):
            occurrence_date = week_start + timedelta(days=offset)
            if occurrence_date.weekday() not in active_set:
                continue
            original_start = datetime.combine(
                occurrence_date, habit.preferred_time, tzinfo=HANOI_TZ
            )
            original_end = original_start + duration

            shift_reason: Optional[str] = None
            shifted = False
            start = original_start
            end = original_end

            state_row = states_by_key.get((habit.id, occurrence_date))

            # Rule 0 (highest priority) — per-occurrence time override.
            # If the user dragged this habit to a new slot on this specific
            # day, `state_row.actual_start` carries the new wall-clock time.
            # That override beats both auto-shift rules and the
            # high/urgent-task displacement rule because it represents an
            # explicit user choice for this date only. The template
            # (preferred_time) is unchanged — every other day still renders
            # at the original time.
            if state_row is not None and state_row.actual_start is not None:
                start = datetime.combine(
                    occurrence_date,
                    state_row.actual_start,
                    tzinfo=HANOI_TZ,
                )
                end = start + duration
                shifted = start != original_start
                if shifted and not state_row.shift_reason:
                    shift_reason = "đã chỉnh giờ riêng cho ngày này"
                elif state_row.shift_reason:
                    shift_reason = state_row.shift_reason
            else:
                # Pre-compute the day's task intervals for fast overlap checks.
                day_lower = datetime.combine(
                    occurrence_date, time.min, tzinfo=HANOI_TZ
                )
                day_upper = day_lower + timedelta(days=1)
                day_tasks = [
                    t
                    for t in task_events
                    if t.scheduled_end_at > day_lower
                    and t.scheduled_start_at < day_upper
                ]

                # Rule 1 — high/urgent task displaces habit (legacy).
                displacing_task: Optional[CalendarTaskEvent] = None
                for task in day_tasks:
                    task_pri = _enum_value(task.priority)
                    if task_pri not in _HIGH_PRIORITY_VALUES:
                        continue
                    if task.scheduled_end_at <= original_start:
                        continue
                    if task.scheduled_start_at >= original_end:
                        continue
                    displacing_task = task
                    break
                if displacing_task is not None:
                    task_pri = _enum_value(displacing_task.priority)
                    shift_reason = (
                        f"conflicts with {task_pri} task "
                        f"'{displacing_task.title}'"
                    )
                    shifted = True
                    start = displacing_task.scheduled_end_at
                    end = start + duration
                elif habit_pri in _LOW_PRIORITY_HABIT_VALUES:
                    # Rule 2 — low/none habit slides out of any conflict.
                    conflict = _first_overlap(
                        day_tasks, original_start, original_end
                    )
                    if conflict is not None:
                        free = _find_free_slot(
                            day_tasks,
                            occurrence_date,
                            original_start,
                            duration,
                        )
                        if free is not None:
                            start, end = free
                            shifted = True
                            shift_reason = (
                                f"trùng giờ '{conflict.title}', "
                                "tự dời sang khung trống"
                            )
                        # else: leave at original_start; UI stack chip will
                        # surface the conflict.

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


def _first_overlap(
    tasks: list[CalendarTaskEvent],
    start: datetime,
    end: datetime,
) -> Optional[CalendarTaskEvent]:
    """Return the first task whose [start, end) interval overlaps [start, end)."""
    for t in tasks:
        if t.scheduled_end_at <= start:
            continue
        if t.scheduled_start_at >= end:
            continue
        return t
    return None


def _find_free_slot(
    tasks: list[CalendarTaskEvent],
    occurrence_date: date,
    preferred_start: datetime,
    duration: timedelta,
) -> Optional[tuple[datetime, datetime]]:
    """Search for a free contiguous slot of `duration` near `preferred_start`.

    Strategy: scan AFTER `preferred_start` first (user-stated preference for
    "ưu tiên chuyển ra sau"); if no slot found in the day's work-hour window,
    scan BEFORE `preferred_start`. Search step is 5 minutes — fine-grained
    enough to feel responsive without exploding the search space.

    Bounds: [_SHIFT_HOUR_START..(_SHIFT_HOUR_END - duration)] in Hanoi local
    time of `occurrence_date`. Returns None if no slot fits within the day.
    """
    day_start = datetime.combine(
        occurrence_date,
        time(hour=_SHIFT_HOUR_START),
        tzinfo=HANOI_TZ,
    )
    last_possible_start = datetime.combine(
        occurrence_date,
        time(hour=_SHIFT_HOUR_END),
        tzinfo=HANOI_TZ,
    ) - duration
    if last_possible_start < day_start:
        return None

    def fits(candidate_start: datetime) -> bool:
        candidate_end = candidate_start + duration
        return _first_overlap(tasks, candidate_start, candidate_end) is None

    # Forward scan: from the conflict's end, snap to next 5-min boundary.
    conflict = _first_overlap(tasks, preferred_start, preferred_start + duration)
    forward_anchor = (
        conflict.scheduled_end_at if conflict is not None else preferred_start
    )
    # Snap up to the next _SHIFT_STEP boundary.
    forward_minutes = forward_anchor.minute
    snap_remainder = forward_minutes % (_SHIFT_STEP.seconds // 60)
    if snap_remainder:
        forward_anchor = forward_anchor + timedelta(
            minutes=(_SHIFT_STEP.seconds // 60) - snap_remainder
        )
        forward_anchor = forward_anchor.replace(second=0, microsecond=0)

    candidate = forward_anchor
    while candidate <= last_possible_start:
        if fits(candidate):
            return candidate, candidate + duration
        # Skip past the next conflict if any to avoid O(n²) thrashing.
        next_conflict = _first_overlap(tasks, candidate, candidate + duration)
        if next_conflict is None:
            candidate = candidate + _SHIFT_STEP
        else:
            candidate = next_conflict.scheduled_end_at

    # Backward scan: from preferred_start - duration, walk back in 5-min steps.
    candidate = preferred_start - _SHIFT_STEP
    while candidate >= day_start:
        if fits(candidate):
            return candidate, candidate + duration
        candidate = candidate - _SHIFT_STEP

    return None


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
