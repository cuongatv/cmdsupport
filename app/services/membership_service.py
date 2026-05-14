"""Department membership service layer."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    MembershipRole,
    UnitType,
)


class MembershipRoleNotAllowedError(ValueError):
    """Raised when role is not valid for the department's unit_type."""


class LastActiveMembershipError(ValueError):
    """Raised when trying to deactivate the last active membership."""


class DepartmentArchiveBlockedError(ValueError):
    """Raised when trying to archive a department that has open TaskProjects."""

    def __init__(self, open_project_count: int):
        super().__init__(f"Cannot archive: {open_project_count} open task project(s)")
        self.open_project_count: int = open_project_count


class DepartmentDeleteBlockedError(ValueError):
    """Raised when trying to hard-delete a department that still has dependencies."""

    def __init__(self, reasons: list[str]):
        super().__init__("Cannot delete: " + "; ".join(reasons))
        self.reasons: list[str] = reasons


class PrimaryMembershipRequiredError(ValueError):
    """Raised when trying to delete/deactivate the only primary membership."""


async def list_memberships(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    include_inactive: bool = False,
) -> list[EmployeeDepartmentMembership]:
    stmt = select(EmployeeDepartmentMembership)
    if employee_id:
        stmt = stmt.where(EmployeeDepartmentMembership.employee_id == employee_id)
    if department_id:
        stmt = stmt.where(EmployeeDepartmentMembership.department_id == department_id)
    if not include_inactive:
        stmt = stmt.where(EmployeeDepartmentMembership.is_active.is_(True))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_membership(
    session: AsyncSession, membership_id: uuid.UUID
) -> EmployeeDepartmentMembership:
    membership = await session.get(EmployeeDepartmentMembership, membership_id)
    if not membership:
        raise ValueError(f"Membership {membership_id} not found")
    return membership


