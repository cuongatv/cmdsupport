"""MRP pipeline orchestration and commit phase."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional, cast

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.mrp.mapper import run_map_phase
from app.ai.mrp.reducer import run_reduce_phase
from app.ai.mrp.verifier import run_verify_phase
from app.ai.mrp.writer import PageWriteResult, run_refine_phase
from app.services.wiki_taxonomy_classifier import ClassifierResult, classify_page_candidate
from app.utils.progress import ProgressTracker

DEFAULT_INGESTION_PIPELINE = "mrp"


def normalize_ingestion_pipeline(value: Optional[str]) -> str:
    """Normalize user-provided ingestion pipeline selection.

    Mặc định là ``mrp`` để mọi tài liệu mới chạy luồng map/reduce/plan/refine.
    Người dùng vẫn có thể chọn ``legacy`` để dùng wiki agent biên dịch trực tiếp.
    """
    normalized = (value or DEFAULT_INGESTION_PIPELINE).strip().lower()
    if normalized not in {"legacy", "mrp"}:
        raise ValueError("ingestion_pipeline must be 'legacy' or 'mrp'")
    return normalized


def get_ingestion_pipeline(source) -> str:
    """Read source metadata and return legacy or mrp.

    Source được tạo trước khi default đổi sang ``mrp`` (không có metadata) sẽ
    được coi là ``legacy`` để không bị reprocess ngoài ý muốn.
    """
    metadata = source.metadata_ or {}
    raw = metadata.get("ingestion_pipeline")
    if not raw:
        return "legacy"
    return normalize_ingestion_pipeline(str(raw))


def set_ingestion_pipeline(source, pipeline: str) -> None:
    """Store ingestion pipeline in Source.metadata_ without clobbering metadata."""
    metadata = dict(source.metadata_ or {})
    metadata["ingestion_pipeline"] = normalize_ingestion_pipeline(pipeline)
    source.metadata_ = metadata


async def _embed_page(registry, title: str, summary: str, content_md: str) -> Optional[list[float]]:
    """Best-effort page embedding using CMD Support's active embedding provider."""
    try:
        provider = await registry.get_embedding(task="document")
        return await provider.embed(f"{title}\n\n{summary}\n\n{content_md[:4000]}")
    except Exception as exc:
        logger.warning(f"MRP COMMIT embedding skipped: {exc}")
        return None


