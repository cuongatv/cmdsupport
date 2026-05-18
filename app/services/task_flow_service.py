"""Phase 5 Agile flow metrics service.

The service owns snapshot capture and read-side metric queries for cumulative
flow and throughput. It is deliberately advisory/read-only: when the Phase 5
feature flag is disabled every public function short-circuits to an empty/zero
result so callers can keep wiring in place during rollout.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from loguru import logger
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.config import settings
from app.database.models import (
    Task,
    TaskActivity,
    TaskFlowSnapshot,
    TaskProject,
    TaskState,
)


def _normalise_date(value: date | datetime | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    return value


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min)


def _end_of_day(value: date) -> datetime:
    return datetime.combine(value, time.max)


def _activity_exists_stmt(task_id_column) -> Select[tuple[bool]]:
    return select(TaskActivity.id).where(TaskActivity.task_id == task_id_column).limit(1)


async def capture_flow_snapshot(
    db: AsyncSession,
    task_project_id: uuid.UUID,
    *,
    snapshot_date: date | datetime | None = None,
) -> list[TaskFlowSnapshot]:
    """Capture current task counts per state for ``task_project_id``.

    Idempotent by date: if any snapshot row already exists for this project/date,
    the function logs an advisory and returns the existing rows without writing.
    """
    if not settings.FEATURE_AGILE_PHASE_5:
        return []

    project = await db.get(TaskProject, task_project_id)
    if project is None:
        raise ValueError("task project not found")

    captured_on = _normalise_date(snapshot_date)
    existing_stmt = (
        select(TaskFlowSnapshot)
        .where(
            TaskFlowSnapshot.task_project_id == task_project_id,
            TaskFlowSnapshot.snapshot_date == captured_on,
        )
        .order_by(TaskFlowSnapshot.snapshot_date.asc(), TaskFlowSnapshot.state_id.asc())
    )
    existing = list((await db.execute(existing_stmt)).scalars().all())
    if existing:
        logger.info(
            "capture_flow_snapshot: project={} date={} already captured rows={}",
            task_project_id,
            captured_on,
            len(existing),
        )
        return existing

    counts_stmt = (
        select(
            Task.state_id,
            func.count(Task.id).label("task_count"),
            func.sum(Task.story_points).label("story_points_sum"),
            func.sum(case((Task.blocked_reason.is_not(None), 1), else_=0)).label(
                "blocked_count"
            ),
        )
        .where(
            Task.task_project_id == task_project_id,
            Task.deleted_at.is_(None),
        )
        .group_by(Task.state_id)
        .execution_options(populate_existing=True)
    )
    result = await db.execute(counts_stmt)

    snapshots: list[TaskFlowSnapshot] = []
    for row in result.all():
        snapshot = TaskFlowSnapshot(
            task_project_id=task_project_id,
            snapshot_date=captured_on,
            state_id=row.state_id,
            task_count=int(row.task_count or 0),
            story_points_sum=(
                int(row.story_points_sum) if row.story_points_sum is not None else None
            ),
            blocked_count=int(row.blocked_count or 0),
        )
        db.add(snapshot)
        snapshots.append(snapshot)

    if not snapshots:
        logger.info(
            "capture_flow_snapshot: project={} date={} has no tasks to snapshot",
            task_project_id,
            captured_on,
        )
        return []

    await db.flush()
    return snapshots


async def get_flow_metrics(
    db: AsyncSession,
    task_project_id: uuid.UUID,
    *,
    start_date: date | datetime,
    end_date: date | datetime,
) -> list[TaskFlowSnapshot]:
    """Return snapshot rows for a project/date range, oldest first."""
    if not settings.FEATURE_AGILE_PHASE_5:
        return []

    project = await db.get(TaskProject, task_project_id)
    if project is None:
        raise ValueError("task project not found")

    start = _normalise_date(start_date)
    end = _normalise_date(end_date)
    stmt = (
        select(TaskFlowSnapshot)
        .where(
            TaskFlowSnapshot.task_project_id == task_project_id,
            TaskFlowSnapshot.snapshot_date >= start,
            TaskFlowSnapshot.snapshot_date <= end,
        )
        .order_by(TaskFlowSnapshot.snapshot_date.asc(), TaskFlowSnapshot.state_id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_throughput(
    db: AsyncSession,
    task_project_id: uuid.UUID,
    *,
    start_date: date | datetime,
    end_date: date | datetime,
) -> dict[str, int]:
    """Count tasks completed in the range using ``Task.updated_at`` as proxy."""
    if not settings.FEATURE_AGILE_PHASE_5:
        return {"tasks_completed": 0, "story_points_completed": 0}

    project = await db.get(TaskProject, task_project_id)
    if project is None:
        raise ValueError("task project not found")

    start = _normalise_date(start_date)
    end = _normalise_date(end_date)
    stmt = (
        select(
            func.count(Task.id).label("tasks_completed"),
            func.coalesce(func.sum(Task.story_points), 0).label(
                "story_points_completed"
            ),
        )
        .join(TaskState, TaskState.id == Task.state_id)
        .where(
            Task.task_project_id == task_project_id,
            Task.deleted_at.is_(None),
            TaskState.group == "done",
            Task.updated_at >= _start_of_day(start),
            Task.updated_at <= _end_of_day(end),
        )
        .execution_options(populate_existing=True)
    )
    row = (await db.execute(stmt)).one()
    return {
        "tasks_completed": int(row.tasks_completed or 0),
        "story_points_completed": int(row.story_points_completed or 0),
    }


async def compute_flow_metrics_summary(
    db: AsyncSession,
    task_project_id: uuid.UUID,
    *,
    start_date: date | datetime,
    end_date: date | datetime,
) -> dict[str, object]:
    """Return lightweight Phase 5 flow metrics for dashboards/tests.

    Historical task movement was not fully captured before the Agile rollout.
    This summary therefore uses exact counters where possible (current WIP,
    blocked count, throughput) and falls back to ``Task.created_at`` /
    ``Task.updated_at`` deltas for cycle/lead time when activity transitions are
    incomplete. ``approximation_used`` documents that caveat for callers.
    """
    if not settings.FEATURE_AGILE_PHASE_5:
        return {
            "cycle_time": 0.0,
            "lead_time": 0.0,
            "throughput": 0,
            "blocked_count": 0,
            "wip_count": 0,
            "sprint_metrics": {},
            "approximation_used": False,
        }

    project = await db.get(TaskProject, task_project_id)
    if project is None:
        raise ValueError("task project not found")

    start = _normalise_date(start_date)
    end = _normalise_date(end_date)
    start_dt = _start_of_day(start)
    end_dt = _end_of_day(end)

    completed_stmt = (
        select(
            Task.created_at,
            Task.updated_at,
            Task.sprint_id,
            _activity_exists_stmt(Task.id).exists().label("has_activity"),
        )
        .join(TaskState, TaskState.id == Task.state_id)
        .where(
            Task.task_project_id == task_project_id,
            Task.deleted_at.is_(None),
            TaskState.group == "done",
            Task.updated_at >= start_dt,
            Task.updated_at <= end_dt,
        )
        .execution_options(populate_existing=True)
    )
    completed_rows = (await db.execute(completed_stmt)).all()

    active_stmt = (
        select(
            func.count(Task.id).label("wip_count"),
            func.sum(case((Task.blocked_reason.is_not(None), 1), else_=0)).label(
                "blocked_count"
            ),
        )
        .join(TaskState, TaskState.id == Task.state_id)
        .where(
            Task.task_project_id == task_project_id,
            Task.deleted_at.is_(None),
            TaskState.group.not_in(("done", "cancelled")),
        )
        .execution_options(populate_existing=True)
    )
    active_row = (await db.execute(active_stmt)).one()

    durations: list[float] = []
    approximation_used = False
    sprint_counts: dict[str, int] = {}
    for row in completed_rows:
        if row.created_at is not None and row.updated_at is not None:
            seconds = max(0.0, (row.updated_at - row.created_at).total_seconds())
            durations.append(seconds / 86400)
        if not row.has_activity:
            approximation_used = True
        if row.sprint_id is not None:
            key = str(row.sprint_id)
            sprint_counts[key] = sprint_counts.get(key, 0) + 1

    avg_lead = sum(durations) / len(durations) if durations else 0.0
    throughput = len(completed_rows)
    wip_count = int(active_row.wip_count or 0)
    blocked_count = int(active_row.blocked_count or 0)
    cycle_time = (wip_count / throughput) if throughput > 0 else 0.0

    return {
        "cycle_time": round(cycle_time, 2),
        "lead_time": round(avg_lead, 2),
        "throughput": throughput,
        "blocked_count": blocked_count,
        "wip_count": wip_count,
        "sprint_metrics": sprint_counts,
        "approximation_used": approximation_used,
    }
