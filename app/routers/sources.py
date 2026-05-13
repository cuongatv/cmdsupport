"""Sources router — CRUD + upload + arq ingestion pipeline (compiles into wiki).

Permission model v2:
  - doc:read:own_dept → only own department + global docs
  - doc:read:all → all docs
  - Upload creates source_departments M2M entries
"""

import uuid
from typing import Optional

from arq.connections import ArqRedis, create_pool
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import delete as sql_delete
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.database.models import (
    Employee,
    ScopeType,
    Source,
    SourceChunkExtract,
    SourceCompilationPlan,
    SourceCompilationPlanRevision,
    SourceDepartment,
    WikiPage,
)
from app.database.repository import Repository
from app.services.audit_service import log_audit
from app.services.auth_service import (
    get_current_user,
    require_permission,
)
from app.services.permission_engine import (
    _get_user_permissions,
    get_scope_level,
)

router = APIRouter()

_arq_pool: Optional[ArqRedis] = None


async def get_arq_pool() -> ArqRedis:
    """Lazy-init arq Redis connection pool."""
    global _arq_pool
    if _arq_pool is None:
        from app.worker import _get_redis_settings
        _arq_pool = await create_pool(_get_redis_settings())
    return _arq_pool


class SourceResponse(BaseModel):
    id: uuid.UUID
    title: Optional[str]
    source_type: Optional[str]
    file_name: Optional[str]
    url: Optional[str]
    status: str
    error_message: Optional[str] = None
    progress: int = 0
    progress_message: Optional[str] = None
    job_id: Optional[str] = None
    page_count: int = 0
    wiki_page_count: int = 0
    knowledge_type_id: Optional[uuid.UUID] = None
    knowledge_type_name: Optional[str] = None
    knowledge_type_color: Optional[str] = None
    # Multi-department (v2)
    department_ids: list[str] = []
    department_names: list[str] = []
    contributed_by_employee_id: Optional[uuid.UUID] = None
    contributed_by_name: Optional[str] = None
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None
    pipeline_strategy: Optional[str] = None
    pipeline_phase: Optional[str] = None
    ingestion_pipeline: str = "legacy"
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class SourceDetail(SourceResponse):
    full_text: Optional[str] = None
    outline: Optional[list] = None
    download_url: Optional[str] = None


class SourceCreateURL(BaseModel):
    url: str
    title: Optional[str] = None
    knowledge_type_id: Optional[uuid.UUID] = None
    department_ids: list[uuid.UUID] = []
    ingestion_pipeline: Optional[str] = None


class PlanApproveRequest(BaseModel):
    note: Optional[str] = None
    modified_plan: Optional[dict] = None


class PlanRejectRequest(BaseModel):
    note: Optional[str] = None


class PlanReviseRequest(BaseModel):
    feedback: str


class SourceUpdate(BaseModel):
    title: Optional[str] = None
    knowledge_type_id: Optional[uuid.UUID] = None
    department_ids: Optional[list[uuid.UUID]] = None
    scope_type: Optional[str] = None
    scope_id: Optional[uuid.UUID] = None


async def _wiki_page_count(session: AsyncSession, source_id: uuid.UUID) -> int:
    """How many wiki pages reference this source in their source_ids array."""
    stmt = select(func.count()).select_from(WikiPage).where(WikiPage.source_ids.any(source_id))
    return (await session.execute(stmt)).scalar_one()


def _to_response(source: Source, wiki_page_count: int = 0) -> SourceResponse:
    # Extract departments from M2M relationship
    dept_ids = []
    dept_names = []
    if hasattr(source, 'departments') and source.departments:
        for sd in source.departments:
            dept_ids.append(str(sd.department_id))
            if hasattr(sd, 'department') and sd.department:
                dept_names.append(sd.department.name)

    return SourceResponse(
        id=source.id,
        title=source.title,
        source_type=source.source_type,
        file_name=source.file_name,
        url=source.url,
        status=source.status,
        error_message=source.error_message,
        progress=source.progress,
        progress_message=source.progress_message,
        job_id=source.job_id,
        page_count=len(source.page_offsets or []),
        wiki_page_count=wiki_page_count,
        knowledge_type_id=source.knowledge_type_id,
        knowledge_type_name=source.knowledge_type.name if source.knowledge_type else None,
        knowledge_type_color=source.knowledge_type.color if source.knowledge_type else None,
        department_ids=dept_ids,
        department_names=dept_names,
        contributed_by_employee_id=source.contributed_by_employee_id,
        contributed_by_name=source.contributor.name if source.contributor else None,
        scope_type=source.scope_type or "global",
        scope_id=source.scope_id,
        pipeline_strategy=source.pipeline_strategy,
        pipeline_phase=source.pipeline_phase,
        ingestion_pipeline=(source.metadata_ or {}).get("ingestion_pipeline", "legacy"),
        created_at=source.created_at.isoformat(),
        updated_at=source.updated_at.isoformat(),
    )