async def run_commit_phase(
    session: AsyncSession,
    source,
    page_results: list[PageWriteResult],
    plan,
    registry,
    kt_slug: Optional[str],
    tracker: ProgressTracker,
) -> dict[str, int]:
    """Commit generated pages to the scoped wiki."""
    from app.ai.mrp.merger import merge_page_content
    from app.database.models import Source
    from app.services import wiki_service

    scope_type = source.scope_type or "global"
    scope_id = source.scope_id
    pages_created = 0
    pages_updated = 0

    merge_llm = None
    try:
        merge_llm = await registry.get_llm()
    except Exception as exc:
        logger.warning(f"MRP COMMIT merge LLM unavailable: {exc}")

    await tracker.update(95, f"Committing {len(page_results)} pages to wiki...")

    for page_result in page_results:
        try:
            await session.execute(select(func.pg_advisory_xact_lock(func.hashtext(page_result.slug))))
            action = page_result.action.upper()
            if action == "CREATE":
                existing = await wiki_service.get_page_by_slug(
                    session,
                    page_result.slug,
                    scope_type=scope_type,
                    scope_id=scope_id,
                )
                if existing:
                    action = "UPDATE"
                else:
                    embedding = await _embed_page(
                        registry,
                        page_result.title,
                        page_result.summary,
                        page_result.content_md,
                    )
                    classification: ClassifierResult = await classify_page_candidate(
                        session,
                        title=page_result.title,
                        summary=page_result.summary,
                        page_type=page_result.page_type,
                        body_excerpt=page_result.content_md,
                        source_taxonomy_slugs=[kt_slug] if kt_slug else None,
                        source_ids=[str(source.id)] if source and source.id else None,
                        existing_slugs=None,
                        rule_linked=False,
                    )
                    taxonomy_slugs = list(cast(list[str], classification.get("slugs") or []))
                    if kt_slug and kt_slug not in taxonomy_slugs:
                        taxonomy_slugs.append(kt_slug)
                    await wiki_service.apply_create(
                        session,
                        slug=page_result.slug,
                        title=page_result.title,
                        page_type=page_result.page_type,
                        content_md=page_result.content_md,
                        summary=page_result.summary,
                        knowledge_type_slugs=taxonomy_slugs,
                        source_ids=[source.id],
                        embedding=embedding,
                        scope_type=scope_type,
                        scope_id=scope_id,
                        taxonomy_confidence=cast(Optional[float], classification.get("confidence")),
                        taxonomy_rationale=cast(Optional[str], classification.get("rationale")),
                        taxonomy_needs_review=cast(Optional[bool], classification.get("needs_review")),
                        taxonomy_classifier_version=cast(
                            Optional[str], classification.get("classifier_version")
                        ),
                    )
                    pages_created += 1

            if action == "UPDATE":
                existing_page = await wiki_service.get_page_by_slug(
                    session,
                    page_result.slug,
                    scope_type=scope_type,
                    scope_id=scope_id,
                )
                final_content = page_result.content_md
                if existing_page and existing_page.content_md and merge_llm:
                    existing_source_ids = {str(item) for item in (existing_page.source_ids or [])}
                    if str(source.id) not in existing_source_ids and len(existing_page.content_md.strip()) > 100:
                        final_content = await merge_page_content(
                            merge_llm,
                            existing_page.content_md,
                            page_result.content_md,
                            page_result.slug,
                        )
                embedding = await _embed_page(
                    registry,
                    page_result.title,
                    page_result.summary,
                    final_content,
                )
                existing_slugs = list(existing_page.knowledge_type_slugs or []) if existing_page else []
                classification: ClassifierResult = await classify_page_candidate(
                    session,
                    title=page_result.title,
                    summary=page_result.summary,
                    page_type=(existing_page.page_type if existing_page else page_result.page_type) or "concept",
                    body_excerpt=final_content,
                    source_taxonomy_slugs=[kt_slug] if kt_slug else None,
                    source_ids=[str(source.id)] if source and source.id else None,
                    existing_slugs=existing_slugs or None,
                    rule_linked=False,
                )
                taxonomy_slugs = list(cast(list[str], classification.get("slugs") or []))
                for slug_value in existing_slugs:
                    if slug_value not in taxonomy_slugs:
                        taxonomy_slugs.append(slug_value)
                if kt_slug and kt_slug not in taxonomy_slugs:
                    taxonomy_slugs.append(kt_slug)
                page = await wiki_service.apply_update(
                    session,
                    slug=page_result.slug,
                    new_content_md=final_content,
                    summary=page_result.summary,
                    title=page_result.title,
                    knowledge_type_slugs=taxonomy_slugs,
                    add_source_id=source.id,
                    embedding=embedding,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    taxonomy_confidence=cast(Optional[float], classification.get("confidence")),
                    taxonomy_rationale=cast(Optional[str], classification.get("rationale")),
                    taxonomy_needs_review=cast(Optional[bool], classification.get("needs_review")),
                    taxonomy_classifier_version=cast(
                        Optional[str], classification.get("classifier_version")
                    ),
                )
                if page is None:
                    await wiki_service.apply_create(
                        session,
                        slug=page_result.slug,
                        title=page_result.title,
                        page_type=page_result.page_type,
                        content_md=page_result.content_md,
                        summary=page_result.summary,
                        knowledge_type_slugs=taxonomy_slugs,
                        source_ids=[source.id],
                        embedding=embedding,
                        scope_type=scope_type,
                        scope_id=scope_id,
                        taxonomy_confidence=cast(Optional[float], classification.get("confidence")),
                        taxonomy_rationale=cast(Optional[str], classification.get("rationale")),
                        taxonomy_needs_review=cast(Optional[bool], classification.get("needs_review")),
                        taxonomy_classifier_version=cast(
                            Optional[str], classification.get("classifier_version")
                        ),
                    )
                    pages_created += 1
                else:
                    pages_updated += 1
            await session.flush()
        except Exception as exc:
            logger.error(f"MRP COMMIT failed for {page_result.slug}: {exc}")

    await wiki_service.regenerate_index(session, scope_type=scope_type, scope_id=scope_id)
    await wiki_service.append_log(
        session,
        f"MRP ingested '{source.title or source.file_name or source.id}': +{pages_created} created, ~{pages_updated} updated",
        scope_type=scope_type,
        scope_id=scope_id,
    )

    if plan:
        plan.status = "done"
    src = await session.get(Source, source.id)
    if src:
        src.pipeline_phase = "commit"
        src.status = "ready"
        src.progress = 100
        src.progress_message = "Done"
        src.error_message = None
    await session.commit()
    return {"pages_created": pages_created, "pages_updated": pages_updated}


async def _load_plan(session: AsyncSession, source_id: uuid.UUID):
    from app.database.models import SourceCompilationPlan

    return (await session.execute(
        select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == source_id)
    )).scalar_one_or_none()


async def _load_chunk_extracts(session: AsyncSession, source_id: uuid.UUID) -> list[Any]:
    from app.database.models import SourceChunkExtract

    rows = (await session.execute(
        select(SourceChunkExtract).where(
            SourceChunkExtract.source_id == source_id,
            SourceChunkExtract.status == "done",
        ).order_by(SourceChunkExtract.chunk_index)
    )).scalars().all()
    return list(rows)


