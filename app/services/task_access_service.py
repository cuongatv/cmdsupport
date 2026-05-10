"""Task project access checks and assignee eligibility helpers."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Employee, ProjectMember, Role, Task, TaskProject
from app.services.permissions import EMPLOYEE_DEFAULT_PERMISSIONS


async def can_access_task_project(
    db: AsyncSession,
    employee: Employee,
    task_project: TaskProject,
) -> bool:
    """Return whether an employee is permitted for the task project's scope."""
    if _is_admin(employee):
        return True

    permissions = await _get_employee_permissions(db, employee)
    if "task:read:all" in permissions or "task_project:manage:all" in permissions:
        return True

    if task_project.department_id is not None:
        if "task:read:own_dept" not in permissions and "task_project:manage:own_dept" not in permissions:
            return False
        return employee.department_id == task_project.department_id

    if task_project.workspace_id is not None:
        return await _is_workspace_member(db, task_project.workspace_id, employee.id)

    return False


async def can_access_task(db: AsyncSession, employee: Employee, task: Task) -> bool:
    """Return whether an employee can read a task within its task-project scope."""
    if _is_admin(employee):
        return True

    permissions = await _get_employee_permissions(db, employee)
    if "task:read:all" in permissions:
        return True
    if "task:read:own_dept" not in permissions:
        return False

    task_project = task.task_project or await db.get(TaskProject, task.task_project_id)
    if task_project is None:
        return False

    return await can_access_task_project(db, employee, task_project)


async def list_eligible_assignees(db: AsyncSession, task_project: TaskProject) -> list[Employee]:
    """List active employees assignable to a task project without broadening read access."""
    stmt = select(Employee).where(Employee.is_active.is_(True)).order_by(Employee.name, Employee.email)

    if task_project.allow_any_employee:
        result = await db.execute(stmt)
        return list(result.scalars().all())

    if task_project.department_id is not None:
        stmt = stmt.where(Employee.department_id == task_project.department_id)
    elif task_project.workspace_id is not None:
        stmt = stmt.join(ProjectMember, ProjectMember.employee_id == Employee.id).where(
            ProjectMember.project_id == task_project.workspace_id
        )
    else:
        return []

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def validate_assignee(db: AsyncSession, task_project: TaskProject, employee: Employee) -> None:
    """Validate an employee may be newly assigned to the task project."""
    if not employee.is_active:
        raise ValueError("inactive employee cannot be assigned")

    if task_project.allow_any_employee:
        return

    if not await can_access_task_project(db, employee, task_project):
        raise ValueError("employee is out of scope for this task project")


def _is_admin(employee: Employee) -> bool:
    return employee.role == "admin"


async def _get_employee_permissions(db: AsyncSession, employee: Employee) -> set[str]:
    if employee.custom_role_id is None:
        return set(EMPLOYEE_DEFAULT_PERMISSIONS)

    role = await db.get(Role, employee.custom_role_id)
    if role is None:
        return set(EMPLOYEE_DEFAULT_PERMISSIONS)
    return set(role.permissions or [])


async def _is_workspace_member(db: AsyncSession, workspace_id: uuid.UUID, employee_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(ProjectMember.employee_id).where(
            ProjectMember.project_id == workspace_id,
            ProjectMember.employee_id == employee_id,
        )
    )
    return result.scalar_one_or_none() is not None
