"""Sprint router (Phase 2 Agile).

Surfaces the ``sprint_service`` lifecycle as REST endpoints under two
URL groups:

* ``/api/task-projects/{project_id}/sprints`` — collection ops (create / list)
* ``/api/sprints/{sprint_id}`` — item ops (get / patch / start / close / cancel / delete)

Two prefix groups live in one ``APIRouter`` because they are the same
domain (sprint lifecycle) and splitting them across two routers would
fragment registration without buying anything.

Feature gating: every write endpoint short-circuits with
``403 FEATURE_DISABLED`` when ``settings.FEATURE_AGILE_PHASE_2`` is False.
Reads stay open so a partial-rollout (UI rendered but flag off) does not
turn into a wall of 403s in observability.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.database.models import Employee, Sprint
from app.schemas.tasks import SprintCreate, SprintOut, SprintUpdate
from app.services.auth_service import require_permission
from app.services.sprint_service import (
    INVALID_DATE_RANGE_ERROR_CODE,
    SPRINT_CLOSED_ERROR_CODE,
    ActiveSprintExistsError,
    cancel_sprint,
    close_sprint,
    create_sprint,
    delete_sprint,
    get_sprint,
    list_sprints,
    start_sprint,
    update_sprint,
)
from app.services.task_constants import FEATURE_DISABLED_ERROR_CODE

router = APIRouter(tags=["sprints"])


def _require_phase_2_enabled() -> None:
    """Short-circuit with 403 FEATURE_DISABLED when Phase 2 is off."""
    if not settings.FEATURE_AGILE_PHASE_2:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": FEATURE_DISABLED_ERROR_CODE},
        )


async def _call_service(coro: Any) -> Any:
    """Translate sprint-service domain errors into HTTP responses.

    Mirrors the ``tasks.py`` ``_call_service`` translator so the surface
    contract stays uniform. ``ValueError`` carrying one of the stable error
    codes maps to a 409 with a structured payload; bare ``ValueError`` falls
    back to 400/404 depending on the message.
    """
    try:
        return await coro
    except ActiveSprintExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": exc.code,
                "task_project_id": str(exc.task_project_id),
            },
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        message = str(exc)
        if message == INVALID_DATE_RANGE_ERROR_CODE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": INVALID_DATE_RANGE_ERROR_CODE},
            ) from exc
        if message == SPRINT_CLOSED_ERROR_CODE:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": SPRINT_CLOSED_ERROR_CODE},
            ) from exc
        if "not found" in message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=message
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=message
        ) from exc


@router.post(
    "/task-projects/{project_id}/sprints",
    response_model=SprintOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_sprint_endpoint(
    project_id: uuid.UUID,
    body: SprintCreate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> Sprint:
    """Create a sprint (default ``status='planned'``)."""
    _require_phase_2_enabled()
    sprint = await _call_service(create_sprint(db, project_id, body, actor=user))
    await db.commit()
    await db.refresh(sprint)
    return sprint


@router.get(
    "/task-projects/{project_id}/sprints",
    response_model=list[SprintOut],
)
async def list_sprints_endpoint(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> list[Sprint]:
    """List sprints for a project, oldest first."""
    return await list_sprints(db, project_id)


@router.get("/sprints/{sprint_id}", response_model=SprintOut)
async def get_sprint_endpoint(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> Sprint:
    """Fetch one sprint by id."""
    return await _call_service(get_sprint(db, sprint_id))


@router.patch("/sprints/{sprint_id}", response_model=SprintOut)
async def update_sprint_endpoint(
    sprint_id: uuid.UUID,
    body: SprintUpdate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> Sprint:
    """Patch mutable sprint fields."""
    _require_phase_2_enabled()
    sprint = await _call_service(update_sprint(db, sprint_id, body, actor=user))
    await db.commit()
    await db.refresh(sprint)
    return sprint


@router.post("/sprints/{sprint_id}/start", response_model=SprintOut)
async def start_sprint_endpoint(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> Sprint:
    """Transition a sprint to ``active``."""
    _require_phase_2_enabled()
    sprint = await _call_service(start_sprint(db, sprint_id, actor=user))
    await db.commit()
    await db.refresh(sprint)
    return sprint


@router.post("/sprints/{sprint_id}/close")
async def close_sprint_endpoint(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> dict[str, Any]:
    """Close a sprint and unlink still-open tasks.

    Returns the closed sprint plus an optional Phase 5 governance advisory:
    ``{"id": ..., ..., "advisory": {"code": ..., "permission": ...}}`` when
    the actor lacks ``agile.sprint.close``. The advisory is omitted entirely
    when no governance check fired so existing UI consumers keep parsing
    the same shape.
    """
    _require_phase_2_enabled()
    sprint, advisory = await _call_service(close_sprint(db, sprint_id, actor=user))
    await db.commit()
    await db.refresh(sprint)
    payload: dict[str, Any] = SprintOut.model_validate(sprint).model_dump(mode="json")
    if advisory is not None:
        payload["advisory"] = advisory
    return payload


@router.post("/sprints/{sprint_id}/cancel", response_model=SprintOut)
async def cancel_sprint_endpoint(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> Sprint:
    """Cancel a sprint without touching linked tasks."""
    _require_phase_2_enabled()
    sprint = await _call_service(cancel_sprint(db, sprint_id, actor=user))
    await db.commit()
    await db.refresh(sprint)
    return sprint


@router.delete("/sprints/{sprint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sprint_endpoint(
    sprint_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> None:
    """Delete a sprint, unlinking referencing tasks first."""
    _require_phase_2_enabled()
    await _call_service(delete_sprint(db, sprint_id, actor=user))
    await db.commit()
