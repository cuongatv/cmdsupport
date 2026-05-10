"""
Audit log router — admin-only view of access decisions.
Implements audit_read capability from AccessControl.md.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import AuditLog, Employee
from app.services.auth_service import require_permission

router = APIRouter(prefix="/audit", tags=["audit"])


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------

class AuditEntryOut(BaseModel):
    id: str
    timestamp: str
    principal_id: str
    principal_type: str
    principal_name: Optional[str] = None
    principal_email: Optional[str] = None
    action: str
    resource_type: str
    resource_id: str
    decision: str
    reason: Optional[str] = None


class AuditListResponse(BaseModel):
    items: list[AuditEntryOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/log", response_model=AuditListResponse)
async def get_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    principal_id: Optional[str] = None,
    action: Optional[str] = None,
    decision: Optional[str] = None,
    resource_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("audit.read"),
):
    """
    Query audit log with pagination and filters.
    Admin-only endpoint.
    """
    stmt = select(AuditLog)

    if principal_id:
        stmt = stmt.where(AuditLog.principal_id == uuid.UUID(principal_id))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if decision:
        stmt = stmt.where(AuditLog.decision == decision)
    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    # Paginate
    stmt = (
        stmt
        .order_by(desc(AuditLog.timestamp))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    
    # Join with Employee to get names/emails
    join_stmt = (
        select(AuditLog, Employee)
        .select_from(stmt.subquery().alias("log_sub"))
        .join(AuditLog, AuditLog.id == text("log_sub.id"))
        .outerjoin(Employee, AuditLog.principal_id == Employee.id)
        .order_by(desc(AuditLog.timestamp))
    )
    
    result = await db.execute(join_stmt)
    rows = result.all()

    return AuditListResponse(
        items=[
            AuditEntryOut(
                id=str(e.id),
                timestamp=e.timestamp.isoformat(),
                principal_id=str(e.principal_id),
                principal_type=e.principal_type,
                principal_name=emp.name if emp else None,
                principal_email=emp.email if emp else None,
                action=e.action,
                resource_type=e.resource_type,
                resource_id=e.resource_id,
                decision=e.decision,
                reason=e.reason,
            )
            for e, emp in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
