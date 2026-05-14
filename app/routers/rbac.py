"""
Department & Employee router — RBAC management for admin portal.
Permission model v2: uses scoped permission format.
"""

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    Province,
    Role,
    UnitType,
)
from app.services import membership_service
from app.services.audit_service import log_audit
from app.services.auth_service import (
    get_current_user,
    hash_password,
    require_permission,
)
from app.services.mcp_auth_service import MCPAuthService
from app.services.membership_service import DepartmentDeleteBlockedError
from app.services.permissions import EMPLOYEE_DEFAULT_PERMISSIONS
from app.services.storage_service import storage_service

# Allowed avatar formats (jpg/jpeg/png/webp) — extension is the source of truth,
# content-type is best-effort because browsers/clients are inconsistent.
AVATAR_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
AVATAR_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}
AVATAR_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

router = APIRouter()


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class DepartmentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    unit_type: UnitType = UnitType.BUSINESS_GROUP


class DepartmentOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    unit_type: UnitType = UnitType.BUSINESS_GROUP
    is_archived: bool = False
    archived_at: Optional[str] = None
    member_count: int = 0
    # Legacy field kept for the existing admin UI — equals member_count.
    employee_count: int = 0

    class Config:
        from_attributes = True


class EmployeeCreate(BaseModel):
    name: str
    email: str
    password: Optional[str] = None  # Optional on update
    role: str = "employee"  # "admin" or "employee"
    department_id: str
    custom_role_id: Optional[str] = None
    phone: Optional[str] = None
    zalo_phone: Optional[str] = None
    slogan: Optional[str] = None


class EmployeeOut(BaseModel):
    id: str
    name: str
    email: str
    role: str
    department_id: str
    department_name: str = ""
    is_active: bool
    has_token: bool
    last_connected: Optional[str] = None
    custom_role_id: Optional[str] = None
    custom_role_name: Optional[str] = None
    phone: Optional[str] = None
    zalo_phone: Optional[str] = None
    # effective_zalo_phone = zalo_phone if set, else phone. Computed on read so
    # downstream Zalo tasks can use a single field without re-implementing the
    # fallback rule everywhere.
    effective_zalo_phone: Optional[str] = None
    slogan: Optional[str] = None
    avatar_url: Optional[str] = None

    class Config:
        from_attributes = True


class AvatarResponse(BaseModel):
    avatar_url: str


class TokenResponse(BaseModel):
    token: str
    employee_name: str
    instructions: str


class EmployeeContactOut(BaseModel):
    """Compact employee contact card.

    Used by both the Menu Tổ chức assignment tab and the CMD advisory result
    HQ contact section. `effective_zalo_phone` falls back to `phone` so callers
    don't have to re-implement the rule.
    """

    id: str
    name: str
    email: str
    department_name: str = ""
    phone: Optional[str] = None
    zalo_phone: Optional[str] = None
    effective_zalo_phone: Optional[str] = None
    avatar_url: Optional[str] = None
    slogan: Optional[str] = None
    is_active: bool = True

    class Config:
        from_attributes = True


class ProvinceAssignmentOut(BaseModel):
    province_id: str
    province_code: str
    province_name: str
    province_short_name: str
    province_type: str
    region: str
    assigned_employee_id: Optional[str] = None
    assigned_employee: Optional[EmployeeContactOut] = None

    class Config:
        from_attributes = True


class ProvinceAssignmentUpdate(BaseModel):
    employee_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _avatar_url_for(emp: Employee) -> Optional[str]:
    """Return a presigned URL for the employee's avatar, or None."""
    if not emp.avatar_key:
        return None
    try:
        return storage_service.get_download_url(emp.avatar_key, expires_seconds=3600)
    except Exception as exc:  # noqa: BLE001 — never break the user list over a broken avatar
        logger.warning(f"Failed to presign avatar for employee {emp.id}: {exc}")
        return None


def _employee_to_contact(emp: Optional[Employee]) -> Optional[EmployeeContactOut]:
    """Shape an Employee into the compact contact card used by the advisory
    HQ section and the admin province-assignment tab."""
    if emp is None:
        return None
    return EmployeeContactOut(
        id=str(emp.id),
        name=emp.name,
        email=emp.email,
        department_name=emp.department.name if emp.department else "",
        phone=emp.phone,
        zalo_phone=emp.zalo_phone,
        effective_zalo_phone=emp.zalo_phone or emp.phone,
        avatar_url=_avatar_url_for(emp),
        slogan=emp.slogan,
        is_active=emp.is_active,
    )


