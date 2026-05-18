"""Phase 5 governance — Stage A advisory tests.

Verifies the three advisory pathways added in T20:

* Sprint close without ``agile.sprint.close`` → action succeeds,
  ``permission_denied_advisory`` audit row, response advisory metadata.
* WIP advisory move without ``agile.wip.override`` → move still succeeds
  (warn policy), permission advisory recorded, audit row written.
* Move-to-done with incomplete DoD without ``agile.dod.bypass`` → move
  succeeds, permission advisory recorded, audit row written.

The tests intentionally use a non-admin ``employee`` actor with no custom
role attached; ``_get_user_permissions`` then resolves to
``EMPLOYEE_DEFAULT_PERMISSIONS``, which contains none of the ``agile.*``
strings. Service calls are exercised directly so we never have to plumb a
non-admin through ``require_permission`` — the contract under test is the
service-layer advisory + audit, not RBAC routing.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.config import settings
from app.database.models import AuditLog, Employee, TaskActivity
from app.schemas.tasks import SprintCreate, TaskCreate, TaskProjectCreate
from app.services.agile_governance import (
    PERMISSION_ADVISORY_AUDIT_ACTION,
    PERMISSION_ADVISORY_CODE,
    PERMISSION_AGILE_DOD_BYPASS,
    PERMISSION_AGILE_SPRINT_CLOSE,
    PERMISSION_AGILE_WIP_OVERRIDE,
)
from app.services.sprint_service import (
    close_sprint,
    create_sprint,
    start_sprint,
)
from app.services.task_constants import WIP_EXCEEDED_ERROR_CODE
from app.services.task_project_service import create_task_project
from app.services.task_service import create_task, move_task_state

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Shared fixtures / helpers — mirrors test_agile_phase_1 to stay independent.
# ---------------------------------------------------------------------------


async def _insert_department(db_session) -> uuid.UUID:
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {
            "id": department_id,
            "name": f"Governance Dept {department_id.hex[:8]}",
        },
    )
    return department_id


async def _insert_workspace(db_session) -> uuid.UUID:
    workspace_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
        {
            "id": workspace_id,
            "name": f"Governance Workspace {workspace_id.hex[:8]}",
        },
    )
    return workspace_id


async def _insert_employee(db_session) -> Employee:
    """Create a non-admin ``employee`` with no custom role attached.

    ``_get_user_permissions`` falls back to ``EMPLOYEE_DEFAULT_PERMISSIONS``
    which contains zero ``agile.*`` strings, so every Stage A advisory in
    these tests is guaranteed to fire.
    """
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
            "name": f"Governance Actor {employee_id.hex[:6]}",
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
            name="Governance Project",
            identifier=f"GV{workspace_id.hex[:4].upper()}",
            workspace_id=workspace_id,
        ),
        creator,
    )
    states = sorted(project.states, key=lambda state: state.position)
    return project, states, creator


async def _advisory_rows(
    db_session,
    *,
    resource_type: str,
    resource_id: uuid.UUID,
    permission: str,
) -> list[AuditLog]:
    """Return ``permission_denied_advisory`` audit rows for a (resource, perm)."""
    result = await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == PERMISSION_ADVISORY_AUDIT_ACTION,
            AuditLog.resource_type == resource_type,
            AuditLog.resource_id == str(resource_id),
            AuditLog.reason == permission,
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# 1. Sprint close advisory
# ---------------------------------------------------------------------------


async def test_sprint_close_advisory_allows_and_audits(
    db_session, monkeypatch
):
    """Closing a sprint without ``agile.sprint.close`` still succeeds (200-equivalent),
    but logs a ``permission_denied_advisory`` row and returns advisory metadata.
    """
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)

    project, _states, actor = await _workspace_project(db_session)
    sprint = await create_sprint(
        db_session,
        project.id,
        SprintCreate(name="Sprint Governance"),
        actor=actor,
    )
    await start_sprint(db_session, sprint.id, actor=actor)

    closed_sprint, advisory = await close_sprint(
        db_session, sprint.id, actor=actor
    )

    # Action succeeded — sprint is completed regardless of permission.
    assert closed_sprint.status == "completed"

    # Advisory dict returned to caller for response metadata.
    assert advisory is not None
    assert advisory["code"] == PERMISSION_ADVISORY_CODE
    assert advisory["permission"] == PERMISSION_AGILE_SPRINT_CLOSE

    # Audit row recorded with the permission string as ``reason``.
    rows = await _advisory_rows(
        db_session,
        resource_type="sprint",
        resource_id=sprint.id,
        permission=PERMISSION_AGILE_SPRINT_CLOSE,
    )
    assert len(rows) == 1
    assert rows[0].principal_id == actor.id
    assert rows[0].decision == "ALLOW"


async def test_sprint_close_with_permission_skips_advisory(
    db_session, monkeypatch
):
    """Regression guard: admin (which carries every permission) never trips advisory."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)

    project, _states, actor = await _workspace_project(db_session)
    # Upgrade the actor to admin — ``_get_user_permissions`` returns ALL_PERMISSIONS.
    actor.role = "admin"
    db_session.add(actor)
    await db_session.flush()

    sprint = await create_sprint(
        db_session,
        project.id,
        SprintCreate(name="Sprint Admin Close"),
        actor=actor,
    )
    await start_sprint(db_session, sprint.id, actor=actor)

    _closed, advisory = await close_sprint(db_session, sprint.id, actor=actor)
    assert advisory is None

    rows = await _advisory_rows(
        db_session,
        resource_type="sprint",
        resource_id=sprint.id,
        permission=PERMISSION_AGILE_SPRINT_CLOSE,
    )
    assert rows == []