def _source_load_options():
    """Common selectinload options for Source queries."""
    return [
        selectinload(Source.knowledge_type),
        selectinload(Source.departments).selectinload(SourceDepartment.department),
        selectinload(Source.contributor),
    ]


@router.get("/sources")
async def list_sources(
    knowledge_type_id: Optional[uuid.UUID] = Query(None),
    department_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """List sources with scoped filtering based on user permissions."""
    # Check user has at least some doc:read permission
    perms = _get_user_permissions(user)
    if user.role != "admin" and not any(p.startswith("doc:read:") for p in perms):
        raise HTTPException(403, "Permission required: doc:read")

    base = select(Source).options(*_source_load_options())
    count_base = select(func.count(Source.id))

    # --- Scope filtering ---
    scope_level = "all" if user.role == "admin" else get_scope_level(list(perms), "doc", "read")

    if scope_level == "own_dept":
        # Only show: global docs (no departments) OR docs in user's department
        dept_filter = or_(
            # Source has no departments → global
            ~exists(
                select(SourceDepartment.source_id)
                .where(SourceDepartment.source_id == Source.id)
            ),
            # Source has user's department
            exists(
                select(SourceDepartment.source_id)
                .where(
                    SourceDepartment.source_id == Source.id,
                    SourceDepartment.department_id == user.department_id,
                )
            ),
        )
        base = base.where(dept_filter)
        count_base = count_base.where(dept_filter)
    elif scope_level is None:
        # No doc:read permission at all
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 1}

    # --- Additional filters ---
    if knowledge_type_id:
        base = base.where(Source.knowledge_type_id == knowledge_type_id)
        count_base = count_base.where(Source.knowledge_type_id == knowledge_type_id)
    if department_id:
        dept_exists = exists(
            select(SourceDepartment.source_id)
            .where(
                SourceDepartment.source_id == Source.id,
                SourceDepartment.department_id == department_id,
            )
        )
        base = base.where(dept_exists)
        count_base = count_base.where(dept_exists)
    if status:
        base = base.where(Source.status == status)
        count_base = count_base.where(Source.status == status)
    if search:
        like = f"%{search}%"
        base = base.where(Source.title.ilike(like) | Source.file_name.ilike(like))
        count_base = count_base.where(Source.title.ilike(like) | Source.file_name.ilike(like))

    total = (await db.execute(count_base)).scalar() or 0

    offset = (max(page, 1) - 1) * page_size
    stmt = base.order_by(Source.created_at.desc()).offset(offset).limit(page_size)
    sources = (await db.execute(stmt)).scalars().all()

    items: list[SourceResponse] = []
    for s in sources:
        items.append(_to_response(s, await _wiki_page_count(db, s.id)))

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, -(-total // page_size)),
    }


@router.get("/sources/{source_id}")
async def get_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source_id)
    )).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Check access using permission engine
    from app.services.permission_engine import can_access_document
    if not await can_access_document(db, user, source, "read"):
        raise HTTPException(403, "Access denied")

    wiki_count = await _wiki_page_count(db, source_id)
    download_url = None
    if source.minio_key:
        try:
            from app.services.storage_service import storage_service
            download_url = storage_service.get_download_url(
                source.minio_key,
                expires_seconds=3600,
            )
        except Exception:
            pass

    base = _to_response(source, wiki_count)
    return SourceDetail(
        **base.model_dump(),
        full_text=source.full_text,
        outline=source.outline_json,
        download_url=download_url,
    )