def _province_to_assignment(prov: Province) -> ProvinceAssignmentOut:
    return ProvinceAssignmentOut(
        province_id=str(prov.id),
        province_code=prov.code,
        province_name=prov.name,
        province_short_name=prov.short_name,
        province_type=prov.type,
        region=prov.region,
        assigned_employee_id=(
            str(prov.assigned_employee_id) if prov.assigned_employee_id else None
        ),
        assigned_employee=_employee_to_contact(prov.assigned_employee),
    )


def _employee_to_out(emp: Employee) -> EmployeeOut:
    return EmployeeOut(
        id=str(emp.id),
        name=emp.name,
        email=emp.email,
        role=emp.role,
        department_id=str(emp.department_id),
        department_name=emp.department.name if emp.department else "",
        is_active=emp.is_active,
        has_token=bool(emp.mcp_token),
        last_connected=emp.last_connected.isoformat() if emp.last_connected else None,
        custom_role_id=str(emp.custom_role_id) if emp.custom_role_id else None,
        custom_role_name=emp.custom_role.name if emp.custom_role else None,
        phone=emp.phone,
        zalo_phone=emp.zalo_phone,
        effective_zalo_phone=emp.zalo_phone or emp.phone,
        slogan=emp.slogan,
        avatar_url=_avatar_url_for(emp),
    )


# ---------------------------------------------------------------------------
# Department CRUD
# ---------------------------------------------------------------------------


@router.get("/departments")
async def list_departments(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:read"),
):
    """List all departments with active-membership counts.

    ``member_count`` is the number of *active* rows in
    ``employee_department_memberships``. ``employee_count`` is kept for
    legacy UI callers and mirrors ``member_count``.
    """
    stmt = select(Department)
    result = await db.execute(stmt)
    departments = result.scalars().all()

    member_counts_stmt = (
        select(
            EmployeeDepartmentMembership.department_id,
            sa_func.count(EmployeeDepartmentMembership.id),
        )
        .where(EmployeeDepartmentMembership.is_active.is_(True))
        .group_by(EmployeeDepartmentMembership.department_id)
    )
    member_counts_rows = (await db.execute(member_counts_stmt)).all()
    counts: dict[uuid.UUID, int] = {row[0]: int(row[1]) for row in member_counts_rows}

    return [
        DepartmentOut(
            id=str(d.id),
            name=d.name,
            description=d.description,
            unit_type=d.unit_type,
            is_archived=d.is_archived,
            archived_at=d.archived_at.isoformat() if d.archived_at else None,
            member_count=counts.get(d.id, 0),
            employee_count=counts.get(d.id, 0),
        )
        for d in departments
    ]


@router.post("/departments", status_code=201)
async def create_department(
    body: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:manage"),
):
    """Create a new department.

    ``unit_type`` is captured at creation time and is immutable thereafter —
    PATCH /api/departments/{id} will reject any attempt to change it.
    """
    dept = Department(
        name=body.name,
        description=body.description,
        unit_type=body.unit_type,
    )
    db.add(dept)
    await db.flush()
    await log_audit(db, _user, "create", "department", str(dept.id), reason=dept.name)
    await db.commit()
    await db.refresh(dept)
    return {
        "id": str(dept.id),
        "name": dept.name,
        "unit_type": dept.unit_type.value,
        "is_archived": dept.is_archived,
    }


@router.put("/departments/{dept_id}")
async def update_department(
    dept_id: str,
    body: DepartmentCreate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:manage"),
):
    """Legacy PUT — kept for the existing admin UI.

    Name and description only; ``unit_type`` cannot be changed once set
    (use PATCH /api/departments/{id} which returns a clear 400 if attempted).
    """
    dept = await db.get(Department, uuid.UUID(dept_id))
    if not dept:
        raise HTTPException(404, "Department not found")
    dept.name = body.name
    dept.description = body.description
    await log_audit(db, _user, "update", "department", str(dept.id), reason=dept.name)
    await db.flush()
    return {"id": str(dept.id), "name": dept.name}


