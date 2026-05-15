"""
Departments router — membership-aware department endpoints.

This router complements the legacy department CRUD in ``rbac.py`` with the
multi-unit-membership endpoints introduced by the unit-agile upgrade:

  * ``POST   /api/departments/{id}/archive``    — soft archive
  * ``POST   /api/departments/{id}/unarchive``  — flip the flag back
  * ``GET    /api/departments/{id}/members``    — active memberships
  * ``POST   /api/departments/{id}/members``    — add an employee with role
  * ``GET    /api/departments/{id}/sources``    — sources attached to dept
  * ``POST   /api/departments/{id}/sources/{source_id}``   — attach source
  * ``DELETE /api/departments/{id}/sources/{source_id}``   — detach source
  * ``GET    /api/employees/{id}/memberships``  — list one employee's memberships
  * ``PATCH  /api/departments/{id}``            — partial update; rejects
                                                  ``unit_type`` change with 400
  * ``PATCH  /api/memberships/{id}``            — update role / capacity / active
  * ``PATCH  /api/memberships/{id}/primary``    — set as the employee's primary
  * ``DELETE /api/memberships/{id}``            — remove a membership

Service errors translate to HTTP:
  * ``MembershipRoleNotAllowedError``  → 400
  * ``DepartmentArchiveBlockedError``  → 409
  * ``DepartmentDeleteBlockedError``   → 409 (used by the rbac DELETE handler)
  * ``LastActiveMembershipError``      → 409
  * ``PrimaryMembershipRequiredError`` → 409
  * Generic ``ValueError`` (not found / duplicate) → 404 (not found) else 409
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    MembershipRole,
    Skill,
    SkillDepartment,
    Source,
    SourceDepartment,
)
from app.schemas.departments import (
    DepartmentResponse,
    DepartmentSkillResponse,
    DepartmentUpdate,
    MembershipCreate,
    MembershipResponse,
    MembershipUpdate,
)
from app.services import membership_service
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission
from app.services.membership_service import (
    DepartmentArchiveBlockedError,
    LastActiveMembershipError,
    MembershipRoleNotAllowedError,
    PrimaryMembershipRequiredError,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _membership_to_response(
    membership: EmployeeDepartmentMembership,
    employee_name: str | None = None,
) -> MembershipResponse:
    return MembershipResponse(
        id=membership.id,
        employee_id=membership.employee_id,
        department_id=membership.department_id,
        role=membership.role,
        capacity_percent=membership.capacity_percent,
        is_primary=membership.is_primary,
        is_active=membership.is_active,
        employee_name=employee_name,
    )


async def _resolve_employee_name(
    db: AsyncSession, employee_id: uuid.UUID
) -> str | None:
    employee = await db.get(Employee, employee_id)
    return employee.name if employee else None


# ---------------------------------------------------------------------------
# Department: update + archive lifecycle
# ---------------------------------------------------------------------------


@router.patch("/departments/{department_id}", response_model=DepartmentResponse)
async def update_department(
    department_id: uuid.UUID,
    payload: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:manage"),
):
    """Partial update of a department.

    ``unit_type`` is immutable: trying to change it returns 400 instead of
    silently dropping the field. Use the archive/delete flow if you need to
    retire a department with the wrong type.
    """
    if payload.unit_type is not None:
        raise HTTPException(
            status_code=400,
            detail="unit_type cannot be changed after creation",
        )

    dept = await db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")

    if payload.name is not None:
        dept.name = payload.name
    if payload.description is not None:
        dept.description = payload.description

    await log_audit(db, _user, "update", "department", str(dept.id), reason=dept.name)
    await db.flush()
    await db.commit()
    await db.refresh(dept)

    member_count = await _active_member_count(db, dept.id)
    return DepartmentResponse(
        id=dept.id,
        name=dept.name,
        description=dept.description,
        unit_type=dept.unit_type,
        is_archived=dept.is_archived,
        archived_at=dept.archived_at,
        member_count=member_count,
    )


@router.post("/departments/{department_id}/archive")
async def archive_department(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:manage"),
):
    """Soft-archive a department.

    Blocked with 409 if any non-archived TaskProject still references the
    department. Memberships are deactivated as a side effect of archive.
    """
    try:
        result = await membership_service.archive_department(db, department_id)
    except DepartmentArchiveBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await log_audit(
        db, _user, "update", "department", str(department_id), reason="archive"
    )
    await db.commit()
    return result


@router.post("/departments/{department_id}/unarchive")
async def unarchive_department(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:manage"),
):
    """Flip the archived flag off. Memberships stay deactivated; callers must
    re-create them explicitly via POST /departments/{id}/members."""
    try:
        result = await membership_service.unarchive_department(db, department_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await log_audit(
        db, _user, "update", "department", str(department_id), reason="unarchive"
    )
    await db.commit()
    return result


# ---------------------------------------------------------------------------
# Department members
# ---------------------------------------------------------------------------


@router.get(
    "/departments/{department_id}/members",
    response_model=list[MembershipResponse],
)
async def list_members(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:read"),
):
    """List active members for a department, unioning the membership table with
    the legacy ``employees.department_id`` pointer.

    BIDV pilot data was created before the multi-unit membership backfill, so
    some employees only have ``employees.department_id`` set without a matching
    row in ``employee_department_memberships``. Mirror the union logic from
    ``task_access_service.list_eligible_assignees`` here so the forward-task
    picker (and any other UI that lists "who's in this unit") never shows a
    spurious empty list for legacy-only memberships.

    Legacy-only employees are reported as synthesized membership rows with a
    null UUID id and the ``member`` role; they have no real membership row,
    so PATCH /memberships/{id} on them will 404 — that's expected, callers
    should backfill via POST /departments/{id}/members first.
    """
    dept = await db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")

    membership_stmt = (
        select(EmployeeDepartmentMembership)
        .options(selectinload(EmployeeDepartmentMembership.employee))
        .where(
            EmployeeDepartmentMembership.department_id == department_id,
            EmployeeDepartmentMembership.is_active.is_(True),
        )
    )
    membership_rows = (await db.execute(membership_stmt)).scalars().all()
    seen_employee_ids: set[uuid.UUID] = {m.employee_id for m in membership_rows}

    legacy_stmt = (
        select(Employee)
        .where(
            Employee.department_id == department_id,
            Employee.is_active.is_(True),
        )
        .order_by(Employee.name, Employee.email)
    )
    if seen_employee_ids:
        legacy_stmt = legacy_stmt.where(Employee.id.notin_(seen_employee_ids))
    legacy_rows = (await db.execute(legacy_stmt)).scalars().all()

    response: list[MembershipResponse] = [
        _membership_to_response(
            m, employee_name=m.employee.name if m.employee else None
        )
        for m in membership_rows
    ]
    for emp in legacy_rows:
        response.append(
            MembershipResponse(
                id=uuid.UUID(int=0),
                employee_id=emp.id,
                department_id=department_id,
                role=MembershipRole.MEMBER,
                capacity_percent=None,
                is_primary=False,
                is_active=True,
                employee_name=emp.name,
            )
        )
    return response


@router.post(
    "/departments/{department_id}/members",
    status_code=201,
    response_model=MembershipResponse,
)
async def add_member(
    department_id: uuid.UUID,
    payload: MembershipCreate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:manage"),
):
    """Add an employee to the department with the given membership role.

    Role/unit_type combinations are validated by the service layer; invalid
    role choices return 400 with a descriptive detail string. Duplicate
    employee/department pairs return 409.
    """
    try:
        membership = await membership_service.create_membership(
            db,
            employee_id=payload.employee_id,
            department_id=department_id,
            role=payload.role,
            capacity_percent=payload.capacity_percent,
            set_primary=payload.set_primary,
        )
    except MembershipRoleNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        # "Department not found" → 404, everything else (duplicate, etc.) → 409
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=409, detail=message) from exc

    await log_audit(
        db,
        _user,
        "create",
        "membership",
        str(membership.id),
        reason=f"{payload.employee_id} -> {department_id} as {payload.role.value}",
    )
    await db.commit()
    await db.refresh(membership)
    employee_name = await _resolve_employee_name(db, membership.employee_id)
    return _membership_to_response(membership, employee_name=employee_name)


# ---------------------------------------------------------------------------
# Employee-scoped membership listing
# ---------------------------------------------------------------------------


@router.get(
    "/employees/{employee_id}/memberships",
    response_model=list[MembershipResponse],
)
async def list_employee_memberships(
    employee_id: uuid.UUID,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:employees:read"),
):
    """List memberships for a single employee, ordered with primary first.

    By default returns only active memberships, which matches the membership
    UI workflow (the employee dialog only edits active rows). Pass
    ``include_inactive=true`` to also see archived/deactivated rows.
    """
    employee = await db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    stmt = select(EmployeeDepartmentMembership).where(
        EmployeeDepartmentMembership.employee_id == employee_id,
    )
    if not include_inactive:
        stmt = stmt.where(EmployeeDepartmentMembership.is_active.is_(True))

    result = await db.execute(stmt)
    memberships = list(result.scalars().all())
    # Primary first, then by department_id for deterministic ordering.
    memberships.sort(key=lambda m: (0 if m.is_primary else 1, str(m.department_id)))
    return [
        _membership_to_response(m, employee_name=employee.name) for m in memberships
    ]


# ---------------------------------------------------------------------------
# Memberships (employee × department rows)
# ---------------------------------------------------------------------------


@router.patch("/memberships/{membership_id}", response_model=MembershipResponse)
async def update_membership(
    membership_id: uuid.UUID,
    payload: MembershipUpdate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:manage"),
):
    """Update role / capacity / activation status on a single membership."""
    try:
        membership = await membership_service.update_membership(
            db,
            membership_id,
            role=payload.role,
            capacity_percent=payload.capacity_percent,
            is_active=payload.is_active,
        )
    except MembershipRoleNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LastActiveMembershipError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await log_audit(
        db, _user, "update", "membership", str(membership.id), reason="update"
    )
    await db.commit()
    await db.refresh(membership)
    employee_name = await _resolve_employee_name(db, membership.employee_id)
    return _membership_to_response(membership, employee_name=employee_name)


@router.patch(
    "/memberships/{membership_id}/primary",
    response_model=MembershipResponse,
)
async def set_membership_primary(
    membership_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:manage"),
):
    """Promote a membership to the employee's primary. Inactive memberships
    cannot become primary; that case returns 400 with a service error."""
    try:
        membership = await membership_service.set_primary(db, membership_id)
    except ValueError as exc:
        message = str(exc)
        if "not found" in message.lower():
            raise HTTPException(status_code=404, detail=message) from exc
        raise HTTPException(status_code=400, detail=message) from exc

    await log_audit(
        db, _user, "update", "membership", str(membership.id), reason="set_primary"
    )
    await db.commit()
    await db.refresh(membership)
    employee_name = await _resolve_employee_name(db, membership.employee_id)
    return _membership_to_response(membership, employee_name=employee_name)


@router.delete("/memberships/{membership_id}")
async def delete_membership(
    membership_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:manage"),
):
    """Remove a membership row.

    Blocked with 409 if it is the employee's only remaining membership AND it
    is primary — the service enforces "every employee has at least one
    membership" as an invariant.
    """
    try:
        await membership_service.delete_membership(db, membership_id)
    except PrimaryMembershipRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await log_audit(
        db, _user, "delete", "membership", str(membership_id), reason="delete"
    )
    await db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Department sources (quick attach/detach for Knowledge tab)
# ---------------------------------------------------------------------------


class DepartmentSourceResponse(BaseModel):
    """Minimal source DTO for the department knowledge tab."""

    model_config = ConfigDict(from_attributes=True)

    source_id: uuid.UUID
    title: str | None = None
    source_type: str | None = None
    file_name: str | None = None
    status: str
    knowledge_type_name: str | None = None


@router.get(
    "/departments/{department_id}/sources",
    response_model=list[DepartmentSourceResponse],
)
async def list_department_sources(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:read"),
):
    """List sources currently attached to the department via SourceDepartment."""
    dept = await db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")

    stmt = (
        select(Source)
        .join(SourceDepartment, SourceDepartment.source_id == Source.id)
        .options(selectinload(Source.knowledge_type))
        .where(SourceDepartment.department_id == department_id)
        .order_by(Source.created_at.desc())
    )
    result = await db.execute(stmt)
    sources = result.scalars().all()
    return [
        DepartmentSourceResponse(
            source_id=s.id,
            title=s.title,
            source_type=s.source_type,
            file_name=s.file_name,
            status=s.status,
            knowledge_type_name=s.knowledge_type.name if s.knowledge_type else None,
        )
        for s in sources
    ]


@router.post(
    "/departments/{department_id}/sources/{source_id}",
    status_code=201,
)
async def attach_department_source(
    department_id: uuid.UUID,
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:manage"),
):
    """Attach a source to a department (idempotent — re-attach returns 200)."""
    dept = await db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")

    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    existing = await db.get(SourceDepartment, (source_id, department_id))
    if existing is not None:
        return {"attached": True, "already": True}

    db.add(SourceDepartment(source_id=source_id, department_id=department_id))
    await log_audit(
        db,
        _user,
        "create",
        "source_department",
        f"{source_id}:{department_id}",
        reason=source.title,
    )
    await db.commit()
    return {"attached": True, "already": False}


@router.delete("/departments/{department_id}/sources/{source_id}")
async def detach_department_source(
    department_id: uuid.UUID,
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:manage"),
):
    """Detach a source from a department."""
    dept = await db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")

    existing = await db.get(SourceDepartment, (source_id, department_id))
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail="Source not attached to this department",
        )

    await db.execute(
        sql_delete(SourceDepartment).where(
            SourceDepartment.source_id == source_id,
            SourceDepartment.department_id == department_id,
        )
    )
    await log_audit(
        db,
        _user,
        "delete",
        "source_department",
        f"{source_id}:{department_id}",
    )
    await db.commit()
    return {"detached": True}


# ---------------------------------------------------------------------------
# Department × Skill (M2M join via SkillDepartment) — Skills hub tab
# ---------------------------------------------------------------------------


@router.get(
    "/departments/{department_id}/skills",
    response_model=list[DepartmentSkillResponse],
)
async def list_department_skills(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("skill:read"),
):
    """List AI skills attached to this department via SkillDepartment.

    Returns only active (non-deleting) rows ordered by most-recent update.
    Global skills (no SkillDepartment row) are intentionally excluded — they
    are served by the unscoped ``/api/skills`` listing.
    """
    dept = await db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")

    stmt = (
        select(Skill)
        .join(SkillDepartment, SkillDepartment.skill_id == Skill.id)
        .where(
            SkillDepartment.department_id == department_id,
            Skill.status != "deleting",
        )
        .order_by(Skill.updated_at.desc(), Skill.id.desc())
    )
    result = await db.execute(stmt)
    skills = result.scalars().unique().all()
    return [DepartmentSkillResponse.model_validate(s) for s in skills]


@router.post(
    "/departments/{department_id}/skills/{skill_id}",
    status_code=201,
    response_model=DepartmentSkillResponse,
)
async def attach_department_skill(
    department_id: uuid.UUID,
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("skill:edit"),
):
    """Attach a skill to a department.

    Idempotent — re-attaching an already-linked skill returns 201 with the
    current state instead of 409, matching the tab's "click again to retry"
    UX. The skill's legacy ``scope_type``/``scope_id`` columns are kept in
    sync with the M2M state so the wider ``/api/skills`` listing stays
    consistent.
    """
    dept = await db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")
    skill = await db.get(Skill, skill_id)
    if skill is None or skill.status == "deleting":
        raise HTTPException(status_code=404, detail="Skill not found")

    link_stmt = select(SkillDepartment).where(
        SkillDepartment.skill_id == skill_id,
        SkillDepartment.department_id == department_id,
    )
    existing = (await db.execute(link_stmt)).scalars().first()
    if existing is None:
        db.add(SkillDepartment(skill_id=skill_id, department_id=department_id))
        # Flip global → department-scoped so /api/skills filters stay coherent.
        if skill.scope_type == "global":
            skill.scope_type = "department"
        if skill.scope_id is None:
            skill.scope_id = department_id
        await log_audit(
            db,
            _user,
            "create",
            "skill_department",
            f"{skill_id}:{department_id}",
            reason=f"attach skill '{skill.name}' to dept '{dept.name}'",
        )
        await db.commit()
        await db.refresh(skill)

    return DepartmentSkillResponse.model_validate(skill)


@router.delete("/departments/{department_id}/skills/{skill_id}")
async def detach_department_skill(
    department_id: uuid.UUID,
    skill_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("skill:edit"),
):
    """Detach a skill from a department.

    If this was the last remaining link, the skill flips back to ``global``
    scope so it remains visible in the unscoped listing. If ``scope_id`` was
    pointing at the now-detached department, it is reassigned to one of the
    remaining links for legacy consumers that still read ``scope_id``.

    Returns 404 if the skill was not attached to this department.
    """
    dept = await db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="Department not found")
    skill = await db.get(Skill, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")

    link_stmt = select(SkillDepartment).where(
        SkillDepartment.skill_id == skill_id,
        SkillDepartment.department_id == department_id,
    )
    link = (await db.execute(link_stmt)).scalars().first()
    if link is None:
        raise HTTPException(
            status_code=404, detail="Skill is not attached to this department"
        )

    await db.delete(link)
    await db.flush()

    remaining_stmt = select(SkillDepartment.department_id).where(
        SkillDepartment.skill_id == skill_id
    )
    remaining = (await db.execute(remaining_stmt)).scalars().all()
    if not remaining:
        skill.scope_type = "global"
        skill.scope_id = None
    elif skill.scope_id == department_id:
        skill.scope_id = remaining[0]

    await log_audit(
        db,
        _user,
        "delete",
        "skill_department",
        f"{skill_id}:{department_id}",
        reason=f"detach skill '{skill.name}' from dept '{dept.name}'",
    )
    await db.commit()
    return {"detached": True}


# ---------------------------------------------------------------------------
# Shared helpers (also used by rbac.py via import)
# ---------------------------------------------------------------------------


async def _active_member_count(db: AsyncSession, department_id: uuid.UUID) -> int:
    """Count active memberships for a department.

    Lives here so ``rbac.py`` can reuse the same definition when shaping
    its list/create responses.
    """
    from sqlalchemy import func

    stmt = select(func.count(EmployeeDepartmentMembership.id)).where(
        EmployeeDepartmentMembership.department_id == department_id,
        EmployeeDepartmentMembership.is_active.is_(True),
    )
    result = await db.execute(stmt)
    return int(result.scalar() or 0)
