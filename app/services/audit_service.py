from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditLog, Employee


async def log_audit(
    db: AsyncSession,
    user: Employee,
    action: str,
    resource_type: str,
    resource_id: str,
    decision: str = "ALLOW",
    reason: Optional[str] = None,
):
    """
    Log an action to the audit log.
    This should be called during sensitive mutations (Create/Update/Delete).
    Does NOT commit the session — the caller must commit.
    """
    entry = AuditLog(
        principal_id=user.id,
        principal_type="human",
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        decision=decision,
        reason=reason,
    )
    db.add(entry)