@router.delete("/departments/{dept_id}")
async def delete_department(
    dept_id: str,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:manage"),
):
    """Hard-delete a department.

    Delegates safety checks to ``membership_service.delete_department`` which
    refuses to drop a department that is not archived, still has memberships,
    or still has TaskProject rows pointing at it. Each refusal surfaces here
    as a 409 with the offending reason(s) in ``detail``.
    """
    try:
        dept_uuid = uuid.UUID(dept_id)
    except ValueError as exc:
        raise HTTPException(400, "Invalid department id") from exc

    try:
        await membership_service.delete_department(db, dept_uuid)
    except DepartmentDeleteBlockedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await log_audit(db, _user, "delete", "department", dept_id, reason="hard delete")
    await db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Employee CRUD
# ---------------------------------------------------------------------------


@router.get("/employees")
async def list_employees(
    department_id: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:employees:read"),
):
    """List employees with pagination, optionally filtered by department or search."""
    from sqlalchemy import func as sa_func

    base = select(Employee).options(
        selectinload(Employee.department), selectinload(Employee.custom_role)
    )
    count_base = select(sa_func.count(Employee.id))

    if department_id:
        base = base.where(Employee.department_id == uuid.UUID(department_id))
        count_base = count_base.where(
            Employee.department_id == uuid.UUID(department_id)
        )
    if search:
        like = f"%{search}%"
        base = base.where(Employee.name.ilike(like) | Employee.email.ilike(like))
        count_base = count_base.where(
            Employee.name.ilike(like) | Employee.email.ilike(like)
        )

    # Total count
    total = (await db.execute(count_base)).scalar() or 0

    # Paginated query
    offset = (max(page, 1) - 1) * page_size
    stmt = base.order_by(Employee.name).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    employees = result.scalars().all()

    return {
        "items": [_employee_to_out(e) for e in employees],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),  # ceil division
    }


@router.post("/employees", status_code=201)
async def create_employee(
    body: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:employees:manage"),
):
    """Create a new employee."""
    dept = await db.get(Department, uuid.UUID(body.department_id))
    if not dept:
        raise HTTPException(400, "Department not found")

    if not body.password:
        raise HTTPException(400, "Password is required")
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    if body.role not in ("admin", "employee"):
        raise HTTPException(400, "Role must be 'admin' or 'employee'")

    custom_role_id = uuid.UUID(body.custom_role_id) if body.custom_role_id else None
    if body.role == "employee" and custom_role_id is None:
        custom_role = (
            await db.execute(
                select(Role).where(Role.name == "Employee", Role.is_system.is_(True))
            )
        ).scalar_one_or_none()
        if custom_role is None:
            custom_role = Role(
                name="Employee",
                description="Default employee permissions",
                permissions=EMPLOYEE_DEFAULT_PERMISSIONS,
                is_system=True,
            )
            db.add(custom_role)
            await db.flush()
        custom_role_id = custom_role.id

    emp = Employee(
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
        department_id=uuid.UUID(body.department_id),
        custom_role_id=custom_role_id,
        phone=(body.phone or None),
        zalo_phone=(body.zalo_phone or None),
        slogan=(body.slogan or None),
    )
    db.add(emp)
    await log_audit(db, _user, "create", "employee", str(emp.id), reason=emp.email)
    await db.flush()
    await db.commit()

    return {
        "id": str(emp.id),
        "name": emp.name,
        "email": emp.email,
        "custom_role_id": str(emp.custom_role_id) if emp.custom_role_id else None,
        "phone": emp.phone,
        "zalo_phone": emp.zalo_phone,
        "slogan": emp.slogan,
    }


@router.put("/employees/{emp_id}")
async def update_employee(
    emp_id: str,
    body: EmployeeCreate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:employees:manage"),
):
    emp = await db.get(Employee, uuid.UUID(emp_id))
    if not emp:
        raise HTTPException(404, "Employee not found")
    emp.name = body.name
    emp.email = body.email
    emp.role = body.role
    emp.department_id = uuid.UUID(body.department_id)
    emp.custom_role_id = uuid.UUID(body.custom_role_id) if body.custom_role_id else None
    # Treat empty strings as "clear the field" so the user can intentionally
    # blank phone/zalo/slogan from the edit form. The zalo fallback to phone
    # only happens at read time via effective_zalo_phone.
    emp.phone = body.phone or None
    emp.zalo_phone = body.zalo_phone or None
    emp.slogan = body.slogan or None
    if body.password:
        emp.password_hash = hash_password(body.password)
    await log_audit(db, _user, "update", "employee", str(emp.id), reason=emp.email)
    await db.flush()
    return {"id": str(emp.id), "name": emp.name}


