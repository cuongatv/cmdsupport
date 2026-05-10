from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.database.models import Employee, ProjectMember, Role, TaskProject
from app.schemas.tasks import TaskCreate, TaskProjectCreate
from app.services.task_access_service import (
    can_access_task,
    can_access_task_project,
    list_eligible_assignees,
    validate_assignee,
)
from app.services.task_project_service import create_task_project
from app.services.task_service import create_task

pytestmark = pytest.mark.asyncio


async def _insert_department(db_session, name: str = "Task Access Department") -> uuid.UUID:
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": department_id, "name": f"{name} {department_id.hex[:8]}"},
    )
    return department_id


async def _insert_workspace(db_session, name: str = "Task Access Workspace") -> uuid.UUID:
    workspace_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
        {"id": workspace_id, "name": f"{name} {workspace_id.hex[:8]}"},
    )
    return workspace_id


async def _insert_role(db_session, permissions: list[str]) -> Role:
    role_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO roles (id, name, permissions, is_system)
            VALUES (:id, :name, CAST(:permissions AS JSONB), false)
            """
        ),
        {
            "id": role_id,
            "name": f"Task Access Role {role_id.hex[:8]}",
            "permissions": "[" + ",".join(f'\"{permission}\"' for permission in permissions) + "]",
        },
    )
    role = await db_session.get(Role, role_id)
    assert role is not None
    return role


async def _insert_employee(
    db_session,
    *,
    department_id: uuid.UUID | None = None,
    role: str = "employee",
    permissions: list[str] | None = None,
    name: str = "Task Access Tester",
    is_active: bool = True,
) -> Employee:
    if department_id is None:
        department_id = await _insert_department(db_session)
    custom_role = await _insert_role(db_session, permissions) if permissions is not None else None
    employee_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, role, department_id, custom_role_id, is_active)
            VALUES (:id, :name, :email, :role, :department_id, :custom_role_id, :is_active)
            """
        ),
        {
            "id": employee_id,
            "name": f"{name} {employee_id.hex[:6]}",
            "email": f"{employee_id.hex[:12]}@example.test",
            "role": role,
            "department_id": department_id,
            "custom_role_id": custom_role.id if custom_role else None,
            "is_active": is_active,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


async def _add_workspace_member(db_session, workspace_id: uuid.UUID, employee: Employee) -> None:
    db_session.add(ProjectMember(project_id=workspace_id, employee_id=employee.id, role="viewer"))
    await db_session.flush()


async def _workspace_project(
    db_session,
    *,
    actor: Employee,
    workspace_id: uuid.UUID | None = None,
    allow_any_employee: bool = False,
) -> TaskProject:
    if workspace_id is None:
        workspace_id = await _insert_workspace(db_session)
    return await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Workspace Access Project",
            identifier=f"WA{workspace_id.hex[:4].upper()}",
            workspace_id=workspace_id,
            allow_any_employee=allow_any_employee,
        ),
        actor,
    )


async def _department_project(
    db_session,
    *,
    department_id: uuid.UUID,
    actor: Employee,
    allow_any_employee: bool = False,
) -> TaskProject:
    return await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Department Access Project",
            identifier=f"DA{department_id.hex[:4].upper()}",
            department_id=department_id,
            allow_any_employee=allow_any_employee,
        ),
        actor,
    )


async def _create_task(db_session, project: TaskProject, actor: Employee):
    state = sorted(project.states, key=lambda item: item.position)[0]
    return await create_task(db_session, project.id, TaskCreate(title="Scoped Task", state_id=state.id), actor)


async def test_admin_bypass_can_access_any_task_project(db_session):
    owner = await _insert_employee(db_session)
    project = await _department_project(db_session, department_id=owner.department_id, actor=owner)
    admin = await _insert_employee(db_session, role="admin")

    assert await can_access_task_project(db_session, admin, project) is True


