"""Idea Submissions router.

* ``POST /api/public/ideas``                — unauthenticated submission
* ``POST /api/public/ideas/{id}/images``    — unauthenticated image upload
                                              (only allowed within a short
                                              window after creation — caller
                                              must know the freshly-issued id)
* ``GET  /api/admin/ideas``                 — admin list (auth)
* ``GET  /api/admin/ideas/{id}``            — admin detail (auth)
* ``PATCH /api/admin/ideas/{id}``           — admin update status/notes
* ``DELETE /api/admin/ideas/{id}``          — admin delete (auth)

Public endpoints carry a light rate-limit hint via in-memory counters,
but real rate-limiting is left to nginx / reverse-proxy in production.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee
from app.schemas.idea_submissions import (
    CATEGORY_VALUES,
    STATUS_VALUES,
    IdeaImageOut,
    IdeaSubmissionCreate,
    IdeaSubmissionListOut,
    IdeaSubmissionOut,
    IdeaSubmissionPublicOut,
    IdeaSubmissionUpdate,
)
from app.services import idea_submission_service as svc
from app.services.audit_service import log_audit
from app.services.auth_service import require_admin

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_admin_out(submission, include_images: bool = True) -> IdeaSubmissionOut:
    images_out: list[IdeaImageOut] = []
    if include_images:
        for img in submission.images:
            images_out.append(
                IdeaImageOut(
                    id=img.id,
                    file_name=img.file_name,
                    content_type=img.content_type,
                    size_bytes=img.size_bytes,
                    url=svc.build_image_url(img),
                )
            )
    return IdeaSubmissionOut(
        id=submission.id,
        contributor_name=submission.contributor_name,
        contributor_phone=submission.contributor_phone,
        contributor_email=submission.contributor_email,
        contributor_department=submission.contributor_department,
        title=submission.title,
        description=submission.description,
        current_pain=submission.current_pain,
        expected_benefit=submission.expected_benefit,
        reference_system=submission.reference_system,
        category=submission.category,  # type: ignore[arg-type]
        status=submission.status,  # type: ignore[arg-type]
        admin_notes=submission.admin_notes,
        created_at=submission.created_at,
        updated_at=submission.updated_at,
        images=images_out,
    )


def _client_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    if request.client and request.client.host:
        return request.client.host[:64]
    return None


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/public/ideas",
    response_model=IdeaSubmissionPublicOut,
    status_code=201,
)
async def submit_idea(
    payload: IdeaSubmissionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — anyone can submit an idea."""
    try:
        submission = await svc.create_submission(
            db,
            contributor_name=payload.contributor_name,
            description=payload.description,
            contributor_phone=payload.contributor_phone,
            contributor_email=payload.contributor_email,
            contributor_department=payload.contributor_department,
            title=payload.title,
            current_pain=payload.current_pain,
            expected_benefit=payload.expected_benefit,
            reference_system=payload.reference_system,
            category=payload.category,
            submitter_ip=_client_ip(request),
            submitter_user_agent=(request.headers.get("user-agent") or "")[:500] or None,
        )
        await db.commit()
        logger.info(
            f"New idea submission {submission.id} from "
            f"{submission.contributor_name!r} ({payload.category})"
        )
        return IdeaSubmissionPublicOut(
            id=submission.id, created_at=submission.created_at
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to create idea submission: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Không thể lưu góp ý. Vui lòng thử lại.")


@router.post(
    "/public/ideas/{submission_id}/images",
    response_model=IdeaImageOut,
    status_code=201,
)
async def upload_idea_image(
    submission_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Attach an image to a freshly-submitted idea.

    Caller must already know the submission id (returned from POST
    /public/ideas) — there's no listing of submissions for public users.
    Storage caps and mime checks live in the service.
    """
    submission = await svc.get_submission(db, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Không tìm thấy góp ý.")

    data = await file.read()
    try:
        image = await svc.attach_image(
            db,
            submission,
            data=data,
            file_name=file.filename,
            content_type=file.content_type,
        )
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.exception(f"Failed to attach image to idea {submission_id}: {e}")
        raise HTTPException(status_code=500, detail="Không thể tải ảnh lên. Vui lòng thử lại.")

    await db.commit()
    return IdeaImageOut(
        id=image.id,
        file_name=image.file_name,
        content_type=image.content_type,
        size_bytes=image.size_bytes,
        url=svc.build_image_url(image),
    )


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------

@router.get("/admin/ideas", response_model=IdeaSubmissionListOut)
async def list_ideas(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(require_admin),
):
    if status and status not in STATUS_VALUES:
        raise HTTPException(400, "Invalid status filter")
    if category and category not in CATEGORY_VALUES:
        raise HTTPException(400, "Invalid category filter")

    rows, total = await svc.list_submissions(
        db,
        status=status,
        category=category,
        search=search,
        page=page,
        page_size=page_size,
    )
    return IdeaSubmissionListOut(
        items=[_to_admin_out(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/admin/ideas/{submission_id}", response_model=IdeaSubmissionOut)
async def get_idea(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(require_admin),
):
    submission = await svc.get_submission(db, submission_id)
    if not submission:
        raise HTTPException(404, "Không tìm thấy góp ý.")
    return _to_admin_out(submission)


@router.patch("/admin/ideas/{submission_id}", response_model=IdeaSubmissionOut)
async def update_idea(
    submission_id: uuid.UUID,
    payload: IdeaSubmissionUpdate,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(require_admin),
):
    submission = await svc.get_submission(db, submission_id)
    if not submission:
        raise HTTPException(404, "Không tìm thấy góp ý.")

    updated = await svc.update_submission(
        db,
        submission,
        status=payload.status,
        admin_notes=payload.admin_notes,
        category=payload.category,
    )
    parts = []
    if payload.status:
        parts.append(f"status={payload.status}")
    if payload.category:
        parts.append(f"category={payload.category}")
    if payload.admin_notes is not None:
        parts.append("admin_notes")
    await log_audit(
        db,
        user=user,
        action="idea.update",
        resource_type="idea_submission",
        resource_id=str(submission.id),
        reason=", ".join(parts) or None,
    )
    await db.commit()
    # Refresh images relation for response
    refreshed = await svc.get_submission(db, updated.id)
    assert refreshed is not None
    return _to_admin_out(refreshed)


@router.delete("/admin/ideas/{submission_id}")
async def delete_idea(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(require_admin),
):
    submission = await svc.get_submission(db, submission_id)
    if not submission:
        raise HTTPException(404, "Không tìm thấy góp ý.")
    await svc.delete_submission(db, submission)
    await log_audit(
        db,
        user=user,
        action="idea.delete",
        resource_type="idea_submission",
        resource_id=str(submission_id),
    )
    await db.commit()
    return {"deleted": True}