async def test_sprint_close_advisory_skipped_when_phase_5_off(
    db_session, monkeypatch
):
    """Phase 5 flag off ⇒ no governance side-effects even for non-admin actors."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", False)

    project, _states, actor = await _workspace_project(db_session)
    sprint = await create_sprint(
        db_session,
        project.id,
        SprintCreate(name="Sprint Flag Off"),
        actor=actor,
    )
    await start_sprint(db_session, sprint.id, actor=actor)

    _closed, advisory = await close_sprint(db_session, sprint.id, actor=actor)
    assert advisory is None

    rows = await _advisory_rows(
        db_session,
        resource_type="sprint",
        resource_id=sprint.id,
        permission=PERMISSION_AGILE_SPRINT_CLOSE,
    )
    assert rows == []


# ---------------------------------------------------------------------------
# 2. WIP override advisory
# ---------------------------------------------------------------------------


async def test_wip_override_without_permission_advisory_allows_and_audits(
    db_session, monkeypatch
):
    """WIP warn move without ``agile.wip.override`` allows the move and audits."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)

    project, states, actor = await _workspace_project(db_session)
    backlog, in_progress = states[0], states[2]

    # Saturate the target state at its warn limit so the next move triggers WIP.
    existing = await create_task(
        db_session,
        project.id,
        TaskCreate(title="existing", state_id=in_progress.id),
        actor,
    )
    assert existing.state_id == in_progress.id
    in_progress.wip_limit = 1
    in_progress.wip_policy = "warn"
    db_session.add(in_progress)
    await db_session.flush()

    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="moving", state_id=backlog.id),
        actor,
    )

    moved, wip_advisory, permission_advisories = await move_task_state(
        db_session, task.id, in_progress.id, 5000.0, actor
    )

    # Move succeeded (warn policy never blocks).
    assert moved.state_id == in_progress.id
    # Existing WIP warn advisory still surfaces as before.
    assert wip_advisory is not None
    assert wip_advisory["code"] == WIP_EXCEEDED_ERROR_CODE
    # New permission advisory rides alongside the WIP advisory.
    assert any(
        adv["code"] == PERMISSION_ADVISORY_CODE
        and adv["permission"] == PERMISSION_AGILE_WIP_OVERRIDE
        for adv in permission_advisories
    )

    rows = await _advisory_rows(
        db_session,
        resource_type="task",
        resource_id=task.id,
        permission=PERMISSION_AGILE_WIP_OVERRIDE,
    )
    assert len(rows) == 1
    assert rows[0].principal_id == actor.id