async def test_can_access_task_project_workspace_member(db_session):
    owner = await _insert_employee(db_session)
    workspace_id = await _insert_workspace(db_session)
    member = await _insert_employee(db_session)
    project = await _workspace_project(db_session, actor=owner, workspace_id=workspace_id)
    await _add_workspace_member(db_session, workspace_id, member)

    assert await can_access_task_project(db_session, member, project) is True


async def test_can_access_task_project_department_member(db_session):
    department_id = await _insert_department(db_session)
    owner = await _insert_employee(db_session, department_id=department_id)
    member = await _insert_employee(db_session, department_id=department_id)
    project = await _department_project(db_session, department_id=department_id, actor=owner)

    assert await can_access_task_project(db_session, member, project) is True


async def test_cross_department_user_denied_without_task_read_all(db_session):
    owner = await _insert_employee(db_session)
    other = await _insert_employee(db_session, permissions=["task:read:own_dept"])
    project = await _department_project(db_session, department_id=owner.department_id, actor=owner)
    task = await _create_task(db_session, project, owner)

    assert await can_access_task(db_session, other, task) is False


async def test_task_read_all_grants_cross_scope_task_project_access(db_session):
    owner = await _insert_employee(db_session)
    reader = await _insert_employee(db_session, permissions=["task:read:all"])
    project = await _department_project(db_session, department_id=owner.department_id, actor=owner)

    assert await can_access_task_project(db_session, reader, project) is True


async def test_task_project_manage_all_grants_cross_scope_task_project_access(db_session):
    owner = await _insert_employee(db_session)
    manager = await _insert_employee(db_session, permissions=["task_project:manage:all"])
    project = await _department_project(db_session, department_id=owner.department_id, actor=owner)

    assert await can_access_task_project(db_session, manager, project) is True


async def test_task_read_all_grants_access_anywhere(db_session):
    owner = await _insert_employee(db_session)
    reader = await _insert_employee(db_session, permissions=["task:read:all"])
    project = await _department_project(db_session, department_id=owner.department_id, actor=owner)
    task = await _create_task(db_session, project, owner)

    assert await can_access_task(db_session, reader, task) is True


async def test_scoped_assignee_picker_excludes_out_of_scope(db_session):
    owner = await _insert_employee(db_session)
    in_scope = await _insert_employee(db_session, department_id=owner.department_id)
    out_of_scope = await _insert_employee(db_session)
    project = await _department_project(db_session, department_id=owner.department_id, actor=owner)

    eligible = await list_eligible_assignees(db_session, project)

    eligible_ids = {employee.id for employee in eligible}
    assert in_scope.id in eligible_ids
    assert out_of_scope.id not in eligible_ids


async def test_allow_any_employee_widens_assignee_picker(db_session):
    owner = await _insert_employee(db_session)
    out_of_scope = await _insert_employee(db_session)
    project = await _department_project(
        db_session,
        department_id=owner.department_id,
        actor=owner,
        allow_any_employee=True,
    )

    eligible = await list_eligible_assignees(db_session, project)

    assert out_of_scope.id in {employee.id for employee in eligible}


async def test_allow_any_employee_assignment_does_not_widen_read_access(db_session):
    owner = await _insert_employee(db_session)
    out_of_scope = await _insert_employee(db_session, permissions=["task:read:own_dept"])
    project = await _department_project(
        db_session,
        department_id=owner.department_id,
        actor=owner,
        allow_any_employee=True,
    )
    task = await _create_task(db_session, project, owner)

    await validate_assignee(db_session, project, out_of_scope)

    assert await can_access_task(db_session, out_of_scope, task) is False


async def test_inactive_employee_cannot_be_newly_assigned(db_session):
    owner = await _insert_employee(db_session)
    inactive = await _insert_employee(db_session, department_id=owner.department_id, is_active=False)
    project = await _department_project(db_session, department_id=owner.department_id, actor=owner)

    with pytest.raises(ValueError, match="inactive employee"):
        await validate_assignee(db_session, project, inactive)