async def get_user_department_ids(
    session: AsyncSession, employee_id: uuid.UUID
) -> set[uuid.UUID]:
    """Return set of department_ids where employee has active membership."""
    stmt = select(EmployeeDepartmentMembership.department_id).where(
        EmployeeDepartmentMembership.employee_id == employee_id,
        EmployeeDepartmentMembership.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return set(result.scalars().all())


def _validate_role_for_unit_type(role: MembershipRole, unit_type: UnitType) -> None:
    squad_only = {
        MembershipRole.PRODUCT_OWNER,
        MembershipRole.SCRUM_MASTER,
        MembershipRole.DEVELOPER,
    }
    if role in squad_only and unit_type != UnitType.SQUAD_TEAM:
        raise MembershipRoleNotAllowedError(
            f"role '{role.value}' not allowed for unit_type '{unit_type.value}'"
        )


async def create_membership(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID,
    department_id: uuid.UUID,
    role: MembershipRole,
    capacity_percent: int | None = None,
    set_primary: bool = False,
) -> EmployeeDepartmentMembership:
    dept = await session.get(Department, department_id)
    if not dept:
        raise ValueError(f"Department {department_id} not found")
    _validate_role_for_unit_type(role, dept.unit_type)

    existing = await session.execute(
        select(EmployeeDepartmentMembership).where(
            EmployeeDepartmentMembership.employee_id == employee_id,
            EmployeeDepartmentMembership.department_id == department_id,
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError(
            f"Employee already has a membership in department {department_id}"
        )

    if set_primary:
        await _unset_primary(session, employee_id)

    membership = EmployeeDepartmentMembership(
        employee_id=employee_id,
        department_id=department_id,
        role=role,
        capacity_percent=capacity_percent,
        is_primary=set_primary,
        is_active=True,
    )
    session.add(membership)

    if set_primary:
        employee = await session.get(Employee, employee_id)
        if employee:
            employee.department_id = department_id

    await session.flush()
    return membership


async def _unset_primary(session: AsyncSession, employee_id: uuid.UUID) -> None:
    """Set is_primary=False for all memberships of this employee."""
    stmt = (
        update(EmployeeDepartmentMembership)
        .where(
            EmployeeDepartmentMembership.employee_id == employee_id,
            EmployeeDepartmentMembership.is_primary.is_(True),
        )
        .values(is_primary=False)
    )
    await session.execute(stmt)


async def update_membership(
    session: AsyncSession,
    membership_id: uuid.UUID,
    *,
    role: MembershipRole | None = None,
    capacity_percent: int | None = None,
    is_active: bool | None = None,
) -> EmployeeDepartmentMembership:
    membership = await get_membership(session, membership_id)

    if role is not None:
        dept = await session.get(Department, membership.department_id)
        if not dept:
            raise ValueError(f"Department {membership.department_id} not found")
        _validate_role_for_unit_type(role, dept.unit_type)
        membership.role = role

    if capacity_percent is not None:
        membership.capacity_percent = capacity_percent

    if is_active is not None and is_active is False:
        active_count = await session.execute(
            select(func.count()).where(
                EmployeeDepartmentMembership.employee_id == membership.employee_id,
                EmployeeDepartmentMembership.is_active.is_(True),
                EmployeeDepartmentMembership.id != membership_id,
            )
        )
        if active_count.scalar() == 0 and membership.is_primary:
            raise LastActiveMembershipError(
                "Cannot deactivate the only active primary membership"
            )
        membership.is_active = False
        if membership.is_primary:
            membership.is_primary = False
    elif is_active is True:
        membership.is_active = True

    await session.flush()
    return membership


async def set_primary(
    session: AsyncSession, membership_id: uuid.UUID
) -> EmployeeDepartmentMembership:
    membership = await get_membership(session, membership_id)
    if not membership.is_active:
        raise ValueError("Cannot set inactive membership as primary")

    await _unset_primary(session, membership.employee_id)
    membership.is_primary = True

    employee = await session.get(Employee, membership.employee_id)
    if employee:
        employee.department_id = membership.department_id

    await session.flush()
    return membership


async def archive_department(
    session: AsyncSession, department_id: uuid.UUID
) -> dict[str, bool | str]:
    from app.database.models import TaskProject

    open_count_result = await session.execute(
        select(func.count())
        .select_from(TaskProject)
        .where(
            TaskProject.department_id == department_id,
            TaskProject.is_archived.is_(False),
        )
    )
    open_count = open_count_result.scalar() or 0
    if open_count > 0:
        raise DepartmentArchiveBlockedError(open_count)

    dept = await session.get(Department, department_id)
    if not dept:
        raise ValueError(f"Department {department_id} not found")

    dept.is_archived = True
    dept.archived_at = datetime.now(timezone.utc)

    await session.execute(
        update(EmployeeDepartmentMembership)
        .where(EmployeeDepartmentMembership.department_id == department_id)
        .values(is_active=False, is_primary=False)
    )

    await session.flush()
    return {"archived": True, "department_id": str(department_id)}


async def unarchive_department(
    session: AsyncSession, department_id: uuid.UUID
) -> dict[str, bool | str]:
    dept = await session.get(Department, department_id)
    if not dept:
        raise ValueError(f"Department {department_id} not found")
    dept.is_archived = False
    dept.archived_at = None
    await session.flush()
    return {"archived": False, "department_id": str(department_id)}


async def delete_department(session: AsyncSession, department_id: uuid.UUID) -> None:
    from app.database.models import TaskProject

    dept = await session.get(Department, department_id)
    if not dept:
        raise ValueError(f"Department {department_id} not found")

    reasons: list[str] = []
    if not dept.is_archived:
        reasons.append("department must be archived first")

    membership_count_result = await session.execute(
        select(func.count()).where(
            EmployeeDepartmentMembership.department_id == department_id
        )
    )
    membership_count = membership_count_result.scalar() or 0
    if membership_count > 0:
        reasons.append(f"{membership_count} membership row(s) still exist")

    task_project_count_result = await session.execute(
        select(func.count())
        .select_from(TaskProject)
        .where(TaskProject.department_id == department_id)
    )
    task_project_count = task_project_count_result.scalar() or 0
    if task_project_count > 0:
        reasons.append(f"{task_project_count} task project(s) still exist")

    if reasons:
        raise DepartmentDeleteBlockedError(reasons)

    await session.delete(dept)
    await session.flush()


async def delete_membership(session: AsyncSession, membership_id: uuid.UUID) -> None:
    membership = await get_membership(session, membership_id)
    if membership.is_primary:
        other_count_result = await session.execute(
            select(func.count()).where(
                EmployeeDepartmentMembership.employee_id == membership.employee_id,
                EmployeeDepartmentMembership.id != membership_id,
            )
        )
        other_count = other_count_result.scalar() or 0
        if other_count == 0:
            raise PrimaryMembershipRequiredError("Cannot delete the only membership")
    await session.delete(membership)
    await session.flush()
