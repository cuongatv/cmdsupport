"""Service-layer tests for Phase 1 Agile WIP advisory behaviour."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.config import settings
from app.database.models import Employee, TaskActivity
from app.schemas.tasks import TaskCreate, TaskProjectCreate
from app.services.task_constants import WIP_EXCEEDED_ERROR_CODE
from app.services.task_project_service import create_task_project
from app.services.task_service import (
    WipExceededError,
    create_task,
    move_task_state,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


async def _insert_department(db_session) -> uuid.UUID:
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {
            "id": department_id,
            "name": f"WIP Dept {department_id.hex[:8]}",
        },
    )
    return department_id


async def _insert_workspace(db_session) -> uuid.UUID:
    workspace_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
        {
            "id": workspace_id,
            "name": f"WIP Workspace {workspace_id.hex[:8]}",
        },
    )
    return workspace_id


async def _insert_employee(db_session) -> Employee:
    department_id = await _insert_department(db_session)
    employee_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, role, department_id, is_active)
            VALUES (:id, :name, :email, 'employee', :department_id, true)
            """
        ),
        {
            "id": employee_id,
            "name": f"WIP Tester {employee_id.hex[:6]}",
            "email": f"{employee_id.hex[:12]}@example.test",
            "department_id": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


async def _workspace_project(db_session):
    workspace_id = await _insert_workspace(db_session)
    creator = await _insert_employee(db_session)
    project = await create_task_project(
        db_session,
        TaskProjectCreate(
            name="WIP Project",
            identifier=f"WIP{workspace_id.hex[:4].upper()}",
            workspace_id=workspace_id,
        ),
        creator,
    )
    states = sorted(project.states, key=lambda state: state.position)
    return project, states, creator


async def _make_task(db_session, project_id, state_id, actor, *, title="Task"):
    return await create_task(
        db_session,
        project_id,
        TaskCreate(title=title, state_id=state_id),
        actor,
    )


async def _set_wip(db_session, state, *, limit, policy):
    state.wip_limit = limit
    state.wip_policy = policy
    db_session.add(state)
    await db_session.flush()


async def _wip_activities(db_session, task_id):
    result = await db_session.execute(
        select(TaskActivity).where(
            TaskActivity.task_id == task_id,
            TaskActivity.verb == "wip_advisory_warned",
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Required scenarios
# ---------------------------------------------------------------------------


async def test_wip_warn_allows_move_and_records_audit(db_session, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    project, states, actor = await _workspace_project(db_session)
    backlog, in_progress = states[0], states[2]

    # State already at WIP limit (1 task in In Progress, warn policy).
    existing = await _make_task(
        db_session, project.id, in_progress.id, actor, title="existing"
    )
    assert existing.state_id == in_progress.id
    await _set_wip(db_session, in_progress, limit=1, policy="warn")

    task = await _make_task(db_session, project.id, backlog.id, actor, title="moving")

    moved, advisory, _ = await move_task_state(
        db_session, task.id, in_progress.id, 5000.0, actor
    )

    # Move succeeded.
    assert moved.state_id == in_progress.id
    # Advisory payload returned to caller.
    assert advisory is not None
    assert advisory["code"] == WIP_EXCEEDED_ERROR_CODE
    assert advisory["policy"] == "warn"
    assert advisory["wip_limit"] == 1
    assert advisory["current_count"] == 1
    assert advisory["projected_count"] == 2

    # Activity row recorded for audit trail.
    advisory_rows = await _wip_activities(db_session, moved.id)
    assert len(advisory_rows) == 1
    assert advisory_rows[0].actor_id == actor.id
    assert advisory_rows[0].meta["wip_limit"] == 1


async def test_wip_enforce_blocks_move(db_session, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    project, states, actor = await _workspace_project(db_session)
    backlog, in_progress = states[0], states[2]

    blocker = await _make_task(
        db_session, project.id, in_progress.id, actor, title="blocker"
    )
    assert blocker.state_id == in_progress.id
    await _set_wip(db_session, in_progress, limit=1, policy="enforce")

    task = await _make_task(db_session, project.id, backlog.id, actor, title="moving")
    original_version = task.version

    with pytest.raises(WipExceededError) as exc:
        await move_task_state(db_session, task.id, in_progress.id, 5000.0, actor)
    assert exc.value.code == WIP_EXCEEDED_ERROR_CODE
    assert exc.value.limit == 1
    assert exc.value.state_id == in_progress.id

    # Task NOT moved and version unchanged.
    await db_session.refresh(task)
    assert task.state_id == backlog.id
    assert task.version == original_version

    # No advisory activity row created on enforce reject.
    advisory_rows = await _wip_activities(db_session, task.id)
    assert advisory_rows == []


async def test_wip_off_policy_allows_move_no_audit(db_session, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    project, states, actor = await _workspace_project(db_session)
    backlog, in_progress = states[0], states[2]

    # Pile tasks into the target state but keep wip_policy='off' (default).
    for index in range(3):
        await _make_task(
            db_session, project.id, in_progress.id, actor, title=f"filler-{index}"
        )
    # Even setting a tiny limit must NOT trigger when policy is off.
    await _set_wip(db_session, in_progress, limit=1, policy="off")

    task = await _make_task(db_session, project.id, backlog.id, actor, title="off")
    moved, advisory, _ = await move_task_state(
        db_session, task.id, in_progress.id, 9000.0, actor
    )

    assert moved.state_id == in_progress.id
    assert advisory is None
    assert await _wip_activities(db_session, moved.id) == []


async def test_feature_flag_off_skips_wip_check(db_session, monkeypatch):
    # Even with enforce policy + over limit, flag OFF preserves legacy behaviour.
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", False)
    project, states, actor = await _workspace_project(db_session)
    backlog, in_progress = states[0], states[2]

    existing = await _make_task(
        db_session, project.id, in_progress.id, actor, title="existing"
    )
    assert existing.state_id == in_progress.id
    await _set_wip(db_session, in_progress, limit=1, policy="enforce")

    task = await _make_task(db_session, project.id, backlog.id, actor, title="legacy")
    moved, advisory, _ = await move_task_state(
        db_session, task.id, in_progress.id, 4000.0, actor
    )

    assert moved.state_id == in_progress.id
    assert advisory is None
    assert await _wip_activities(db_session, moved.id) == []


# ---------------------------------------------------------------------------
# Regression guards
# ---------------------------------------------------------------------------


async def test_stale_version_still_returns_conflict(db_session, monkeypatch):
    """Optimistic concurrency must keep raising for stale move requests."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    project, states, actor = await _workspace_project(db_session)
    backlog, in_progress = states[0], states[2]

    task = await _make_task(db_session, project.id, backlog.id, actor, title="stale")
    stale_version = task.version - 1

    with pytest.raises(ValueError, match="version conflict"):
        await move_task_state(
            db_session,
            task.id,
            in_progress.id,
            1000.0,
            actor,
            expected_version=stale_version,
        )


async def test_warn_policy_below_limit_emits_no_advisory(db_session, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    project, states, actor = await _workspace_project(db_session)
    backlog, in_progress = states[0], states[2]

    await _set_wip(db_session, in_progress, limit=5, policy="warn")

    task = await _make_task(db_session, project.id, backlog.id, actor, title="ok")
    moved, advisory, _ = await move_task_state(
        db_session, task.id, in_progress.id, 1000.0, actor
    )

    assert moved.state_id == in_progress.id
    assert advisory is None
    assert await _wip_activities(db_session, moved.id) == []
