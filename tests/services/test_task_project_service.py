from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import text

from app.database.models import Employee, TaskProject, TaskState
from app.schemas.tasks import TaskLabelCreate, TaskProjectCreate
from app.services.task_constants import (
    DEFAULT_STATE_GROUPS,
    DEFAULT_STATE_NAMES,
    POSITION_GAP,
)
from app.services.task_project_service import (
    archive_task_project,
    create_label,
    create_task_project,
    delete_state,
    restore_task_project,
)

pytestmark = pytest.mark.asyncio


async def _insert_department(db_session, name: str = "Task Service Department") -> uuid.UUID:
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": department_id, "name": f"{name} {department_id.hex[:8]}"},
    )
    return department_id


async def _insert_workspace(db_session, name: str = "Task Service Workspace") -> uuid.UUID:
    workspace_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
        {"id": workspace_id, "name": f"{name} {workspace_id.hex[:8]}"},
    )
    return workspace_id


async def _insert_employee(
    db_session,
    *,
    department_id: uuid.UUID | None = None,
    role: str = "employee",
    name: str = "Task Tester",
) -> Employee:
    if department_id is None:
        department_id = await _insert_department(db_session)
    employee_id = uuid.uuid4()
    email = f"{employee_id.hex[:12]}@example.test"
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, role, department_id, is_active)
            VALUES (:id, :name, :email, :role, :department_id, true)
            """
        ),
        {
            "id": employee_id,
            "name": f"{name} {employee_id.hex[:6]}",
            "email": email,
            "role": role,
            "department_id": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


async def _workspace_project(db_session, *, actor: Employee | None = None):
    workspace_id = await _insert_workspace(db_session)
    creator = actor or await _insert_employee(db_session)
    return await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Workspace Task Project",
            identifier="WTP",
            workspace_id=workspace_id,
        ),
        creator,
    )


async def test_create_workspace_project_defaults(db_session):
    workspace_id = await _insert_workspace(db_session)
    creator = await _insert_employee(db_session)

    project = await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Workspace Project Defaults",
            identifier="WPD",
            workspace_id=workspace_id,
        ),
        creator,
    )

    states = sorted(project.states, key=lambda state: state.position)
    assert len(states) == 6
    assert [state.name for state in states] == DEFAULT_STATE_NAMES
    assert [state.group for state in states] == DEFAULT_STATE_GROUPS
    assert [state.position for state in states] == [i * POSITION_GAP for i in range(6)]
    assert states[0].is_default is True
    assert all(state.is_default is False for state in states[1:])


async def test_create_department_project_defaults(db_session):
    department_id = await _insert_department(db_session)
    creator = await _insert_employee(db_session, department_id=department_id)

    project = await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Department Project Defaults",
            identifier="DPD",
            department_id=department_id,
        ),
        creator,
    )

    states = sorted(project.states, key=lambda state: state.position)
    assert len(states) == 6
    assert [state.name for state in states] == DEFAULT_STATE_NAMES
    assert [state.group for state in states] == DEFAULT_STATE_GROUPS
    assert states[0].is_default is True


async def test_create_project_both_parents_raises(db_session):
    workspace_id = await _insert_workspace(db_session)
    department_id = await _insert_department(db_session)
    creator = await _insert_employee(db_session)

    with pytest.raises(ValueError, match="exactly one of workspace_id or department_id must be set"):
        await create_task_project(
            db_session,
            TaskProjectCreate(
                name="Invalid Both Parents",
                identifier="IBP",
                workspace_id=workspace_id,
                department_id=department_id,
            ),
            creator,
        )


async def test_create_project_no_parent_raises(db_session):
    creator = await _insert_employee(db_session)

    with pytest.raises(ValueError, match="exactly one of workspace_id or department_id must be set"):
        await create_task_project(
            db_session,
            TaskProjectCreate(name="Invalid No Parent", identifier="INP"),
            creator,
        )


async def test_archived_project_rejects_label_mutation(db_session):
    actor = await _insert_employee(db_session, role="employee")
    project = await _workspace_project(db_session, actor=actor)
    await archive_task_project(db_session, project.id, actor)

    with pytest.raises(PermissionError, match="archived project is read-only"):
        await create_label(
            db_session,
            project.id,
            TaskLabelCreate(name="Blocked", color="#888888"),
            actor,
        )


async def test_admin_can_mutate_archived_project(db_session):
    creator = await _insert_employee(db_session, role="employee")
    admin = await _insert_employee(db_session, role="admin")
    project = await _workspace_project(db_session, actor=creator)
    await archive_task_project(db_session, project.id, creator)

    label = await create_label(
        db_session,
        project.id,
        TaskLabelCreate(name="Admin Label", color="#00AA00"),
        admin,
    )

    assert label.id is not None
    assert label.task_project_id == project.id
    assert label.name == "Admin Label"


async def test_label_name_unique_per_project(db_session):
    actor = await _insert_employee(db_session, role="employee")
    project = await _workspace_project(db_session, actor=actor)

    await create_label(db_session, project.id, TaskLabelCreate(name="Bug"), actor)

    with pytest.raises(ValueError, match="label name already exists"):
        await create_label(db_session, project.id, TaskLabelCreate(name="Bug"), actor)


async def test_state_delete_requires_reassign_when_tasks_exist():
    project_id = uuid.uuid4()
    state_id = uuid.uuid4()
    actor = Employee(id=uuid.uuid4(), name="Actor", email="actor@example.test", role="employee")

    project = TaskProject(
        id=project_id,
        name="Project",
        identifier="PROJ",
        workspace_id=uuid.uuid4(),
        is_archived=False,
    )
    state = TaskState(
        id=state_id,
        task_project_id=project_id,
        name="Todo",
        group="todo",
        position=0.0,
    )
    state.task_project = project

    result = Mock()
    result.scalar_one_or_none.return_value = state
    db = AsyncMock()
    db.execute.return_value = result
    db.scalar.return_value = 1

    with pytest.raises(ValueError, match="state has tasks — provide reassign_state_id"):
        await delete_state(db, state_id, None, actor)

    db.scalar.assert_called_once()
    assert db.delete.await_count == 0


async def test_restore_project_non_admin_raises(db_session):
    actor = await _insert_employee(db_session, role="employee")
    project = await _workspace_project(db_session, actor=actor)
    await archive_task_project(db_session, project.id, actor)

    with pytest.raises(PermissionError, match="admin only"):
        await restore_task_project(db_session, project.id, actor)
