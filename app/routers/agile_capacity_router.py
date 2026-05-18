"""Agile capacity router (Phase 3).

Exposes the squad-overview surface for the Phase 3 capacity dashboard:

* ``GET /api/departments/{department_id}/agile/capacity`` — per-member
  capacity rows for an individual squad.

Lives in its own router (not piggy-backed on ``tasks.py`` or ``departments.py``)
for the same reason the sprint router does: a Phase-N feature gets its own
file so the registration, gate, and access-check surface stay greppable.

Feature gating: the endpoint short-circuits with ``403 FEATURE_DISABLED`` when
``settings.FEATURE_AGILE_PHASE_3`` is False. Department access is enforced via
``require_permission("org:departments:read")`` — the same permission the
``GET /departments/{id}/members`` endpoint uses, since the capacity view is a
read-only projection of the membership roster.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.database.models import Department, Employee
from app.schemas.tasks import SquadMemberCapacityOut
from app.services.auth_service import require_permission
from app.services.task_constants import FEATURE_DISABLED_ERROR_CODE
from app.services.task_dashboard_service import get_squad_capacity

router = APIRouter(tags=["agile-capacity"])


def _require_phase_3_enabled() -> None:
    """Short-circuit with 403 FEATURE_DISABLED when Phase 3 is off.

    Mirrors the Phase 1/2 helpers (``_reject_wip_fields_when_phase_1_disabled``
    in ``tasks.py`` and ``_require_phase_2_enabled`` in ``sprint_router.py``)
    so the contract stays uniform across phases.
    """
    if not settings.FEATURE_AGILE_PHASE_3:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": FEATURE_DISABLED_ERROR_CODE},
        )


@router.get(
    "/departments/{department_id}/agile/capacity",
    response_model=list[SquadMemberCapacityOut],
)
async def get_department_agile_capacity(
    department_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:departments:read"),
) -> list[SquadMemberCapacityOut]:
    """Return one capacity row per active membership in ``department_id``.

    Multi-squad users yield independent rows from *other* squads' calls; this
    endpoint never aggregates across squads — see the
    ``SquadMemberCapacity`` docstring for the rationale.
    """
    _require_phase_3_enabled()

    department = await db.get(Department, department_id)
    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="department not found",
        )

    rows = await get_squad_capacity(db, department_id)
    return [SquadMemberCapacityOut.model_validate(row) for row in rows]
