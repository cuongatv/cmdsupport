"""Agile Phase 5 flow metrics router."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.database.models import Employee, TaskFlowSnapshot
from app.schemas.tasks import TaskFlowSnapshotOut, ThroughputOut
from app.services.auth_service import require_permission
from app.services.task_constants import FEATURE_DISABLED_ERROR_CODE
from app.services.task_flow_service import (
    capture_flow_snapshot,
    get_flow_metrics,
    get_throughput,
)

router = APIRouter(tags=["flow-metrics"])


def _require_phase_5_enabled() -> None:
    """Short-circuit with 403 FEATURE_DISABLED when Phase 5 is off."""
    if not settings.FEATURE_AGILE_PHASE_5:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": FEATURE_DISABLED_ERROR_CODE},
        )


async def _call_service(coro: Any) -> Any:
    try:
        return await coro
    except ValueError as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=message
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=message
        ) from exc


@router.get(
    "/task-projects/{project_id}/flow-metrics",
    response_model=list[TaskFlowSnapshotOut],
)
async def get_project_flow_metrics(
    project_id: uuid.UUID,
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("task:read"),
) -> list[TaskFlowSnapshot]:
    """Return Phase 5 flow snapshots for ``project_id`` in a date range."""
    _require_phase_5_enabled()
    return await _call_service(
        get_flow_metrics(db, project_id, start_date=start_date, end_date=end_date)
    )


@router.get(
    "/task-projects/{project_id}/throughput",
    response_model=ThroughputOut,
)
async def get_project_throughput(
    project_id: uuid.UUID,
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("task:read"),
) -> dict[str, int]:
    """Return completed task/story-point counts for a date range."""
    _require_phase_5_enabled()
    return await _call_service(
        get_throughput(db, project_id, start_date=start_date, end_date=end_date)
    )


@router.post(
    "/task-projects/{project_id}/flow-metrics/snapshot",
    response_model=list[TaskFlowSnapshotOut],
)
async def capture_project_flow_snapshot(
    project_id: uuid.UUID,
    response: Response,
    snapshot_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("task_project:manage"),
) -> list[TaskFlowSnapshot]:
    """Capture an immediate Phase 5 flow snapshot for ``project_id``."""
    _require_phase_5_enabled()
    snapshots = await _call_service(
        capture_flow_snapshot(db, project_id, snapshot_date=snapshot_date)
    )
    await db.commit()
    for snapshot in snapshots:
        await db.refresh(snapshot)
    response.status_code = status.HTTP_200_OK if snapshots else status.HTTP_201_CREATED
    return snapshots
