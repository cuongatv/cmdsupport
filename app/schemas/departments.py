"""Pydantic DTOs for departments and employee_department_memberships."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.database.models import MembershipRole, UnitType

# ---------------------------------------------------------------------------
# Department DTOs
# ---------------------------------------------------------------------------


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    unit_type: UnitType
    is_archived: bool
    archived_at: Optional[datetime] = None
    member_count: int = 0


class DepartmentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    unit_type: UnitType = UnitType.BUSINESS_GROUP


class DepartmentUpdate(BaseModel):
    """Department update payload.

    `unit_type` is accepted by the schema but rejected at the router level
    so the API can return a clear 400 instead of silently dropping the field.
    """

    name: Optional[str] = None
    description: Optional[str] = None
    unit_type: Optional[UnitType] = None


# ---------------------------------------------------------------------------
# Membership DTOs
# ---------------------------------------------------------------------------


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    department_id: uuid.UUID
    role: MembershipRole
    capacity_percent: Optional[int] = None
    is_primary: bool
    is_active: bool
    employee_name: Optional[str] = None


class MembershipCreate(BaseModel):
    employee_id: uuid.UUID
    role: MembershipRole
    capacity_percent: Optional[int] = None
    set_primary: bool = False


class MembershipUpdate(BaseModel):
    role: Optional[MembershipRole] = None
    capacity_percent: Optional[int] = None
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Department × Skill DTOs (Skills hub tab)
# ---------------------------------------------------------------------------


class DepartmentSkillResponse(BaseModel):
    """Lightweight view of a skill attached to a department.

    Drives the Skills tab on the department hub — name, latest version,
    updated_at, and the bits the UI needs to render a detach action. Full
    skill detail (description, files, etc.) is still served by /api/skills.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    current_version: int
    status: str
    updated_at: datetime