async def test_wip_advisory_skipped_when_no_wip_event(
    db_session, monkeypatch
):
    """Regression guard: a move below the WIP limit emits no permission advisory."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)

    project, states, actor = await _workspace_project(db_session)
    backlog, in_progress = states[0], states[2]

    # High limit so the move never trips the WIP advisory.
    in_progress.wip_limit = 100
    in_progress.wip_policy = "warn"
    db_session.add(in_progress)
    await db_session.flush()

    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="below-limit", state_id=backlog.id),
        actor,
    )
    moved, wip_advisory, permission_advisories = await move_task_state(
        db_session, task.id, in_progress.id, 1000.0, actor
    )

    assert moved.state_id == in_progress.id
    assert wip_advisory is None
    assert permission_advisories == []

    rows = await _advisory_rows(
        db_session,
        resource_type="task",
        resource_id=task.id,
        permission=PERMISSION_AGILE_WIP_OVERRIDE,
    )
    assert rows == []


# ---------------------------------------------------------------------------
# 3. DoD bypass advisory
# ---------------------------------------------------------------------------


async def test_dod_bypass_advisory_allows_and_audits(
    db_session, monkeypatch
):
    """Move-to-done with incomplete DoD without ``agile.dod.bypass`` audits + advises."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)

    project, states, actor = await _workspace_project(db_session)
    backlog = states[0]
    done = next(state for state in states if state.group == "done")

    dod_checklist = [
        {"label": "Tests pass", "done": False},
        {"label": "Docs updated", "done": False},
    ]
    task = await create_task(
        db_session,
        project.id,
        TaskCreate(
            title="dod-incomplete",
            state_id=backlog.id,
            dod_checklist=dod_checklist,
        ),
        actor,
    )

    moved, wip_advisory, permission_advisories = await move_task_state(
        db_session, task.id, done.id, 5000.0, actor
    )

    # Move to Done succeeded.
    assert moved.state_id == done.id
    # No WIP situation here, so wip_advisory stays None.
    assert wip_advisory is None
    # DoD bypass advisory present.
    assert any(
        adv["code"] == PERMISSION_ADVISORY_CODE
        and adv["permission"] == PERMISSION_AGILE_DOD_BYPASS
        for adv in permission_advisories
    )

    rows = await _advisory_rows(
        db_session,
        resource_type="task",
        resource_id=task.id,
        permission=PERMISSION_AGILE_DOD_BYPASS,
    )
    assert len(rows) == 1
    assert rows[0].principal_id == actor.id

    # ``state_changed`` activity still emitted alongside the advisory — the
    # advisory must not suppress the normal state-change feed entry.
    activity_rows = await db_session.execute(
        select(TaskActivity).where(
            TaskActivity.task_id == task.id,
            TaskActivity.verb == "state_changed",
        )
    )
    assert activity_rows.scalars().first() is not None


async def test_dod_bypass_skipped_when_all_items_done(
    db_session, monkeypatch
):
    """Regression guard: complete checklist never triggers DoD advisory."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)

    project, states, actor = await _workspace_project(db_session)
    backlog = states[0]
    done = next(state for state in states if state.group == "done")

    task = await create_task(
        db_session,
        project.id,
        TaskCreate(
            title="dod-complete",
            state_id=backlog.id,
            dod_checklist=[{"label": "Tests pass", "done": True}],
        ),
        actor,
    )

    _moved, _wip, permission_advisories = await move_task_state(
        db_session, task.id, done.id, 5000.0, actor
    )
    assert permission_advisories == []

    rows = await _advisory_rows(
        db_session,
        resource_type="task",
        resource_id=task.id,
        permission=PERMISSION_AGILE_DOD_BYPASS,
    )
    assert rows == []


async def test_dod_bypass_skipped_for_non_done_state(
    db_session, monkeypatch
):
    """Regression guard: moves to non-done states never trigger DoD advisory."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)

    project, states, actor = await _workspace_project(db_session)
    backlog, in_progress = states[0], states[2]

    task = await create_task(
        db_session,
        project.id,
        TaskCreate(
            title="dod-non-done",
            state_id=backlog.id,
            dod_checklist=[{"label": "Tests pass", "done": False}],
        ),
        actor,
    )

    _moved, _wip, permission_advisories = await move_task_state(
        db_session, task.id, in_progress.id, 5000.0, actor
    )
    assert permission_advisories == []
