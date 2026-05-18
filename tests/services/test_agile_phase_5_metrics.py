"""Service-layer tests for Agile Phase 5 flow metrics."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Employee, Task, TaskProject, TaskState
from app.services.task_flow_service import compute_flow_metrics_summary

pytestmark = pytest.mark.asyncio


async def _insert_employee(db_session: AsyncSession) -> Employee:
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": department_id, "name": f"Phase 5 Service Dept {department_id.hex[:8]}"},
    )
    employee_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, role, department_id, is_active)
            VALUES (:id, :name, :email, 'admin', :department_id, true)
            """
        ),
        {
            "id": employee_id,
            "name": "Phase 5 Service Admin",
            "email": f"{employee_id.hex[:12]}@p5-service.test",
            "department_id": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


async def _project_with_states(
    db_session: AsyncSession,
    creator: Employee,
) -> tuple[TaskProject, TaskState, TaskState, TaskState]:
    project = TaskProject(
        name=f"Phase 5 Service Project {uuid.uuid4().hex[:6]}",
        identifier=f"P5S{uuid.uuid4().hex[:4].upper()}",
        department_id=creator.department_id,
        created_by_id=creator.id,
        allow_any_employee=True,
    )
    db_session.add(project)
    await db_session.flush()

    todo = TaskState(
        task_project_id=project.id,
        name="Todo",
        group="todo",
        position=0,
        is_default=True,
    )
    doing = TaskState(
        task_project_id=project.id,
        name="Doing",
        group="in_progress",
        position=1000,
        is_default=False,
    )
    done = TaskState(
        task_project_id=project.id,
        name="Done",
        group="done",
        position=2000,
        is_default=False,
    )
    db_session.add_all([todo, doing, done])
    await db_session.flush()
    return project, todo, doing, done


async def _force_task_timestamps(
    db_session: AsyncSession,
    task_id: uuid.UUID,
    *,
    created_at: datetime,
    updated_at: datetime,
) -> None:
    await db_session.execute(
        text(
            """
            UPDATE tasks
            SET created_at = :created_at, updated_at = :updated_at
            WHERE id = :task_id
            """
        ),
        {"task_id": task_id, "created_at": created_at, "updated_at": updated_at},
    )
    await db_session.flush()


async def test_flow_metrics_without_sprints(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)
    creator = await _insert_employee(db_session)
    project, todo, doing, done = await _project_with_states(db_session, creator)
    now = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)

    blocked = Task(
        task_project_id=project.id,
        state_id=doing.id,
        title="Blocked without sprint",
        priority="none",
        sprint_id=None,
        blocked_reason="Waiting for approval",
    )
    done_task = Task(
        task_project_id=project.id,
        state_id=done.id,
        title="Done without sprint",
        priority="none",
        sprint_id=None,
        story_points=5,
    )
    todo_task = Task(
        task_project_id=project.id,
        state_id=todo.id,
        title="Queued without sprint",
        priority="none",
        sprint_id=None,
    )
    db_session.add_all([blocked, done_task, todo_task])
    await db_session.flush()
    await _force_task_timestamps(
        db_session,
        blocked.id,
        created_at=now - timedelta(days=6),
        updated_at=now - timedelta(days=2),
    )
    await _force_task_timestamps(
        db_session,
        done_task.id,
        created_at=now - timedelta(days=4),
        updated_at=now,
    )
    await _force_task_timestamps(
        db_session,
        todo_task.id,
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=1),
    )

    metrics = await compute_flow_metrics_summary(
        db_session,
        project.id,
        start_date=now.date(),
        end_date=now.date(),
    )

    assert metrics["cycle_time"] >= 0
    assert metrics["lead_time"] >= metrics["cycle_time"]
    assert metrics["throughput"] == 1
    assert metrics["blocked_count"] == 1
    assert metrics["wip_count"] == 2
    assert metrics["sprint_metrics"] == {}
    assert metrics["approximation_used"] is True


async def test_metrics_fallback_on_incomplete_activity_history(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)
    creator = await _insert_employee(db_session)
    project, _todo, _doing, done = await _project_with_states(db_session, creator)
    now = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)

    task = Task(
        task_project_id=project.id,
        state_id=done.id,
        title="No activity history",
        priority="none",
        story_points=3,
    )
    db_session.add(task)
    await db_session.flush()
    await _force_task_timestamps(
        db_session,
        task.id,
        created_at=now - timedelta(days=3),
        updated_at=now,
    )

    metrics = await compute_flow_metrics_summary(
        db_session,
        project.id,
        start_date=now.date(),
        end_date=now.date(),
    )

    assert metrics["throughput"] == 1
    assert metrics["lead_time"] >= 0
    assert metrics["cycle_time"] >= 0
    assert metrics["approximation_used"] is True