async def _auto_trigger_refine(source_id: uuid.UUID, plan) -> dict[str, Any]:
    from app.database import async_session_factory
    from app.database.models import Source, SourceCompilationPlan
    from app.worker import get_arq_pool

    async with async_session_factory() as session:
        plan_row = await session.get(SourceCompilationPlan, plan.id)
        if plan_row and plan_row.status == "pending_review":
            plan_row.status = "approved"
            plan_row.review_note = "Auto-approved"
            plan_row.reviewed_at = datetime.now(timezone.utc)
        source = await session.get(Source, source_id)
        if source:
            source.status = "processing"
            source.progress_message = "Plan approved - compiling wiki pages..."
        await session.commit()

    pool = await get_arq_pool()
    job = await pool.enqueue_job("ingest_refine_task", str(source_id))
    return {"status": "plan_auto_approved", "job_id": job.job_id if job else None}


async def run_mrp_pipeline(
    session: AsyncSession,
    source,
    full_text: str,
    tracker: ProgressTracker,
    registry,
    kt_slug: Optional[str],
    kt_name: Optional[str],
    kt_desc: Optional[str],
) -> dict[str, Any]:
    """Run Phase 0-2 and stop at human plan review unless auto-approved."""
    from app.config import settings
    from app.database.models import Source

    source_id = source.id
    if source.pipeline_phase == "plan_review":
        plan = await _load_plan(session, source_id)
        if plan and plan.status in {"pending_review", "approved"}:
            if plan.status == "approved" or settings.mrp_auto_approve_plan:
                return await _auto_trigger_refine(source_id, plan)
            return {"status": "plan_ready", "plan_id": str(plan.id)}

    if source.pipeline_phase in {"refine", "verify", "commit"}:
        return {"status": f"already_in_{source.pipeline_phase}"}

    llm = await registry.get_llm()
    embedding_provider = None
    try:
        embedding_provider = await registry.get_embedding(task="document")
    except Exception as exc:
        logger.warning(f"MRP: embedding unavailable for REDUCE: {exc}")

    _strategy, chunk_extracts = await run_map_phase(
        session=session,
        source_id=source_id,
        full_text=full_text,
        outline_json=source.outline_json,
        tracker=tracker,
        llm=llm,
    )
    if not chunk_extracts:
        raise ValueError(f"MAP produced no successful chunks for source={source_id}")

    src = await session.get(Source, source_id)
    if src:
        src.pipeline_phase = "reduce"
        await session.commit()

    plan = await run_reduce_phase(
        session=session,
        source=source,
        chunk_extracts=chunk_extracts,
        llm=llm,
        embedding_provider=embedding_provider,
        kt_name=kt_name,
        kt_desc=kt_desc,
        tracker=tracker,
    )
    await tracker.update(80, "Compilation plan ready")

    if settings.mrp_auto_approve_plan:
        return await _auto_trigger_refine(source_id, plan)
    return {"status": "plan_ready", "plan_id": str(plan.id)}


async def run_refine_pipeline(
    session: AsyncSession,
    source,
    full_text: str,
    tracker: ProgressTracker,
    registry,
    kt_slug: Optional[str],
    kt_name: Optional[str],
    kt_desc: Optional[str],
) -> dict[str, int]:
    """Run Phase 3-5 after plan approval."""
    del kt_name, kt_desc
    from app.database.models import Source

    plan = await _load_plan(session, source.id)
    if plan is None:
        raise ValueError(f"No compilation plan found for source={source.id}")
    if plan.status not in {"approved", "in_progress", "done"}:
        raise ValueError(f"Plan for source={source.id} is not approved")

    chunk_extracts = await _load_chunk_extracts(session, source.id)
    llm = await registry.get_llm()
    embedding_provider = None
    try:
        embedding_provider = await registry.get_embedding(task="document")
    except Exception as exc:
        logger.warning(f"MRP: embedding unavailable for REFINE/VERIFY: {exc}")

    src = await session.get(Source, source.id)
    if src:
        src.pipeline_phase = "refine"
    plan.status = "in_progress"
    await session.commit()

    page_results = await run_refine_phase(
        session=session,
        source=source,
        plan=plan,
        chunk_extracts=chunk_extracts,
        full_text=full_text,
        llm=llm,
        embedding_provider=embedding_provider,
        kt_slug=kt_slug,
        tracker=tracker,
    )

    src = await session.get(Source, source.id)
    if src:
        src.pipeline_phase = "verify"
    await session.commit()

    page_results = await run_verify_phase(
        session=session,
        source=source,
        page_results=page_results,
        chunk_extracts=chunk_extracts,
        full_text=full_text,
        llm=llm,
        embedding_provider=embedding_provider,
        tracker=tracker,
    )

    return await run_commit_phase(
        session=session,
        source=source,
        page_results=page_results,
        plan=plan,
        registry=registry,
        kt_slug=kt_slug,
        tracker=tracker,
    )
