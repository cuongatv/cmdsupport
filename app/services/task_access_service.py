"""Task project access checks and assignee eligibility helpers."""

from __future__ import annotations

import uuid

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Employee,
    EmployeeDepartmentMembership,
    ProjectMember,
    Role,
    Task,
    TaskProject,
)
from app.services.permission_engine import get_user_department_ids
from app.services.permissions import EMPLOYEE_DEFAULT_PERMISSIONS


async def can_access_task_project(
    db: AsyncSession,
    employee: Employee,
    task_project: TaskProject,
) -> bool:
    """Return whether an employee is permitted for the task project's scope."""
    if _is_admin(employee):
        return True

    if task_project.owner_employee_id is not None:
        # Personal task projects are owner-only. Keep this check before broad
        # permission shortcuts so task:read:all / manage:all cannot leak another
        # employee's personal workspace; admins remain the explicit global
        # escape hatch via the branch above.
        return task_project.owner_employee_id == employee.id

    permissions = await _get_employee_permissions(db, employee)
    if "task:read:all" in permissions or "task_project:manage:all" in permissions:
        return True

    if task_project.department_id is not None:
        if (
            "task:read:own_dept" not in permissions
            and "task_project:manage:own_dept" not in permissions
        ):
            return False
        user_dept_ids = await get_user_department_ids(db, employee)
        return task_project.department_id in user_dept_ids

    if task_project.workspace_id is not None:
        return await _is_workspace_member(db, task_project.workspace_id, employee.id)

    return False


async def can_access_task(db: AsyncSession, employee: Employee, task: Task) -> bool:
    """Return whether an employee can read a task within its task-project scope."""
    if _is_admin(employee):
        return True

    task_project = task.task_project or await db.get(TaskProject, task.task_project_id)
    if task_project is None:
        return False

    if task_project.owner_employee_id is not None:
        # Personal task rows inherit the owner-only rule from their project.
        # Check before broad read shortcuts so task:read:all cannot pierce
        # personal scope.
        return task_project.owner_employee_id == employee.id

    permissions = await _get_employee_permissions(db, employee)
    if "task:read:all" in permissions:
        return True
    if "task:read:own_dept" not in permissions:
        return False

    return await can_access_task_project(db, employee, task_project)


async def list_eligible_assignees(
    db: AsyncSession, task_project: TaskProject
) -> list[Employee]:
    """List active employees assignable to a task project without broadening read access."""
    stmt = (
        select(Employee)
        .where(Employee.is_active.is_(True))
        .order_by(Employee.name, Employee.email)
    )

    if task_project.allow_any_employee:
        result = await db.execute(stmt)
        return list(result.scalars().all())

    if task_project.department_id is not None:
        # Membership union: an employee is eligible if they have an active
        # EmployeeDepartmentMembership row for the project's department OR
        # carry the legacy employees.department_id pointer at that department
        # (covers rows created before the membership backfill).
        stmt = stmt.where(
            or_(
                Employee.department_id == task_project.department_id,
                exists().where(
                    EmployeeDepartmentMembership.employee_id == Employee.id,
                    EmployeeDepartmentMembership.department_id
                    == task_project.department_id,
                    EmployeeDepartmentMembership.is_active.is_(True),
                ),
            )
        )
    elif task_project.workspace_id is not None:
        stmt = stmt.join(ProjectMember, ProjectMember.employee_id == Employee.id).where(
            ProjectMember.project_id == task_project.workspace_id
        )
    elif task_project.owner_employee_id is not None:
        # Personal task projects: only the owner can be assigned.
        stmt = stmt.where(Employee.id == task_project.owner_employee_id)
    else:
        return []

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def is_eligible_assignee(
    db: AsyncSession,
    employee: Employee,
    task_project: TaskProject,
) -> bool:
    """Return whether an employee may be assigned to the task project.

    Membership-based; independent of the employee's read permissions. For a
    department-scoped project, the employee must hold an active
    EmployeeDepartmentMembership in the project's department (legacy
    department_id is honoured via get_user_department_ids' fallback).
    Workspace-scoped and global projects retain existing CRUD semantics —
    any active employee is eligible at create-time; the assignment endpoint
    still enforces workspace membership via validate_assignee().
    allow_any_employee bypasses scope checks.
    """
    if not employee.is_active:
        return False

    if task_project.allow_any_employee:
        return True

    if task_project.department_id is not None:
        user_dept_ids = await get_user_department_ids(db, employee)
        return task_project.department_id in user_dept_ids

    return True


async def validate_assignee(
    db: AsyncSession, task_project: TaskProject, employee: Employee
) -> None:
    """Validate an employee may be newly assigned to the task project."""
    if not employee.is_active:
        raise ValueError("inactive employee cannot be assigned")

    if task_project.allow_any_employee:
        return

    # Workspace-scoped projects keep the legacy workspace-membership gate so the
    # /api/tasks/{id}/assignees endpoint does not regress on workspace isolation.
    if task_project.workspace_id is not None:
        if not await _is_workspace_member(db, task_project.workspace_id, employee.id):
            raise ValueError("employee is out of scope for this task project")
        return

    if not await is_eligible_assignee(db, employee, task_project):
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


async def _is_workspace_member(
    db: AsyncSession, workspace_id: uuid.UUID, employee_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(ProjectMember.employee_id).where(
            ProjectMember.project_id == workspace_id,
            ProjectMember.employee_id == employee_id,
        )
    )
    return result.scalar_one_or_none() is not None