@router.get("/sources/{source_id}/progress")
async def get_source_progress(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("doc:read"),
):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    wiki_count = await _wiki_page_count(db, source_id)
    return {
        "id": str(source.id),
        "status": source.status,
        "progress": source.progress,
        "progress_message": source.progress_message,
        "page_count": len(source.page_offsets or []),
        "wiki_page_count": wiki_count,
        "pipeline_strategy": source.pipeline_strategy,
        "pipeline_phase": source.pipeline_phase,
        "ingestion_pipeline": (source.metadata_ or {}).get("ingestion_pipeline", "legacy"),
    }


@router.post("/sources/upload", response_model=SourceResponse)
async def upload_source(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    knowledge_type_id: Optional[str] = Form(None),
    department_ids: Optional[str] = Form(None),  # comma-separated UUIDs
    ingestion_pipeline: Optional[str] = Form(None),
    scope_type: Optional[str] = Form(None),
    scope_id: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:create"),
):
    from app.ai.mrp.pipeline import normalize_ingestion_pipeline, set_ingestion_pipeline

    file_data = await file.read()
    file_name = file.filename or "unknown"
    try:
        selected_pipeline = normalize_ingestion_pipeline(ingestion_pipeline)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    # Parse department_ids
    dept_uuids: list[uuid.UUID] = []
    if department_ids:
        for d in department_ids.split(","):
            d = d.strip()
            if d:
                try:
                    dept_uuids.append(uuid.UUID(d))
                except ValueError:
                    raise HTTPException(400, f"Invalid department_id: {d}")

    # Scope validation: own_dept users can only assign their own department
    perms = _get_user_permissions(user)
    if user.role != "admin" and "doc:create:all" not in perms:
        # User only has doc:create:own_dept
        for did in dept_uuids:
            if did != user.department_id:
                raise HTTPException(403, "You can only assign documents to your own department")

    repo = Repository(db)
    source = Source(
        title=title or file.filename,
        source_type="file",
        file_name=file_name,
        file_size=len(file_data),
        status="pending",
        progress=0,
        progress_message="Queued for ingestion...",
        knowledge_type_id=uuid.UUID(knowledge_type_id) if knowledge_type_id else None,
        contributed_by_employee_id=user.id,
        scope_type=scope_type or ScopeType.GLOBAL.value,
        scope_id=uuid.UUID(scope_id) if scope_id else None,
    )
    set_ingestion_pipeline(source, selected_pipeline)
    source = await repo.create(source)
    await db.flush()

    # Create M2M department links
    for did in dept_uuids:
        db.add(SourceDepartment(source_id=source.id, department_id=did))
    await db.flush()

    await log_audit(db, user, "create", "source", str(source.id), reason=source.title)
    await db.commit()
    await db.refresh(source)

    # Upload to MinIO before enqueuing so the worker downloads from storage
    from app.services.kb_service import _guess_content_type
    from app.services.storage_service import storage_service
    minio_key = f"sources/{source.id}/original/{file_name}"
    storage_service.upload_file(
        object_name=minio_key,
        data=file_data,
        content_type=_guess_content_type(file_name),
    )
    source.minio_key = minio_key
    source.file_name = file_name
    await db.commit()

    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        "ingest_file_task", str(source.id),
    )
    source.job_id = job.job_id
    await db.commit()

    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source.id)
    )).scalar_one()

    logger.info(f"Enqueued ingestion job {job.job_id} for source {source.id}")
    return _to_response(source)


@router.post("/sources/url", response_model=SourceResponse)
async def add_url_source(
    req: SourceCreateURL,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:create"),
):
    from app.ai.mrp.pipeline import normalize_ingestion_pipeline, set_ingestion_pipeline

    try:
        selected_pipeline = normalize_ingestion_pipeline(req.ingestion_pipeline)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    repo = Repository(db)
    source = Source(
        title=req.title or req.url,
        source_type="url",
        url=req.url,
        status="pending",
        progress=0,
        progress_message="Queued for ingestion...",
        knowledge_type_id=req.knowledge_type_id,
        contributed_by_employee_id=user.id,
        scope_type=ScopeType.GLOBAL.value,
    )
    set_ingestion_pipeline(source, selected_pipeline)
    source = await repo.create(source)
    await db.flush()

    # Create M2M department links
    for did in req.department_ids:
        db.add(SourceDepartment(source_id=source.id, department_id=did))
    await db.flush()

    await log_audit(db, user, "create", "source", str(source.id), reason=source.title)
    await db.commit()
    await db.refresh(source)

    pool = await get_arq_pool()
    job = await pool.enqueue_job("ingest_url_task", str(source.id))
    source.job_id = job.job_id
    await db.commit()

    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source.id)
    )).scalar_one()

    logger.info(f"Enqueued URL ingestion job {job.job_id} for source {source.id}")
    return _to_response(source)


