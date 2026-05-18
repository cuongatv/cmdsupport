"""Service-layer tests for Phase 2 Agile semantics (DoR/DoD snapshot, story points)."""

from __future__ import annotations

import copy
import uuid

import pytest
from sqlalchemy import text

from app.database.models import Employee, TaskProjectTemplate
from app.schemas.tasks import TaskCreate, TaskProjectCreate
from app.services.task_project_service import (
    create_task_project,
    get_project_template,
)
from app.services.task_service import create_task

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
            "name": f"Phase2 Dept {department_id.hex[:8]}",
        },
    )
    return department_id


async def _insert_workspace(db_session) -> uuid.UUID:
    workspace_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
        {
            "id": workspace_id,
            "name": f"Phase2 Workspace {workspace_id.hex[:8]}",
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
            "name": f"Phase2 Tester {employee_id.hex[:6]}",
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
            name="Phase 2 Project",
            identifier=f"P2{workspace_id.hex[:4].upper()}",
            workspace_id=workspace_id,
        ),
        creator,
    )
    states = sorted(project.states, key=lambda state: state.position)
    return project, states, creator


async def _attach_template(db_session, project_id, *, dor, dod) -> TaskProjectTemplate:
    template = TaskProjectTemplate(
        task_project_id=project_id,
        dor_template=copy.deepcopy(dor),
        dod_template=copy.deepcopy(dod),
    )
    db_session.add(template)
    await db_session.flush()
    await db_session.refresh(template)
    return template


# ---------------------------------------------------------------------------
# Required scenarios
# ---------------------------------------------------------------------------


async def test_task_create_snapshots_dor_dod_template(db_session):
    project, states, actor = await _workspace_project(db_session)
    backlog = states[0]

    dor = [{"label": "API contract agreed", "done": False}]
    dod = [
        {"label": "Tests pass", "done": False},
        {"label": "Docs updated", "done": False},
    ]
    await _attach_template(db_session, project.id, dor=dor, dod=dod)

    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="Snapshotted", state_id=backlog.id),
        actor,
    )

    # Snapshot present and equal to the template content at create time.
    assert task.dor_checklist == dor
    assert task.dod_checklist == dod


async def test_template_update_does_not_affect_existing_task(db_session):
    project, states, actor = await _workspace_project(db_session)
    backlog = states[0]

    original_dor = [{"label": "Spec reviewed", "done": False}]
    original_dod = [{"label": "QA pass", "done": False}]
    template = await _attach_template(
        db_session, project.id, dor=original_dor, dod=original_dod
    )

    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="Snapshot Source", state_id=backlog.id),
        actor,
    )
    snapshot_dor_before = copy.deepcopy(task.dor_checklist)
    snapshot_dod_before = copy.deepcopy(task.dod_checklist)
    assert snapshot_dor_before == original_dor
    assert snapshot_dod_before == original_dod

    # Mutate the template AFTER the snapshot.
    template.dor_template = [{"label": "MUTATED dor", "done": False}]
    template.dod_template = [{"label": "MUTATED dod", "done": False}]
    db_session.add(template)
    await db_session.flush()

    # Refresh the task and confirm the snapshot did NOT change.
    await db_session.refresh(task)
    assert task.dor_checklist == snapshot_dor_before
    assert task.dod_checklist == snapshot_dod_before

    # Sanity: the live template now reflects the mutation via the service helper.
    refreshed_template = await get_project_template(db_session, project.id)
    assert refreshed_template is not None
    assert refreshed_template.dor_template == [{"label": "MUTATED dor", "done": False}]


async def test_negative_story_points_rejected(db_session):
    project, states, actor = await _workspace_project(db_session)
    backlog = states[0]

    # Pydantic schema (Field(ge=0)) rejects negative story_points at the
    # boundary before the service or DB is reached.
    with pytest.raises(ValueError):
        TaskCreate(
            title="Negative", state_id=backlog.id, story_points=-1
        )

    # Belt-and-braces: even if the schema is bypassed, the DB CHECK constraint
    # rejects the row. Use raw SQL so we sidestep schema validation entirely.
    with pytest.raises(Exception):
        await db_session.execute(
            text(
                """
                INSERT INTO tasks
                (id, task_project_id, state_id, title, story_points, version, position)
                VALUES (:id, :pid, :sid, :title, :sp, 1, 1000.0)
                """
            ),
            {
                "id": uuid.uuid4(),
                "pid": project.id,
                "sid": backlog.id,
                "title": "Negative SP",
                "sp": -5,
            },
        )
        await db_session.flush()


# ---------------------------------------------------------------------------
# Regression guards
# ---------------------------------------------------------------------------


async def test_task_create_without_template_leaves_checklists_null(db_session):
    """No template attached → snapshot fields stay NULL."""
    project, states, actor = await _workspace_project(db_session)
    backlog = states[0]

    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="No template", state_id=backlog.id),
        actor,
    )
    assert task.dor_checklist is None
    assert task.dod_checklist is None


async def test_explicit_checklist_overrides_template_snapshot(db_session):
    """Client-provided checklist wins over the template snapshot."""
    project, states, actor = await _workspace_project(db_session)
    backlog = states[0]

    await _attach_template(
        db_session,
        project.id,
        dor=[{"label": "from template", "done": False}],
        dod=[{"label": "from template", "done": False}],
    )

    override_dor = [{"label": "client supplied", "done": False}]
    task = await create_task(
        db_session,
        project.id,
        TaskCreate(
            title="Override",
            state_id=backlog.id,
            dor_checklist=override_dor,
            # dod_checklist omitted → falls back to template snapshot.
        ),
        actor,
    )
    assert task.dor_checklist == override_dor
    assert task.dod_checklist == [{"label": "from template", "done": False}]
