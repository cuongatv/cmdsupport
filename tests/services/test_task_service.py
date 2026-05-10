from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.database.models import Employee, Task, TaskActivity
from app.schemas.tasks import TaskCreate, TaskProjectCreate, TaskUpdate
from app.services.task_constants import POSITION_GAP
from app.services.task_project_service import create_task_project
from app.services.task_service import create_task, list_tasks, soft_delete_task, update_task

pytestmark = pytest.mark.asyncio


async def _insert_department(db_session, name: str = "Task CRUD Department") -> uuid.UUID:
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": department_id, "name": f"{name} {department_id.hex[:8]}"},
    )
    return department_id


async def _insert_workspace(db_session, name: str = "Task CRUD Workspace") -> uuid.UUID:
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
    name: str = "Task CRUD Tester",
) -> Employee:
    if department_id is None:
        department_id = await _insert_department(db_session)
    employee_id = uuid.uuid4()
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
            "email": f"{employee_id.hex[:12]}@example.test",
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
    project = await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Task CRUD Project",
            identifier=f"TC{workspace_id.hex[:4].upper()}",
            workspace_id=workspace_id,
        ),
        creator,
    )
    states = sorted(project.states, key=lambda state: state.position)
    return project, states, creator


async def _create_task(
    db_session,
    project_id,
    state_id,
    actor,
    *,
    title="Task",
    parent_task_id=None,
    assignee_ids=None,
):
    return await create_task(
        db_session,
        project_id,
        TaskCreate(
            title=title,
            state_id=state_id,
            parent_task_id=parent_task_id,
            assignee_ids=assignee_ids or [],
        ),
        actor,
    )


async def _activities_for(db_session, task_id: uuid.UUID) -> list[TaskActivity]:
    result = await db_session.execute(
        select(TaskActivity).where(TaskActivity.task_id == task_id).order_by(TaskActivity.created_at, TaskActivity.id)
    )
    return list(result.scalars().all())


async def test_create_task_returns_version_one(db_session):
    project, states, actor = await _workspace_project(db_session)

    task = await _create_task(db_session, project.id, states[0].id, actor)

    assert task.version == 1
    assert task.position == POSITION_GAP
    assert task.created_by_id == actor.id


async def test_create_task_creates_activity_rows_for_create_and_assignees(db_session):
    project, states, actor = await _workspace_project(db_session)
    first_assignee = await _insert_employee(db_session)
    second_assignee = await _insert_employee(db_session)

    task = await _create_task(
        db_session,
        project.id,
        states[0].id,
        actor,
        assignee_ids=[first_assignee.id, second_assignee.id],
    )

    activities = await _activities_for(db_session, task.id)
    created = [activity for activity in activities if activity.verb == "created"]
    assigned = [activity for activity in activities if activity.verb == "assigned"]
    assert len(created) == 1
    assert created[0].actor_id == actor.id
    assert {activity.new_value for activity in assigned} == {str(first_assignee.id), str(second_assignee.id)}
    assert all(activity.field_name == "assignee_id" for activity in assigned)


async def test_soft_delete_task_creates_deleted_activity_row(db_session):
    project, states, actor = await _workspace_project(db_session)
    task = await _create_task(db_session, project.id, states[0].id, actor)

    await soft_delete_task(db_session, task.id, actor)

    activities = await _activities_for(db_session, task.id)
    deleted = [activity for activity in activities if activity.verb == "deleted"]
    assert len(deleted) == 1
    assert deleted[0].actor_id == actor.id


async def test_create_task_subtask_depth_limit(db_session):
    project, states, actor = await _workspace_project(db_session)
    parent = await _create_task(db_session, project.id, states[0].id, actor, title="Parent")
    subtask = await _create_task(
        db_session,
        project.id,
        states[0].id,
        actor,
        title="Subtask",
        parent_task_id=parent.id,
    )

    with pytest.raises(ValueError, match="max subtask depth"):
        await _create_task(
            db_session,
            project.id,
            states[0].id,
            actor,
            title="Sub-subtask",
            parent_task_id=subtask.id,
        )


async def test_optimistic_concurrency_update_succeeds(db_session):
    project, states, actor = await _workspace_project(db_session)
    task = await _create_task(db_session, project.id, states[0].id, actor, title="Before")

    updated = await update_task(
        db_session,
        task.id,
        TaskUpdate(title="After", version=task.version),
        actor,
    )

    assert updated.title == "After"
    assert updated.version == 2


async def test_optimistic_concurrency_stale_version_raises(db_session):
    project, states, actor = await _workspace_project(db_session)
    task = await _create_task(db_session, project.id, states[0].id, actor, title="Before")
    await update_task(db_session, task.id, TaskUpdate(title="After", version=1), actor)

    with pytest.raises(ValueError, match="version conflict"):
        await update_task(db_session, task.id, TaskUpdate(title="Stale", version=1), actor)


async def test_soft_delete_hides_from_default_list(db_session):
    project, states, actor = await _workspace_project(db_session)
    task = await _create_task(db_session, project.id, states[0].id, actor)

    await soft_delete_task(db_session, task.id, actor)
    tasks = await list_tasks(db_session, project.id)

    assert task.id not in {listed.id for listed in tasks}


async def test_soft_delete_cascades_to_subtasks(db_session):
    project, states, actor = await _workspace_project(db_session)
    parent = await _create_task(db_session, project.id, states[0].id, actor, title="Parent")
    subtask = await _create_task(
        db_session,
        project.id,
        states[0].id,
        actor,
        title="Subtask",
        parent_task_id=parent.id,
    )

    await soft_delete_task(db_session, parent.id, actor)
    refreshed_subtask = await db_session.get(Task, subtask.id)

    assert refreshed_subtask is not None
    assert refreshed_subtask.deleted_at is not None


async def test_create_task_state_not_in_project_raises(db_session):
    project, _states, actor = await _workspace_project(db_session)
    _other_project, other_states, _other_actor = await _workspace_project(db_session)

    with pytest.raises(ValueError, match="state not in project"):
        await create_task(
            db_session,
            project.id,
            TaskCreate(title="Wrong state", state_id=other_states[0].id),
            actor,
        )


async def test_list_tasks_orders_by_position(db_session):
    project, states, actor = await _workspace_project(db_session)
    second = await _create_task(db_session, project.id, states[0].id, actor, title="Second")
    first = await _create_task(db_session, project.id, states[0].id, actor, title="First")
    second.position = 2000.0
    first.position = 100.0
    await db_session.flush()

    tasks = await list_tasks(db_session, project.id, state_id=states[0].id)

    assert [task.id for task in tasks[:2]] == [first.id, second.id]