@router.patch("/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("doc:edit"),
):
    source = await db.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if body.title is not None:
        source.title = body.title
    if body.knowledge_type_id is not None:
        source.knowledge_type_id = body.knowledge_type_id
    if body.scope_type is not None:
        source.scope_type = body.scope_type
        source.scope_id = body.scope_id

    # Update department M2M
    if body.department_ids is not None:
        # Delete existing
        await db.execute(
            sql_delete(SourceDepartment).where(SourceDepartment.source_id == source_id)
        )
        # Insert new
        for did in body.department_ids:
            db.add(SourceDepartment(source_id=source_id, department_id=did))

    await log_audit(db, _user, "update", "source", str(source.id), reason=source.title)
    await db.flush()

    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source_id)
    )).scalar_one()
    return _to_response(source, await _wiki_page_count(db, source_id))


@router.post("/sources/{source_id}/recompile", response_model=SourceResponse)
async def recompile_source(
    source_id: uuid.UUID,
    force: bool = Query(False, description="If true, detach this source from existing wiki pages first"),
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("doc:edit"),
):
    """
    Re-run the wiki compiler for this source. Without `force`, the compiler
    merges new ops into the existing wiki state. With `force=True`, the
    source is first detached from all wiki pages (orphans deleted) so the
    wiki effectively starts fresh from this source's perspective.
    """
    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source_id)
    )).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.source_type == "url" and not source.url:
        raise HTTPException(status_code=400, detail="Source has no URL to recompile")
    if source.source_type == "file" and not source.minio_key:
        raise HTTPException(status_code=400, detail="Source file not found in storage")

    source.status = "pending"
    source.progress = 0
    source.progress_message = "Queued for recompile..."
    source.error_message = None

    pool = await get_arq_pool()
    if (source.metadata_ or {}).get("ingestion_pipeline") == "mrp":
        plan = (await db.execute(
            select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == source.id)
        )).scalar_one_or_none()
        if plan and plan.status == "approved":
            # Plan đã được duyệt nhưng REFINE/COMMIT chưa hoàn tất → tiếp tục
            # đường refine. Giữ nguyên pipeline_phase để run_refine_pipeline
            # biết bắt đầu từ đâu.
            job = await pool.enqueue_job("ingest_refine_task", str(source_id))
        else:
            # Mọi trường hợp khác (plan done/rejected/none, hoặc đang
            # pending_review) đều cần reset state để MAP+REDUCE chạy lại từ
            # đầu. Nếu không reset, run_mrp_pipeline sẽ thấy
            # pipeline_phase=commit và short-circuit, source kẹt mãi ở
            # processing 10%.
            source.pipeline_phase = None
            if plan:
                # Xoá plan + chunk extracts để pipeline tái dựng từ đầu.
                # Cascade FK xoá luôn revisions của plan này.
                await db.execute(
                    sql_delete(SourceChunkExtract).where(
                        SourceChunkExtract.source_id == source.id
                    )
                )
                await db.execute(
                    sql_delete(SourceCompilationPlan).where(
                        SourceCompilationPlan.source_id == source.id
                    )
                )
            job = await pool.enqueue_job("ingest_map_reduce_task", str(source_id))
    elif source.source_type == "url":
        job = await pool.enqueue_job("ingest_url_task", str(source_id))
    else:
        job = await pool.enqueue_job("reingest_file_task", str(source_id), force)

    await db.flush()

    source.job_id = job.job_id
    await db.commit()
    await db.refresh(source)

    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source_id)
    )).scalar_one()
    logger.info(f"Queued recompile job {job.job_id} for source {source_id} (force={force})")
    return _to_response(source)


