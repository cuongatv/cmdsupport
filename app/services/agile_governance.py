"""Phase 5 Agile governance — Stage A advisory helpers.

Stage A semantics (current): when an actor lacks the relevant ``agile.*``
permission, the helper writes a ``permission_denied_advisory`` audit row and
returns response metadata. The mutation itself is NEVER blocked — the
advisory only adds observability + a UI hint so operators can grant the
right roles before Stage B starts enforcing.

Stage B (future, not in T20): the same permission strings flip to a hard
``HTTPException`` gate. Centralising the helper now means Stage B only
touches this file plus the routers that surface 403s.

All helpers are no-ops when ``settings.FEATURE_AGILE_PHASE_5`` is False so
the existing Phase 1–4 contracts stay identical for deployments that have
not yet flipped the flag.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Employee
from app.services.audit_service import log_audit

# Stable, ASCII-only audit + response identifiers. Kept here (not in
# ``task_constants``) because they are governance-domain-specific and not
# shared with the existing Phase 1–4 advisory surfaces.
PERMISSION_ADVISORY_AUDIT_ACTION: str = "permission_denied_advisory"
PERMISSION_ADVISORY_CODE: str = "PERMISSION_DENIED_ADVISORY"


# Permission strings — single source is ``app/services/permissions.py``. The
# mutation services import them from here so the literal lives next to its
# narrative; the registry import keeps the catalogue authoritative.
PERMISSION_AGILE_SPRINT_CLOSE: str = "agile.sprint.close"
PERMISSION_AGILE_WIP_OVERRIDE: str = "agile.wip.override"
PERMISSION_AGILE_DOD_BYPASS: str = "agile.dod.bypass"


async def maybe_record_permission_advisory(
    db: AsyncSession,
    *,
    actor: Employee,
    permission: str,
    resource_type: str,
    resource_id: uuid.UUID | str,
) -> Optional[dict[str, str]]:
    """Record a Stage A advisory when ``actor`` lacks ``permission``.

    Returns the advisory metadata dict ``{"code", "permission"}`` when the
    audit row is written, or ``None`` when the check is skipped (Phase 5
    flag is off or actor already holds the permission). The caller forwards
    the dict to the HTTP response so the UI can render a non-blocking warn.

    The audit row is written via :func:`app.services.audit_service.log_audit`
    so the flush still belongs to the caller. ``reason`` carries the literal
    permission string so the audit log + dashboards can pivot on it without
    parsing free-form text.
    """
    if not settings.FEATURE_AGILE_PHASE_5:
        return None

    # Lazy import to avoid a circular dependency: permission_engine pulls
    # `permissions.ALL_PERMISSIONS` which in turn lives in this layer.
    from app.services.permission_engine import _get_user_permissions

    effective = _get_user_permissions(actor)
    if permission in effective:
        return None

    await log_audit(
        db,
        actor,
        PERMISSION_ADVISORY_AUDIT_ACTION,
        resource_type,
        str(resource_id),
        reason=permission,
    )
    return {"code": PERMISSION_ADVISORY_CODE, "permission": permission}


def dod_checklist_has_incomplete_items(checklist: object) -> bool:
    """Return True when ``checklist`` carries at least one un-done item.

    The DoD snapshot shape from Phase 2 stores entries as dicts with a
    ``done: bool`` flag (see ``task_service.create_task``). Items without a
    ``done`` key are treated as incomplete so partially-typed legacy rows
    still trip the advisory rather than silently passing. Non-list
    payloads (``None`` / empty) short-circuit to False — there is nothing
    to bypass.
    """
    if not isinstance(checklist, list) or not checklist:
        return False
    for item in checklist:
        if isinstance(item, dict):
            if not item.get("done", False):
                return True
        else:
            # Treat malformed entries (e.g. a bare string) as incomplete so
            # the advisory still fires; flagging here is preferable to a
            # silent pass that could mask a real DoD violation.
            return True
    return False
