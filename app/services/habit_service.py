"""Personal habit CRUD and occurrence-state service.

Pure-Python (no FastAPI imports), async-first, takes ``AsyncSession`` as the
first argument. Mirrors the ``task_service`` convention: services flush and
refresh but never commit — ``get_db()`` auto-commits at the request boundary,
or the calling router can commit explicitly when it needs the persisted row
before returning.

Ownership rules:
  * Every helper that touches an existing habit row goes through
    :func:`get_habit`, which raises ``ValueError`` when the row is missing and
    ``PermissionError`` when the caller is not the owner. The /api/me router
    translates both to ``HTTP 404`` so cross-owner access does not leak resource
    existence.
  * Soft-delete via :func:`delete_habit` flips ``is_active`` to ``False`` so
    historical occurrence rows are preserved for the dashboard / audit trail.
"""

from __future__ import annotations

import uuid
from datetime import date, time
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    HabitOccurrenceState,
    HabitOccurrenceStatus,
    PersonalHabit,
)
from app.schemas.habits import HabitCreate, HabitUpdate


async def list_habits(
    db: AsyncSession,
    employee_id: uuid.UUID,
    include_inactive: bool = False,
) -> list[PersonalHabit]:
    """Return habits owned by ``employee_id`` ordered by preferred time."""
    stmt = select(PersonalHabit).where(PersonalHabit.owner_employee_id == employee_id)
    if not include_inactive:
        stmt = stmt.where(PersonalHabit.is_active.is_(True))
    stmt = stmt.order_by(PersonalHabit.preferred_time, PersonalHabit.created_at)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_habit(
    db: AsyncSession,
    employee_id: uuid.UUID,
    body: HabitCreate,
) -> PersonalHabit:
    """Persist a new ``PersonalHabit`` owned by ``employee_id`` (flush only)."""
    habit = PersonalHabit(
        owner_employee_id=employee_id,
        title=body.title,
        priority=body.priority,
        preferred_time=body.preferred_time,
        duration_minutes=body.duration_minutes,
        active_days=list(body.active_days),
        is_active=body.is_active,
    )
    db.add(habit)
    await db.flush()
    await db.refresh(habit)
    logger.info(
        "habit.create owner={} habit={} title={}",
        employee_id,
        habit.id,
        habit.title,
    )
    return habit


async def get_habit(
    db: AsyncSession,
    habit_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> PersonalHabit:
    """Fetch a habit and assert ``employee_id`` owns it.

    Raises
    ------
    ValueError
        When the habit row does not exist. The router maps this to ``404``.
    PermissionError
        When the caller is not the owner. The router maps this to ``403``.
    """
    habit = await db.get(PersonalHabit, habit_id)
    if habit is None:
        raise ValueError("habit not found")
    if habit.owner_employee_id != employee_id:
        raise PermissionError("habit access denied")
    return habit


async def update_habit(
    db: AsyncSession,
    habit_id: uuid.UUID,
    employee_id: uuid.UUID,
    body: HabitUpdate,
) -> PersonalHabit:
    """Patch fields on an owned habit (flush only). Unset fields stay as-is."""
    habit = await get_habit(db, habit_id, employee_id)
    payload = body.model_dump(exclude_unset=True)
    for field_name, value in payload.items():
        setattr(habit, field_name, value)
    await db.flush()
    await db.refresh(habit)
    logger.info(
        "habit.update owner={} habit={} fields={}",
        employee_id,
        habit.id,
        sorted(payload.keys()),
    )
    return habit


async def delete_habit(
    db: AsyncSession,
    habit_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> None:
    """Soft-delete an owned habit by flipping ``is_active`` to ``False``.

    Hard-delete would orphan historical ``HabitOccurrenceState`` rows; the
    soft path keeps the audit trail and lets the calendar simply skip the row.
    """
    habit = await get_habit(db, habit_id, employee_id)
    habit.is_active = False
    await db.flush()
    logger.info("habit.delete owner={} habit={}", employee_id, habit.id)


async def upsert_occurrence(
    db: AsyncSession,
    habit_id: uuid.UUID,
    employee_id: uuid.UUID,
    occurrence_date: date,
    state: HabitOccurrenceStatus,
    actual_start: Optional[time] = None,
    shift_reason: Optional[str] = None,
) -> HabitOccurrenceState:
    """Upsert the per-date state for an owned habit (select-then-insert/update).

    The ``uq_habit_occurrence_state_habit_date`` unique constraint guarantees
    one row per ``(habit_id, occurrence_date)`` pair, so the select-or-create
    pattern is safe inside a single transaction.
    """
    habit = await get_habit(db, habit_id, employee_id)

    existing = (
        await db.execute(
            select(HabitOccurrenceState).where(
                HabitOccurrenceState.habit_id == habit.id,
                HabitOccurrenceState.occurrence_date == occurrence_date,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.state = state
        existing.actual_start = actual_start
        existing.shift_reason = shift_reason
        await db.flush()
        await db.refresh(existing)
        return existing

    row = HabitOccurrenceState(
        habit_id=habit.id,
        occurrence_date=occurrence_date,
        state=state,
        actual_start=actual_start,
        shift_reason=shift_reason,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row