async def _get_accessible_source(
    source_id: uuid.UUID,
    db: AsyncSession,
    user: Employee,
    action: str,
) -> Source:
    source = (await db.execute(
        select(Source)
        .options(*_source_load_options())
        .where(Source.id == source_id)
    )).scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    from app.services.permission_engine import can_access_document
    if not await can_access_document(db, user, source, action):
        raise HTTPException(403, "Access denied")
    return source


_INTERNAL_PLAN_KEYS = {"_claims", "_entities", "_concepts"}


def _public_plan(plan_json: Optional[dict]) -> dict:
    """Strip internal reducer keys from a compilation plan before returning."""
    if not plan_json:
        return {}
    return {key: value for key, value in plan_json.items() if key not in _INTERNAL_PLAN_KEYS}


def _serialize_revision(revision: SourceCompilationPlanRevision) -> dict:
    return {
        "id": str(revision.id),
        "feedback": revision.feedback,
        "status": revision.status,
        "base_version": revision.base_version,
        "requested_by": str(revision.requested_by) if revision.requested_by else None,
        "created_at": revision.created_at.isoformat() if revision.created_at else None,
        "completed_at": revision.completed_at.isoformat() if revision.completed_at else None,
        "error_message": revision.error_message,
    }


async def _load_plan_revisions(
    db: AsyncSession, plan_id: uuid.UUID
) -> list[SourceCompilationPlanRevision]:
    rows = (await db.execute(
        select(SourceCompilationPlanRevision)
        .where(SourceCompilationPlanRevision.plan_id == plan_id)
        .order_by(SourceCompilationPlanRevision.created_at.desc())
    )).scalars().all()
    return list(rows)


