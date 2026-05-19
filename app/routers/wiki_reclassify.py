"""
Wiki taxonomy reclassification router — admin-equivalent preview + apply.

Permission model:
  - Both endpoints require ``wiki:write:all`` (admin override applies automatically
    via ``require_permission``). No new permission row is introduced — this is the
    closest existing high-privilege constant for global wiki mutations.

The router is a thin HTTP layer over
:func:`app.services.wiki_reclassification_service.preview_reclassification` (T9)
and :func:`app.services.wiki_reclassification_service.apply_reclassification`
(T10). It does not classify, mutate page contents, or call the LLM directly.
"""

from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission
from app.services.wiki_reclassification_service import (
    apply_reclassification,
    preview_reclassification,
)

router = APIRouter()

DEFAULT_PREVIEW_LIMIT = 25
MAX_PREVIEW_LIMIT = 100


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------


class ReclassifyPreviewRequest(BaseModel):
    """Filters for the preview. At least one filter SHOULD be supplied; if none
    are provided the service falls back to ``scope_type='global'`` + no scope id,
    matching the T9 service default.
    """

    source_id: Optional[uuid.UUID] = None
    page_ids: Optional[list[uuid.UUID]] = Field(default=None, max_length=MAX_PREVIEW_LIMIT)
    scope_type: Literal["global", "workspace", "project"] = "global"
    scope_id: Optional[uuid.UUID] = None
    model_config: ConfigDict = ConfigDict(extra="forbid")

    limit: int = Field(default=DEFAULT_PREVIEW_LIMIT, ge=1)

    @field_validator("limit", mode="before")
    @classmethod
    def cap_limit(cls, value: object) -> object:
        if value is None:
            return DEFAULT_PREVIEW_LIMIT
        if isinstance(value, int) and value > MAX_PREVIEW_LIMIT:
            return MAX_PREVIEW_LIMIT
        return value


class ReclassifyApplyRequest(BaseModel):
    """Body for the apply endpoint.

    Callers may only submit the server-persisted ``preview_id``; the service
    loads the canonical preview payload and verifies ownership plus freshness.
    """

    model_config: ConfigDict = ConfigDict(extra="forbid")

    preview_id: uuid.UUID
    force_rule_linked_tier_change: bool = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/wiki/reclassify/preview")
async def reclassify_preview(
    body: ReclassifyPreviewRequest,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("wiki:write:all"),
) -> dict:
    """Dry-run reclassification — returns and persists a bounded preview diff.

    Preview scope is always bounded: ``limit`` defaults to 25 and is capped at
    ``MAX_PREVIEW_LIMIT`` (100), and explicit ``page_ids`` cannot exceed 100.
    The canonical preview payload is stored server-side for the apply step.
    """
    # T9 expects ``scope_type`` to be ``"global"`` or ``"workspace"``. Accept the
    # legacy ``"project"`` alias from older clients by collapsing it to
    # ``"workspace"`` here since both map to the same WikiPage.scope_type row
    # values handled by the service.
    scope_type = "workspace" if body.scope_type == "project" else body.scope_type
    try:
        result = await preview_reclassification(
            db,
            source_id=body.source_id,
            page_ids=body.page_ids,
            scope_type=scope_type,
            scope_id=body.scope_id,
            limit=body.limit,
            actor=user,
        )
        await db.commit()
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/wiki/reclassify/apply")
async def reclassify_apply(
    body: ReclassifyApplyRequest,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("wiki:write:all"),
) -> dict:
    """Apply taxonomy-only updates from a previously computed preview (T10).

    Rule-linked tier changes are skipped unless ``force_rule_linked_tier_change``
    is true. ``needs_review`` pages are also skipped under the same flag. All
    writes go through ``wiki_service.apply_update`` so revisions, wikilinks,
    source ids, and consulting rule links keep their normal lifecycle.
    """
    try:
        result = await apply_reclassification(
            db,
            preview_id=body.preview_id,
            force_rule_linked_tier_change=body.force_rule_linked_tier_change,
            actor=user,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    preview_id = result.get("preview_id") or ""
    applied_count = result.get("applied_count") or 0
    await log_audit(
        db,
        user,
        "update",
        "wiki_page",
        str(preview_id),
        reason=f"reclassify_apply: applied={applied_count}",
    )
    await db.commit()
    return result
