"""
Policy Engine — legacy compatibility wrapper.

The old PolicyEngine (based on ScopeMembership/ScopeRole/Action enums) has been
replaced by the new dual-realm permission engine in permission_engine.py.

This module is kept for backward compatibility with any code that still references it.
New code should use app.services.permission_engine directly.
"""

import uuid
from dataclasses import dataclass

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditLog, Employee


@dataclass
class PolicyDecision:
    """Result of a policy evaluation."""
    allowed: bool
    reason: str


class PolicyEngine:
    """
    Legacy wrapper — delegates to permission_engine for actual checks.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_document_access(
        self,
        user: Employee,
        source,
        action: str = "read",
    ) -> PolicyDecision:
        """Check document access using the new permission engine."""
        from app.services.permission_engine import can_access_document
        allowed = await can_access_document(self.db, user, source, action)
        return PolicyDecision(
            allowed=allowed,
            reason="Allowed" if allowed else "Access denied",
        )

    async def check_workspace_access(
        self,
        user: Employee,
        workspace_id: uuid.UUID,
    ) -> PolicyDecision:
        """Check workspace access using the new permission engine."""
        from app.services.permission_engine import can_access_workspace
        allowed = await can_access_workspace(self.db, user, workspace_id)
        return PolicyDecision(
            allowed=allowed,
            reason="Allowed" if allowed else "Not a workspace member",
        )

    async def _audit(
        self,
        principal_id: uuid.UUID,
        action: str,
        resource_type: str,
        resource_id: str,
        decision: PolicyDecision,
    ) -> None:
        """Write an audit log entry (append-only)."""
        if not resource_type:
            return

        try:
            entry = AuditLog(
                principal_id=principal_id,
                principal_type="human",
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                decision="allow" if decision.allowed else "deny",
                reason=decision.reason,
            )
            self.db.add(entry)
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
