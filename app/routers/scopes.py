"""
Scope membership router — manage who has access to what scope.

Endpoints:
  GET    /scopes/{scope_type}/{scope_id}/members  — list members
  POST   /scopes/{scope_type}/{scope_id}/members  — add member
  PATCH  /scopes/{scope_type}/{scope_id}/members/{emp_id}  — change role
  DELETE /scopes/{scope_type}/{scope_id}/members/{emp_id}  — remove member
  GET    /my/scopes  — list my scope memberships
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.database.models import (
    Action,
    Employee,
    ScopeMembership,
    ScopeRole,
    ScopeType,
)
from app.services.auth_service import get_current_user
from app.services.policy_engine import PolicyEngine

router = APIRouter(tags=["scopes"])


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

class ScopeMemberOut(BaseModel):
    id: str
    employee_id: str
    employee_name: str
    employee_email: str
    scope_type: str
    scope_id: Optional[str] = None
    role: str
    granted_by_name: Optional[str] = None
    created_at: str


class AddMemberBody(BaseModel):
    employee_id: str
    role: str = "reader"


class UpdateRoleBody(BaseModel):
    role: str


class MyScopeOut(BaseModel):
    scope_type: str
    scope_id: Optional[str] = None
    scope_name: Optional[str] = None
    role: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_scope_type(scope_type: str) -> ScopeType:
    try:
        return ScopeType(scope_type)
    except ValueError:
        raise HTTPException(400, f"Invalid scope type: {scope_type}. Must be one of: {[t.value for t in ScopeType]}")


def _validate_role(role: str) -> ScopeRole:
    try:
        return ScopeRole(role)
    except ValueError:
        raise HTTPException(400, f"Invalid role: {role}. Must be one of: {[r.value for r in ScopeRole]}")


def _parse_scope_id(scope_type: ScopeType, scope_id_str: str) -> Optional[uuid.UUID]:
    """Parse scope_id. 'global' scope uses '_' or 'global' as placeholder."""
    if scope_type == ScopeType.GLOBAL:
        return None
    try:
        return uuid.UUID(scope_id_str)
    except ValueError:
        raise HTTPException(400, f"Invalid scope_id: {scope_id_str}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/scopes/{scope_type}/{scope_id}/members", response_model=list[ScopeMemberOut])
async def list_scope_members(
    scope_type: str,
    scope_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """List all members of a scope. Requires membership in the scope or admin."""
    st = _validate_scope_type(scope_type)
    sid = _parse_scope_id(st, scope_id)

    # Check access: must be member of scope or admin
    engine = PolicyEngine(db)
    if current_user.role != "admin":
        has_access = await engine.has_scope_access(
            current_user.id, st.value, sid,
        )
        if not has_access:
            raise HTTPException(403, "Not a member of this scope")

    stmt = (
        select(ScopeMembership)
        .options(
            selectinload(ScopeMembership.employee),
            selectinload(ScopeMembership.granted_by),
        )
        .where(ScopeMembership.scope_type == st.value)
    )
    if sid is not None:
        stmt = stmt.where(ScopeMembership.scope_id == sid)
    else:
        stmt = stmt.where(ScopeMembership.scope_id.is_(None))

    result = await db.execute(stmt)
    memberships = result.scalars().all()

    return [
        ScopeMemberOut(
            id=str(m.id),
            employee_id=str(m.employee_id),
            employee_name=m.employee.name if m.employee else "",
            employee_email=m.employee.email if m.employee else "",
            scope_type=m.scope_type,
            scope_id=str(m.scope_id) if m.scope_id else None,
            role=m.role,
            granted_by_name=m.granted_by.name if m.granted_by else None,
            created_at=m.created_at.isoformat(),
        )
        for m in memberships
    ]


@router.post("/scopes/{scope_type}/{scope_id}/members", status_code=201)
async def add_scope_member(
    scope_type: str,
    scope_id: str,
    body: AddMemberBody,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """
    Add a member to a scope. Requires owner+ in the scope or admin.
    Default role = reader (FR-12).
    """
    st = _validate_scope_type(scope_type)
    sid = _parse_scope_id(st, scope_id)
    target_role = _validate_role(body.role)

    # Check: must be scope owner/admin or system admin
    engine = PolicyEngine(db)
    if current_user.role != "admin":
        await engine.check_or_raise(
            current_user, Action.MANAGE_MEMBERS, st.value, sid,
            resource_type="scope_membership",
            resource_id=f"{st.value}:{sid or 'global'}",
        )

    # Verify employee exists
    emp = await db.get(Employee, uuid.UUID(body.employee_id))
    if not emp:
        raise HTTPException(404, "Employee not found")

    # Check for existing membership
    existing_stmt = (
        select(ScopeMembership)
        .where(
            ScopeMembership.employee_id == emp.id,
            ScopeMembership.scope_type == st.value,
        )
    )
    if sid is not None:
        existing_stmt = existing_stmt.where(ScopeMembership.scope_id == sid)
    else:
        existing_stmt = existing_stmt.where(ScopeMembership.scope_id.is_(None))

    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Employee is already a member of this scope")

    membership = ScopeMembership(
        employee_id=emp.id,
        scope_type=st.value,
        scope_id=sid,
        role=target_role.value,
        granted_by_id=current_user.id,
    )
    db.add(membership)
    await db.flush()

    return {"id": str(membership.id), "role": membership.role}


@router.patch("/scopes/{scope_type}/{scope_id}/members/{emp_id}")
async def update_member_role(
    scope_type: str,
    scope_id: str,
    emp_id: str,
    body: UpdateRoleBody,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """Change a member's role within a scope. Requires owner+ or admin."""
    st = _validate_scope_type(scope_type)
    sid = _parse_scope_id(st, scope_id)
    new_role = _validate_role(body.role)

    # Check access
    engine = PolicyEngine(db)
    if current_user.role != "admin":
        await engine.check_or_raise(
            current_user, Action.MANAGE_MEMBERS, st.value, sid,
            resource_type="scope_membership",
            resource_id=f"{st.value}:{sid or 'global'}",
        )

    # Find membership
    stmt = (
        select(ScopeMembership)
        .where(
            ScopeMembership.employee_id == uuid.UUID(emp_id),
            ScopeMembership.scope_type == st.value,
        )
    )
    if sid is not None:
        stmt = stmt.where(ScopeMembership.scope_id == sid)
    else:
        stmt = stmt.where(ScopeMembership.scope_id.is_(None))

    membership = (await db.execute(stmt)).scalar_one_or_none()
    if not membership:
        raise HTTPException(404, "Membership not found")

    membership.role = new_role.value
    await db.flush()
    return {"role": membership.role}