@router.get("/sources/{source_id}/plan")
async def get_mrp_plan(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    source = await _get_accessible_source(source_id, db, user, "read")
    plan = (await db.execute(
        select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == source.id)
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="MRP plan not found")
    revisions = await _load_plan_revisions(db, plan.id)
    return {
        "source_id": str(source.id),
        "plan_id": str(plan.id),
        "status": plan.status,
        "version": plan.version,
        "strategy": source.pipeline_strategy,
        "pipeline_phase": source.pipeline_phase,
        "plan": _public_plan(plan.plan_json or {}),
        "review_note": plan.review_note,
        "reviewed_by": str(plan.reviewed_by) if plan.reviewed_by else None,
        "reviewed_at": plan.reviewed_at.isoformat() if plan.reviewed_at else None,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "revisions": [_serialize_revision(item) for item in revisions],
    }


@router.post("/sources/{source_id}/plan/approve")
async def approve_mrp_plan(
    source_id: uuid.UUID,
    body: Optional[PlanApproveRequest] = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:edit"),
):
    from datetime import datetime, timezone

    source = await _get_accessible_source(source_id, db, user, "edit")
    plan = (await db.execute(
        select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == source.id)
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="MRP plan not found")
    if plan.status == "revising":
        raise HTTPException(
            status_code=409,
            detail="Plan đang được tạo lại theo yêu cầu chỉnh sửa, vui lòng chờ.",
        )
    if plan.status not in {"pending_review", "approved"}:
        raise HTTPException(status_code=409, detail=f"Plan cannot be approved from status {plan.status}")

    if body and body.modified_plan is not None:
        merged = dict(body.modified_plan)
        for key in _INTERNAL_PLAN_KEYS:
            if key in (plan.plan_json or {}) and key not in merged:
                merged[key] = (plan.plan_json or {})[key]
        plan.plan_json = merged

    plan.status = "approved"
    plan.reviewed_by = user.id
    plan.review_note = body.note if body else None
    plan.reviewed_at = datetime.now(timezone.utc)

    source.status = "processing"
    source.pipeline_phase = "refine"
    source.progress_message = "Plan approved - compiling wiki pages..."
    source.error_message = None

    pool = await get_arq_pool()
    job = await pool.enqueue_job("ingest_refine_task", str(source.id))
    if job:
        source.job_id = job.job_id
    await log_audit(db, user, "approve", "source_mrp_plan", str(source.id), reason=source.title)
    await db.commit()
    return {"approved": True, "job_id": job.job_id if job else None}


@router.post("/sources/{source_id}/plan/revise")
async def revise_mrp_plan(
    source_id: uuid.UUID,
    body: PlanReviseRequest,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:edit"),
):
    """Yêu cầu chỉnh sửa kế hoạch MRP: chạy lại REDUCE planning với feedback."""
    from datetime import datetime, timezone

    feedback = (body.feedback or "").strip()
    if not feedback:
        raise HTTPException(status_code=400, detail="Feedback không được để trống.")
    if len(feedback) > 4000:
        raise HTTPException(status_code=400, detail="Feedback quá dài (tối đa 4000 ký tự).")

    source = await _get_accessible_source(source_id, db, user, "edit")
    # Lock plan row để chống click đôi (FOR UPDATE).
    plan = (await db.execute(
        select(SourceCompilationPlan)
        .where(SourceCompilationPlan.source_id == source.id)
        .with_for_update()
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="MRP plan not found")
    if plan.status not in {"pending_review", "rejected"}:
        raise HTTPException(
            status_code=409,
            detail=f"Không thể yêu cầu chỉnh sửa khi plan ở trạng thái {plan.status}.",
        )

    revision = SourceCompilationPlanRevision(
        plan_id=plan.id,
        source_id=source.id,
        requested_by=user.id,
        feedback=feedback,
        base_version=plan.version or 1,
        previous_plan_snapshot=plan.plan_json,
        status="requested",
    )
    db.add(revision)

    plan.status = "revising"
    source.status = "processing"
    source.pipeline_phase = "reduce"
    source.progress = 60
    source.progress_message = "Đang tạo lại kế hoạch theo phản hồi..."
    source.error_message = None
    await db.flush()

    pool = await get_arq_pool()
    job = await pool.enqueue_job(
        "revise_compilation_plan_task",
        str(source.id),
        str(revision.id),
    )
    if job:
        source.job_id = job.job_id

    await log_audit(
        db,
        user,
        "revise",
        "source_mrp_plan",
        str(source.id),
        reason=feedback[:200],
    )
    await db.commit()
    await db.refresh(revision)
    return {
        "revision_id": str(revision.id),
        "job_id": job.job_id if job else None,
        "plan_status": plan.status,
        "base_version": revision.base_version,
        "submitted_at": revision.created_at.isoformat() if revision.created_at else datetime.now(timezone.utc).isoformat(),
    }


@router.post("/sources/{source_id}/plan/reject")
async def reject_mrp_plan(
    source_id: uuid.UUID,
    body: PlanRejectRequest,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("doc:edit"),
):
    from datetime import datetime, timezone

    source = await _get_accessible_source(source_id, db, user, "edit")
    plan = (await db.execute(
        select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == source.id)
    )).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="MRP plan not found")
    if plan.status == "revising":
        raise HTTPException(
            status_code=409,
            detail="Plan đang được tạo lại theo yêu cầu chỉnh sửa, vui lòng chờ.",
        )
    if plan.status not in {"pending_review", "approved"}:
        raise HTTPException(status_code=409, detail=f"Plan cannot be rejected from status {plan.status}")

    plan.status = "rejected"
    plan.reviewed_by = user.id
    plan.review_note = body.note
    plan.reviewed_at = datetime.now(timezone.utc)
    source.status = "error"
    source.error_message = body.note or "MRP plan rejected"
    source.progress_message = "MRP plan rejected"
    await log_audit(db, user, "reject", "source_mrp_plan", str(source.id), reason=body.note)
    await db.commit()
    return {"rejected": True}


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("doc:delete"),
):
    repo = Repository(db)
    source = await repo.get_by_id(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    try:
        from app.services.storage_service import storage_service
        storage_service.delete_prefix(f"sources/{source_id}/")
    except Exception as e:
        logger.warning(f"Failed to clean MinIO files for source {source_id}: {e}")

    # Detach from wiki — orphan pages are removed, then rebuild index.
    from app.services import wiki_service
    await wiki_service.detach_source_from_wiki(db, source_id)
    await wiki_service.regenerate_index(db)

    await log_audit(db, _user, "delete", "source", str(source.id), reason=source.title)
    await repo.delete_by_id(Source, source_id)
    return {"deleted": True}
