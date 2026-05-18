"""Admin dashboard aggregation router skeleton."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.database.models import Employee
from app.schemas.tasks import AdminDashboardFlowSummaryResponse
from app.services.auth_service import require_permission

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])


def _empty_flow_summary(*, feature_enabled: bool) -> AdminDashboardFlowSummaryResponse:
    return AdminDashboardFlowSummaryResponse(
        feature_enabled=feature_enabled,
        as_of=datetime.now(timezone.utc),
        approximation_used=False,
        scoped_project_count=0,
        wip_count=0,
        blocked_count=0,
        aging_count=0,
        throughput_count=0,
        cycle_time_p50=0.0,
        lead_time_p50=0.0,
    )


@router.get(
    "/flow-summary",
    response_model=AdminDashboardFlowSummaryResponse,
)
async def get_admin_dashboard_flow_summary(
    start_date: date,
    end_date: date,
    department_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    sprint_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("task:read"),
) -> AdminDashboardFlowSummaryResponse:
    """Return the Agile Flow Command Center dashboard aggregation contract."""
    if not settings.FEATURE_AGILE_PHASE_5:
        return _empty_flow_summary(feature_enabled=False)

    _ = (start_date, end_date, department_id, workspace_id, project_id, sprint_id, db)
    return _empty_flow_summary(feature_enabled=True)