@router.delete("/scopes/{scope_type}/{scope_id}/members/{emp_id}")
async def remove_scope_member(
    scope_type: str,
    scope_id: str,
    emp_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """Remove a member from a scope. Requires owner+ or admin."""
    st = _validate_scope_type(scope_type)
    sid = _parse_scope_id(st, scope_id)

    # Check access
    engine = PolicyEngine(db)
    if current_user.role != "admin":
        await engine.check_or_raise(
            current_user, Action.MANAGE_MEMBERS, st.value, sid,
            resource_type="scope_membership",
            resource_id=f"{st.value}:{sid or 'global'}",
        )

    # Find membership
    stmt = (
        select(ScopeMembership)
        .where(
            ScopeMembership.employee_id == uuid.UUID(emp_id),
            ScopeMembership.scope_type == st.value,
        )
    )
    if sid is not None:
        stmt = stmt.where(ScopeMembership.scope_id == sid)
    else:
        stmt = stmt.where(ScopeMembership.scope_id.is_(None))

    membership = (await db.execute(stmt)).scalar_one_or_none()
    if not membership:
        raise HTTPException(404, "Membership not found")

    await db.delete(membership)
    return {"removed": True}


@router.get("/my/scopes", response_model=list[MyScopeOut])
async def get_my_scopes(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """Get the current user's scope memberships."""
    from app.database.models import Department, Project

    stmt = (
        select(ScopeMembership)
        .where(ScopeMembership.employee_id == current_user.id)
        .order_by(ScopeMembership.scope_type, ScopeMembership.created_at)
    )
    result = await db.execute(stmt)
    memberships = result.scalars().all()

    out = []
    for m in memberships:
        scope_name = None
        if m.scope_type == ScopeType.DEPARTMENT.value and m.scope_id:
            dept = await db.get(Department, m.scope_id)
            scope_name = dept.name if dept else None
        elif m.scope_type == ScopeType.PROJECT.value and m.scope_id:
            proj = await db.get(Project, m.scope_id)
            scope_name = proj.name if proj else None
        elif m.scope_type == ScopeType.GLOBAL.value:
            scope_name = "Global"

        out.append(MyScopeOut(
            scope_type=m.scope_type,
            scope_id=str(m.scope_id) if m.scope_id else None,
            scope_name=scope_name,
            role=m.role,
        ))

    return out