@router.delete("/employees/{emp_id}")
async def delete_employee(
    emp_id: str,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:employees:manage"),
):
    emp = await db.get(Employee, uuid.UUID(emp_id))
    if not emp:
        raise HTTPException(404, "Employee not found")
    if emp.role == "admin":
        raise HTTPException(400, "Cannot delete an admin account")
    await log_audit(db, _user, "delete", "employee", str(emp.id), reason=emp.email)
    await db.delete(emp)
    return {"deleted": True}


@router.patch("/employees/{emp_id}/toggle")
async def toggle_employee(
    emp_id: str,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:employees:manage"),
):
    """Activate or deactivate an employee."""
    emp = await db.get(Employee, uuid.UUID(emp_id))
    if not emp:
        raise HTTPException(404, "Employee not found")
    emp.is_active = not emp.is_active
    await log_audit(
        db,
        _user,
        "update",
        "employee",
        str(emp.id),
        reason=f"toggle active={emp.is_active}",
    )
    await db.flush()
    return {"id": str(emp.id), "is_active": emp.is_active}


# ---------------------------------------------------------------------------
# Avatar Upload
# ---------------------------------------------------------------------------


@router.post("/employees/{emp_id}/avatar", response_model=AvatarResponse)
async def upload_employee_avatar(
    emp_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:employees:manage"),
):
    """Upload (or replace) an employee's avatar. Accepts jpg/jpeg/png/webp."""
    emp = await db.get(Employee, uuid.UUID(emp_id))
    if not emp:
        raise HTTPException(404, "Employee not found")

    file_name = file.filename or ""
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in AVATAR_ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            "Định dạng ảnh không hợp lệ. Chỉ chấp nhận jpg, jpeg, png, webp.",
        )
    if (
        file.content_type
        and file.content_type.lower() not in AVATAR_ALLOWED_CONTENT_TYPES
    ):
        raise HTTPException(
            400,
            f"Content-Type không hợp lệ: {file.content_type}.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(400, "Tệp ảnh trống.")
    if len(data) > AVATAR_MAX_BYTES:
        raise HTTPException(
            413,
            f"Ảnh quá lớn. Tối đa {AVATAR_MAX_BYTES // (1024 * 1024)} MB.",
        )

    # Map extension → canonical content-type so the stored object serves with
    # the right header even if the client lied about content_type.
    content_type_by_ext = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    storage_content_type = content_type_by_ext[ext]

    # Delete previous avatar (best-effort) so we don't leak orphaned objects.
    if emp.avatar_key:
        try:
            storage_service.delete_object(emp.avatar_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to delete previous avatar {emp.avatar_key}: {exc}")

    object_name = f"employees/{emp.id}/avatar/avatar{ext}"
    storage_service.upload_file(
        object_name=object_name,
        data=data,
        content_type=storage_content_type,
    )

    emp.avatar_key = object_name
    await log_audit(
        db, _user, "update", "employee", str(emp.id), reason="upload avatar"
    )
    await db.flush()
    await db.commit()

    presigned = storage_service.get_download_url(object_name, expires_seconds=3600)
    return AvatarResponse(avatar_url=presigned)


@router.delete("/employees/{emp_id}/avatar")
async def delete_employee_avatar(
    emp_id: str,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:employees:manage"),
):
    """Remove an employee's avatar."""
    emp = await db.get(Employee, uuid.UUID(emp_id))
    if not emp:
        raise HTTPException(404, "Employee not found")
    if emp.avatar_key:
        try:
            storage_service.delete_object(emp.avatar_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Failed to delete avatar {emp.avatar_key}: {exc}")
        emp.avatar_key = None
        await log_audit(
            db, _user, "update", "employee", str(emp.id), reason="delete avatar"
        )
        await db.flush()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# MCP Token Management
# ---------------------------------------------------------------------------


@router.post("/employees/{emp_id}/token", response_model=TokenResponse)
async def generate_mcp_token(
    emp_id: str,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:employees:manage"),
):
    """Generate (or regenerate) an MCP token for an employee."""
    emp = await db.get(Employee, uuid.UUID(emp_id))
    if not emp:
        raise HTTPException(404, "Employee not found")

    auth_svc = MCPAuthService(db)
    token = await auth_svc.generate_token(emp.id)

    return TokenResponse(
        token=token,
        employee_name=emp.name,
        instructions=(
            f"Add this to Claude Desktop config:\n"
            f'{{"mcpServers": {{"arkon": {{"url": "https://your-server/mcp", '
            f'"headers": {{"Authorization": "Bearer {token}"}}}}}}}}'
        ),
    )


@router.delete("/employees/{emp_id}/token")
async def revoke_mcp_token(
    emp_id: str,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:employees:manage"),
):
    """Revoke an employee's MCP token."""
    auth_svc = MCPAuthService(db)
    revoked = await auth_svc.revoke_token(uuid.UUID(emp_id))
    if not revoked:
        raise HTTPException(404, "Employee not found or has no token")
    return {"revoked": True}


# ---------------------------------------------------------------------------
# Self-Service: Employee gets their own MCP token
# ---------------------------------------------------------------------------


@router.post("/my/mcp-token", response_model=TokenResponse)
async def get_my_mcp_token(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """
    Generate (or show) the current employee's own MCP token.
    This is the self-service endpoint employees use from their portal.
    """
    auth_svc = MCPAuthService(db)

    if not current_user.mcp_token:
        token = await auth_svc.generate_token(current_user.id)
    else:
        token = current_user.mcp_token

    return TokenResponse(
        token=token,
        employee_name=current_user.name,
        instructions=(
            f"Add this to Claude Desktop config:\n"
            f'{{"mcpServers": {{"arkon": {{"url": "https://your-server/mcp", '
            f'"headers": {{"Authorization": "Bearer {token}"}}}}}}}}'
        ),
    )


@router.delete("/my/mcp-token")
async def revoke_my_mcp_token(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
):
    """Revoke the current employee's own MCP token."""
    auth_svc = MCPAuthService(db)
    await auth_svc.revoke_token(current_user.id)
    return {"revoked": True}


@router.get("/my/mcp-token/status")
async def get_my_mcp_token_status(
    current_user: Employee = Depends(get_current_user),
):
    """Check if the current employee has an active MCP token (without revealing it)."""
    return {"has_token": bool(current_user.mcp_token)}


# ---------------------------------------------------------------------------
# Province ↔ Employee Assignment (Menu Tổ chức → Thông tin phụ trách Chi nhánh)
# ---------------------------------------------------------------------------


@router.get("/province-assignments")
async def list_province_assignments(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:employees:read"),
):
    """List every province/city with the assigned HQ contact officer (if any)."""
    stmt = (
        select(Province)
        .options(
            selectinload(Province.assigned_employee).selectinload(Employee.department),
        )
        .order_by(Province.sort_order)
    )
    result = await db.execute(stmt)
    provinces = result.scalars().all()
    return [_province_to_assignment(p) for p in provinces]


@router.patch("/province-assignments/{province_id}")
async def update_province_assignment(
    province_id: str,
    body: ProvinceAssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:employees:manage"),
):
    """Assign (or clear) the HQ contact officer for a province/city."""
    try:
        prov_uuid = uuid.UUID(province_id)
    except ValueError as exc:
        raise HTTPException(400, "province_id không hợp lệ") from exc

    prov = await db.get(Province, prov_uuid)
    if prov is None:
        raise HTTPException(404, "Tỉnh/Thành phố không tồn tại")

    new_assignee_id: Optional[uuid.UUID] = None
    if body.employee_id:
        try:
            new_assignee_id = uuid.UUID(body.employee_id)
        except ValueError as exc:
            raise HTTPException(400, "employee_id không hợp lệ") from exc
        emp = await db.get(Employee, new_assignee_id)
        if emp is None:
            raise HTTPException(404, "Người dùng không tồn tại")
        if not emp.is_active:
            raise HTTPException(
                400,
                "Không thể gán cán bộ đã ngưng hoạt động làm đầu mối phụ trách.",
            )

    prov.assigned_employee_id = new_assignee_id
    await log_audit(
        db,
        _user,
        "update",
        "province_assignment",
        str(prov.id),
        reason=(
            f"{prov.code} -> {new_assignee_id}"
            if new_assignee_id
            else f"{prov.code} -> cleared"
        ),
    )
    await db.flush()
    await db.commit()

    # Re-fetch with relationships so the response matches GET /province-assignments.
    refreshed = (
        await db.execute(
            select(Province)
            .options(
                selectinload(Province.assigned_employee).selectinload(
                    Employee.department
                ),
            )
            .where(Province.id == prov.id)
        )
    ).scalar_one()
    return _province_to_assignment(refreshed)
