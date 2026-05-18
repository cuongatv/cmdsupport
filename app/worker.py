"""
arq Worker — async Redis queue for document ingestion.

The worker now compiles each source into the LLM Wiki (markdown pages stored
in PostgreSQL) instead of producing chunk embeddings. See app/ai/wiki_compiler.py.

Start with:
    arq app.worker.WorkerSettings
"""

import uuid
import zipfile
from typing import Optional

from arq import cron
from arq.connections import ArqRedis, RedisSettings, create_pool
from loguru import logger
from sqlalchemy.orm.exc import StaleDataError

from app.config import settings
from app.jobs.task_jobs import (
    capture_flow_snapshots_job,
    scan_aging_tasks,
    task_assignment_notification,
    task_due_soon_scan,
)
from app.utils.progress import ProgressTracker


def _get_redis_settings() -> RedisSettings:
    return RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        database=settings.redis_db,
        password=settings.redis_password or None,
    )


# arq Redis pool (lazy init)
_arq_pool: Optional[ArqRedis] = None


async def get_arq_pool() -> ArqRedis:
    """Lazy-init arq Redis connection pool."""
    global _arq_pool
    if _arq_pool is None:
        _arq_pool = await create_pool(_get_redis_settings())
    return _arq_pool


# ---------------------------------------------------------------------------
# Ingestion tasks
# ---------------------------------------------------------------------------

async def ingest_file_task(ctx: dict, source_id: str):
    """
    arq task: full file ingestion → wiki compilation.
    Steps: download from MinIO → extract text → vision captions → outline → compile wiki.
    File must already be uploaded to MinIO before this task is enqueued.
    """
    from app.ai.mrp.pipeline import get_ingestion_pipeline, run_mrp_pipeline
    from app.ai.registry import ProviderRegistry
    from app.ai.wiki_agent import compile_source_with_agent
    from app.database import async_session_factory
    from app.database.models import KnowledgeType, Source
    from app.services.image_service import extract_images
    from app.services.kb_service import (
        _extract_text_from_file,
        _inline_image_captions,
    )
    from app.services.source_outline import assemble_full_text, build_outline
    from app.services.storage_service import storage_service

    sid = uuid.UUID(source_id)
    tracker = ProgressTracker(sid)

    async with async_session_factory() as session:
        source = await session.get(Source, sid)
        if not source:
            raise ValueError(f"Source {source_id} not found")
        if not source.minio_key:
            raise ValueError(f"Source {source_id} has no file in storage")

        file_name = source.file_name or source.minio_key.split("/")[-1]

        try:
            source.status = "processing"
            source.progress = 0
            source.progress_message = "Starting processing..."
            await session.commit()

            # --- Step 1: Download from MinIO (10%) ---
            await tracker.update(5, "Loading file...")
            file_data = storage_service.download_file(source.minio_key)
            await tracker.update(10, "File loaded")

            # --- Step 2: Extract text per page (25%) ---
            await tracker.update(15, "Extracting text (per page)...")
            pages_data = await _extract_text_from_file(file_data, file_name)

            if not pages_data or not any((p.get("content") or "").strip() for p in pages_data):
                source.status = "error"
                source.error_message = "Unable to extract text content"
                source.progress = 0
                await session.commit()
                return {"status": "error", "message": "No text content"}

            await tracker.update(25, "Text extraction complete")

            # --- Step 3: Extract images + vision captions (30→40%) ---
            await tracker.update(30, "Extracting and analyzing images...")
            images = extract_images(file_data, file_name, source_id)

            registry = ProviderRegistry(session)
            vision_provider = await registry.get_vision()
            total_images = len(images)
            if vision_provider and images:
                # Bump progress trong khoảng 30→40 mỗi vài image để UI thấy
                # tiến độ thật. Vision API có thể rate-limit (429/504) khiến
                # mỗi ảnh mất vài giây; nếu không emit progress, người dùng
                # tưởng kẹt ở 30%.
                for idx, img in enumerate(images, 1):
                    try:
                        if idx % 5 == 0 or idx == 1 or idx == total_images:
                            logger.info(f"Vision AI analyzing image {idx}/{total_images}...")
                        img_bytes = storage_service.download_file(img.minio_key)
                        mime_type = "image/png" if img.minio_key.lower().endswith(".png") else "image/jpeg"
                        img.caption = await vision_provider.analyze_image(img_bytes, mime_type)
                    except Exception as e:
                        logger.warning(f"Failed to analyze image {img.minio_key}: {e}")
                    if total_images > 0 and (idx % 5 == 0 or idx == total_images):
                        pct = 30 + int(10 * idx / total_images)
                        await tracker.update(
                            pct,
                            f"Phân tích ảnh {idx}/{total_images}...",
                        )
            elif images:
                logger.info("No vision provider configured, skipping image captioning")

            # Inline captions into per-page text so the compiler sees them.
            _inline_image_captions(pages_data, images)
            await tracker.update(40, f"Đã phân tích {total_images} ảnh")

            # --- Step 4: Build outline + assemble full_text (50%) ---
            await tracker.update(45, "Building document outline...")
            source.outline_json = build_outline(pages_data)
            full_text, page_offsets = assemble_full_text(pages_data)
            source.full_text = full_text
            source.page_offsets = page_offsets
            try:
                await session.commit()
            except StaleDataError:
                # Source row đã bị delete giữa lúc worker chạy (user xoá tay,
                # hoặc duplicate ingestion task race). Bỏ qua thay vì raise
                # để arq không retry mãi.
                await session.rollback()
                logger.warning(
                    f"ingest_file_task: source {source_id} disappeared mid-flight, aborting"
                )
                return {"status": "aborted", "reason": "source_deleted"}
            await tracker.update(50, f"Outline: {len(source.outline_json or [])} top-level sections")

            # --- Step 5: Resolve KnowledgeType context (52%) ---
            kt_slug = kt_name = kt_desc = None
            if source.knowledge_type_id:
                kt = await session.get(KnowledgeType, source.knowledge_type_id)
                if kt:
                    kt_slug, kt_name, kt_desc = kt.slug, kt.name, kt.description

            # --- Step 6: Compile into wiki (55-95%) ---
            if get_ingestion_pipeline(source) == "mrp":
                await tracker.update(55, "Running MRP map/reduce pipeline...")
                mrp_result = await run_mrp_pipeline(
                    session=session,
                    source=source,
                    full_text=full_text,
                    tracker=tracker,
                    registry=registry,
                    kt_slug=kt_slug,
                    kt_name=kt_name,
                    kt_desc=kt_desc,
                )
                mrp_status = mrp_result.get("status")
                if mrp_status in {"plan_ready", "plan_auto_approved", "already_in_refine", "already_in_verify", "already_in_commit"}:
                    if mrp_status == "plan_ready":
                        source.status = "plan_ready"
                        source.progress = 80
                        source.progress_message = "Review compilation plan"
                    else:
                        source.progress_message = "Plan approved - compiling wiki pages..."
                    source.error_message = None
                    await session.commit()
                    return {"status": mrp_status, "images": len(images), **mrp_result}
                # Auto-approved + ran refine inline is handled by run_refine_pipeline elsewhere.
                source.status = "ready"
                source.progress = 100
                source.progress_message = "Done"
                source.error_message = None
                await session.commit()
                return {
                    "status": "ready",
                    "images": len(images),
                    "pages_created": mrp_result.get("pages_created", 0),
                    "pages_updated": mrp_result.get("pages_updated", 0),
                }

            await tracker.update(55, "Compiling into wiki (agent)...")

            async def emit(step: int, message: str) -> None:
                progress = min(95, 55 + step)
                await tracker.update(progress, f"Compiling: {message}")

            result = await compile_source_with_agent(
                session=session,
                source=source,
                full_text=full_text,
                kt_slug=kt_slug,
                kt_name=kt_name,
                kt_desc=kt_desc,
                on_progress=emit,
            )
            await session.commit()
            await tracker.update(
                95,
                f"Wiki: +{result['pages_created']} pages, ~{result['pages_updated']} updated "
                f"({result['tool_calls']} tool calls)",
            )

            # --- Done (100%) ---
            source.status = "ready"
            source.progress = 100
            source.progress_message = "Done"
            source.error_message = None
            await session.commit()

            logger.success(
                f"Source {source_id} ingested: {len(images)} images, "
                f"+{result['pages_created']} pages, ~{result['pages_updated']} updated"
            )
            return {
                "status": "ready",
                "images": len(images),
                "pages_created": result["pages_created"],
                "pages_updated": result["pages_updated"],
            }

        except BaseException as e:
            # BaseException catches arq's asyncio.CancelledError raised on
            # job timeout (Exception alone misses it on some Python versions).
            # We MUST set status='error' so the UI does not show "processing
            # 67%" forever after a timeout.
            etype = type(e).__name__
            logger.error(f"Ingestion failed for {source_id}: {etype}: {e}")
            try:
                source.status = "error"
                source.error_message = f"{etype}: {str(e)[:480]}"
                source.progress = 0
                source.progress_message = f"Error: {etype}"
                await session.commit()
            except Exception as commit_err:
                logger.error(
                    f"Failed to mark source {source_id} as errored: {commit_err}"
                )
            raise


async def ingest_url_task(ctx: dict, source_id: str):
    """arq task: URL ingestion → wiki compilation."""
    from app.ai.mrp.pipeline import get_ingestion_pipeline, run_mrp_pipeline
    from app.ai.registry import ProviderRegistry
    from app.ai.wiki_agent import compile_source_with_agent
    from app.database import async_session_factory
    from app.database.models import KnowledgeType, Source
    from app.services.kb_service import _extract_text_from_url
    from app.services.source_outline import assemble_full_text, build_outline

    sid = uuid.UUID(source_id)
    tracker = ProgressTracker(sid)

    async with async_session_factory() as session:
        source = await session.get(Source, sid)
        if not source:
            raise ValueError(f"Source {source_id} not found")

        try:
            source.status = "processing"
            source.progress = 0
            await session.commit()

            await tracker.update(15, "Fetching content from URL...")
            if not source.url:
                source.status = "error"
                source.error_message = "Source has no URL"
                await session.commit()
                return {"status": "error"}
            pages_data = await _extract_text_from_url(source.url)

            if not pages_data or not any((p.get("content") or "").strip() for p in pages_data):
                source.status = "error"
                source.error_message = "Unable to fetch content from URL"
                await session.commit()
                return {"status": "error"}

            await tracker.update(40, "Building outline...")
            source.outline_json = build_outline(pages_data)
            full_text, page_offsets = assemble_full_text(pages_data)
            source.full_text = full_text
            source.page_offsets = page_offsets
            await session.commit()

            kt_slug = kt_name = kt_desc = None
            if source.knowledge_type_id:
                kt = await session.get(KnowledgeType, source.knowledge_type_id)
                if kt:
                    kt_slug, kt_name, kt_desc = kt.slug, kt.name, kt.description

            if get_ingestion_pipeline(source) == "mrp":
                await tracker.update(55, "Running MRP map/reduce pipeline...")
                registry = ProviderRegistry(session)
                mrp_result = await run_mrp_pipeline(
                    session=session,
                    source=source,
                    full_text=full_text,
                    tracker=tracker,
                    registry=registry,
                    kt_slug=kt_slug,
                    kt_name=kt_name,
                    kt_desc=kt_desc,
                )
                mrp_status = mrp_result.get("status")
                if mrp_status in {"plan_ready", "plan_auto_approved", "already_in_refine", "already_in_verify", "already_in_commit"}:
                    if mrp_status == "plan_ready":
                        source.status = "plan_ready"
                        source.progress = 80
                        source.progress_message = "Review compilation plan"
                    else:
                        source.progress_message = "Plan approved - compiling wiki pages..."
                    source.error_message = None
                    await session.commit()
                    return {"status": mrp_status, **mrp_result}
                source.status = "ready"
                source.progress = 100
                source.progress_message = "Done"
                source.error_message = None
                await session.commit()
                return {
                    "status": "ready",
                    "pages_created": mrp_result.get("pages_created", 0),
                    "pages_updated": mrp_result.get("pages_updated", 0),
                }

            await tracker.update(55, "Compiling into wiki (agent)...")

            async def emit(step: int, message: str) -> None:
                progress = min(95, 55 + step)
                await tracker.update(progress, f"Compiling: {message}")

            result = await compile_source_with_agent(
                session=session,
                source=source,
                full_text=full_text,
                kt_slug=kt_slug,
                kt_name=kt_name,
                kt_desc=kt_desc,
                on_progress=emit,
            )
            await session.commit()

            source.status = "ready"
            source.progress = 100
            source.progress_message = "Done"
            source.error_message = None
            await session.commit()

            logger.success(
                f"URL source {source_id} ingested: "
                f"+{result['pages_created']} pages, ~{result['pages_updated']} updated"
            )
            return {
                "status": "ready",
                "pages_created": result["pages_created"],
                "pages_updated": result["pages_updated"],
            }

        except BaseException as e:
            etype = type(e).__name__
            logger.error(f"URL ingestion failed for {source_id}: {etype}: {e}")
            try:
                source.status = "error"
                source.error_message = f"{etype}: {str(e)[:480]}"
                source.progress = 0
                source.progress_message = f"Error: {etype}"
                await session.commit()
            except Exception as commit_err:
                logger.error(
                    f"Failed to mark source {source_id} as errored: {commit_err}"
                )
            raise


async def reingest_file_task(ctx: dict, source_id: str, force: bool = False):
    """
    arq task: re-ingest a file already stored in MinIO.

    If `force=True`, detach this source from all wiki pages first (orphan
    pages get deleted). Otherwise the compiler will merge new ops on top of
    the existing wiki state.
    """
    from app.database import async_session_factory
    from app.database.models import Source
    from app.services import wiki_service

    sid = uuid.UUID(source_id)

    async with async_session_factory() as session:
        source = await session.get(Source, sid)
        if not source or not source.minio_key:
            raise ValueError(f"Source {source_id} not found or has no file")

        if force:
            await wiki_service.detach_source_from_wiki(session, sid)
            await wiki_service.regenerate_index(session)
            await session.commit()

    await ingest_file_task(ctx, source_id)


async def ingest_map_reduce_task(ctx: dict, source_id: str) -> dict:
    """arq task: re-run MAP + REDUCE for an existing source using cached full_text."""
    from app.ai.mrp.pipeline import run_mrp_pipeline
    from app.ai.registry import ProviderRegistry
    from app.database import async_session_factory
    from app.database.models import KnowledgeType, Source

    sid = uuid.UUID(source_id)
    tracker = ProgressTracker(sid)
    async with async_session_factory() as session:
        source = await session.get(Source, sid)
        if not source:
            raise ValueError(f"Source {source_id} not found")
        full_text = source.full_text or ""
        if not full_text.strip():
            raise ValueError(f"Source {source_id} has no extracted full_text; rerun ingest_file/url first")

        try:
            source.status = "processing"
            await session.commit()

            kt_slug = kt_name = kt_desc = None
            if source.knowledge_type_id:
                kt = await session.get(KnowledgeType, source.knowledge_type_id)
                if kt:
                    kt_slug, kt_name, kt_desc = kt.slug, kt.name, kt.description

            registry = ProviderRegistry(session)
            await tracker.update(10, "Running MRP map/reduce pipeline...")
            result = await run_mrp_pipeline(
                session=session,
                source=source,
                full_text=full_text,
                tracker=tracker,
                registry=registry,
                kt_slug=kt_slug,
                kt_name=kt_name,
                kt_desc=kt_desc,
            )
            mrp_status = result.get("status", "")
            if mrp_status == "plan_ready":
                source.status = "plan_ready"
                source.progress = 80
                source.progress_message = "Review compilation plan"
                source.error_message = None
                await session.commit()
            elif mrp_status.startswith("already_in_"):
                # Pipeline đã đi quá map/reduce ở phiên trước (ví dụ commit).
                # Không clear state -> UI kẹt processing 10%. Reset về trạng
                # thái phản ánh đúng phase hiện tại.
                phase = mrp_status.removeprefix("already_in_")
                if phase == "commit":
                    source.status = "ready"
                    source.progress = 100
                    source.progress_message = "Đã biên dịch xong từ trước"
                else:
                    # refine / verify: refine task vẫn đang chạy ở job khác,
                    # giữ trạng thái processing nhưng update message rõ ràng.
                    source.progress_message = (
                        f"Đang ở pha {phase}, không cần chạy lại MAP/REDUCE"
                    )
                source.error_message = None
                await session.commit()
            return result
        except BaseException as exc:
            etype = type(exc).__name__
            logger.error(f"MRP map/reduce failed for {source_id}: {etype}: {exc}")
            try:
                source.status = "error"
                source.error_message = f"{etype}: {str(exc)[:480]}"
                source.progress_message = f"Error: {etype}"
                await session.commit()
            except Exception as commit_err:
                logger.error(f"Failed to mark source {source_id} as errored: {commit_err}")
            raise


async def ingest_refine_task(ctx: dict, source_id: str) -> dict:
    """arq task: run REFINE + VERIFY + COMMIT for an approved MRP plan."""
    from app.ai.mrp.pipeline import run_refine_pipeline
    from app.ai.registry import ProviderRegistry
    from app.database import async_session_factory
    from app.database.models import KnowledgeType, Source

    sid = uuid.UUID(source_id)
    tracker = ProgressTracker(sid)
    async with async_session_factory() as session:
        source = await session.get(Source, sid)
        if not source:
            raise ValueError(f"Source {source_id} not found")
        full_text = source.full_text or ""
        if not full_text.strip():
            raise ValueError(f"Source {source_id} has no extracted full_text")

        try:
            source.status = "processing"
            await session.commit()

            kt_slug = kt_name = kt_desc = None
            if source.knowledge_type_id:
                kt = await session.get(KnowledgeType, source.knowledge_type_id)
                if kt:
                    kt_slug, kt_name, kt_desc = kt.slug, kt.name, kt.description

            registry = ProviderRegistry(session)
            await tracker.update(80, "Compiling wiki pages from approved plan...")
            result = await run_refine_pipeline(
                session=session,
                source=source,
                full_text=full_text,
                tracker=tracker,
                registry=registry,
                kt_slug=kt_slug,
                kt_name=kt_name,
                kt_desc=kt_desc,
            )
            return result
        except BaseException as exc:
            etype = type(exc).__name__
            logger.error(f"MRP refine failed for {source_id}: {etype}: {exc}")
            try:
                source.status = "error"
                source.error_message = f"{etype}: {str(exc)[:480]}"
                source.progress_message = f"Error: {etype}"
                await session.commit()
            except Exception as commit_err:
                logger.error(f"Failed to mark source {source_id} as errored: {commit_err}")
            raise


async def revise_compilation_plan_task(
    ctx: dict,
    source_id: str,
    revision_id: str,
) -> dict:
    """arq task: rerun REDUCE planning call with user feedback to regenerate plan.

    KHÔNG chạy lại MAP — chunk extracts coi như input bất biến cho vòng review.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.ai.mrp.reducer import run_reduce_phase
    from app.ai.registry import ProviderRegistry
    from app.database import async_session_factory
    from app.database.models import (
        KnowledgeType,
        Source,
        SourceChunkExtract,
        SourceCompilationPlan,
        SourceCompilationPlanRevision,
    )

    sid = uuid.UUID(source_id)
    rid = uuid.UUID(revision_id)
    tracker = ProgressTracker(sid)

    async with async_session_factory() as session:
        revision = await session.get(SourceCompilationPlanRevision, rid)
        source = await session.get(Source, sid)
        plan = (await session.execute(
            select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == sid)
        )).scalar_one_or_none()
        if not revision or not source or not plan:
            raise ValueError(
                f"revise_compilation_plan_task: missing revision/source/plan for {source_id}/{revision_id}"
            )

        # Guard: nếu một worker khác đã pickup cùng revision (re-enqueue,
        # duplicate, hoặc job replay) thì exit sớm để không double-charge LLM
        # và không ghi đè plan_json.
        if revision.status not in {"requested", "running"}:
            logger.info(
                f"revise_compilation_plan_task: revision {revision_id} already in status "
                f"{revision.status} — skipping rerun"
            )
            return {"status": "skipped", "revision_id": str(revision.id)}

        try:
            revision.status = "running"
            plan.status = "revising"
            source.status = "processing"
            source.progress = 60
            source.progress_message = "Đang tạo lại kế hoạch theo phản hồi..."
            source.error_message = None
            await session.commit()

            chunk_rows = (await session.execute(
                select(SourceChunkExtract)
                .where(
                    SourceChunkExtract.source_id == sid,
                    SourceChunkExtract.status == "done",
                )
                .order_by(SourceChunkExtract.chunk_index)
            )).scalars().all()
            if not chunk_rows:
                raise ValueError(
                    f"revise_compilation_plan_task: no MAP extracts found for source {source_id}"
                )

            history = (await session.execute(
                select(SourceCompilationPlanRevision)
                .where(SourceCompilationPlanRevision.plan_id == plan.id)
                .order_by(SourceCompilationPlanRevision.created_at.asc())
            )).scalars().all()
            history_payload = [
                {
                    "feedback": item.feedback,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "base_version": item.base_version,
                }
                for item in history
                if item.id != revision.id
            ]

            kt_slug = kt_name = kt_desc = None
            if source.knowledge_type_id:
                kt = await session.get(KnowledgeType, source.knowledge_type_id)
                if kt:
                    kt_slug, kt_name, kt_desc = kt.slug, kt.name, kt.description
            del kt_slug  # not used in REDUCE-only flow

            previous_plan = revision.previous_plan_snapshot or plan.plan_json or {}

            registry = ProviderRegistry(session)
            llm = await registry.get_llm()
            embedding_provider = None
            try:
                embedding_provider = await registry.get_embedding(task="document")
            except Exception as exc:
                logger.warning(f"MRP REVISE: embedding unavailable: {exc}")

            await tracker.update(65, "Tạo lại kế hoạch biên dịch...")
            await run_reduce_phase(
                session=session,
                source=source,
                chunk_extracts=list(chunk_rows),
                llm=llm,
                embedding_provider=embedding_provider,
                kt_name=kt_name,
                kt_desc=kt_desc,
                tracker=tracker,
                revision_feedback=revision.feedback,
                feedback_history=history_payload,
                previous_plan=previous_plan,
            )

            revision.status = "succeeded"
            revision.completed_at = datetime.now(timezone.utc)
            source.status = "plan_ready"
            source.progress = 80
            source.progress_message = "Kế hoạch đã được tạo lại - sẵn sàng để duyệt"
            await session.commit()
            return {"status": "plan_ready", "revision_id": str(revision.id)}
        except BaseException as exc:
            etype = type(exc).__name__
            logger.error(f"MRP REVISE failed for source={source_id}: {etype}: {exc}")
            try:
                revision.status = "failed"
                revision.error_message = f"{etype}: {str(exc)[:480]}"
                revision.completed_at = datetime.now(timezone.utc)
                plan.status = "pending_review"
                source.status = "plan_ready"
                source.progress_message = f"Tái sinh kế hoạch thất bại: {etype}"
                await session.commit()
            except Exception as commit_err:
                logger.error(
                    f"revise_compilation_plan_task: failed to mark revision errored: {commit_err}"
                )
            raise


# ---------------------------------------------------------------------------
# Worker configuration
# ---------------------------------------------------------------------------


async def ingest_skill_task(ctx: dict, skill_id: str, version_id: str, file_path: str, file_name: str):
    """
    arq task: unzip skill package from disk buffer, store in MinIO, and extract metadata.
    """
    import os

    from app.database import async_session_factory
    from app.database.models import Skill, SkillVersion
    from app.services.storage_service import storage_service

    sid = uuid.UUID(skill_id)
    vid = uuid.UUID(version_id)
    skill_name = file_name.rsplit(".", 1)[0]
    
    logger.info(f"Starting ingestion for skill: {skill_name} ({skill_id})")

    async with async_session_factory() as session:
        skill = await session.get(Skill, sid)
        version = await session.get(SkillVersion, vid)
        
        if not skill or not version:
            logger.error(f"Skill {skill_id} or Version {version_id} not found in DB")
            return

        try:
            skill.status = "processing"
            await session.commit()

            if not os.path.exists(file_path):
                logger.error(f"Disk buffer file not found: {file_path}")
                skill.status = "error"
                await session.commit()
                return

            import asyncio
            import hashlib

            from app.services.kb_service import _guess_content_type

            # 1. Stream Hash calculation
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            file_hash = sha256_hash.hexdigest()

            # 2. Unzip with streaming, security checks, and concurrent uploads
            MAX_UNCOMPRESSED_SIZE = 10 * 1024 * 1024  # 10 MB
            MAX_FILE_COUNT = 100

            total_size = 0
            file_count = 0
            readme_content = None

            upload_tasks = []
            semaphore = asyncio.Semaphore(10)

            async def _upload_worker(zf_path, member_name, obj_name, file_size):
                async with semaphore:
                    # Open a fresh ZipFile instance in the thread to avoid GIL lock contention
                    with zipfile.ZipFile(zf_path) as local_zf:
                        with local_zf.open(member_name) as f_stream:
                            await storage_service.upload_stream_async(
                                obj_name, f_stream, file_size, _guess_content_type(member_name)
                            )

            with zipfile.ZipFile(file_path) as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    
                    filename = member.filename
                    
                    # [Security] Zip Slip check
                    if filename.startswith("/") or filename.startswith("\\") or "../" in filename or "..\\" in filename:
                        raise ValueError(f"Security risk: Zip Slip detected in {filename}")
                        
                    # [Security] File count check
                    file_count += 1
                    if file_count > MAX_FILE_COUNT:
                        raise ValueError(f"Too many files (exceeds {MAX_FILE_COUNT})")
                        
                    # [Security] Zip Bomb check
                    total_size += member.file_size
                    if total_size > MAX_UNCOMPRESSED_SIZE:
                        raise ValueError("Uncompressed size too large (exceeds 10MB)")

                    object_name = f"skills/{skill_id}/versions/{version.version_number}/content/{filename}"
                    target_readme = f"{skill_name}/SKILL.md".lower()

                    if filename.lower() == target_readme or filename.lower().endswith("/skill.md"):
                        with zf.open(member) as f:
                            content = f.read()
                            readme_content = content.decode("utf-8", errors="ignore")
                            logger.info(f"Found SKILL.md in {filename}")
                        
                        storage_service.upload_file(
                            object_name=object_name,
                            data=content,
                            content_type=_guess_content_type(filename)
                        )
                    else:
                        upload_tasks.append(
                            _upload_worker(file_path, filename, object_name, member.file_size)
                        )

            if upload_tasks:
                await asyncio.gather(*upload_tasks)

            # 3. Update DB with extracted metadata
            if readme_content:
                skill.description = readme_content
                version.readme = readme_content
            
            skill.version_hash = file_hash
            skill.current_version = version.version_number
            skill.storage_path = f"skills/{skill_id}/versions/{version.version_number}/content/"
            skill.status = "active"
            
            version.version_hash = file_hash
            version.storage_path = skill.storage_path
            
            await session.commit()
            logger.success(f"Skill {skill_name} version {version.version_number} processed successfully")

        except Exception as e:
            logger.exception(f"Failed to process skill {skill_name}: {e}")
            skill.status = "error"
            await session.commit()
        finally:
            # Clean up disk buffer
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.debug(f"Cleaned up disk buffer: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {file_path}: {e}")


async def delete_skill_task(ctx: dict, skill_id: str):
    """
    arq task: delete skill files from MinIO and remove from DB.
    """
    from app.database import async_session_factory
    from app.database.models import Skill
    from app.services.storage_service import storage_service

    sid = uuid.UUID(skill_id)
    
    logger.info(f"Starting deletion task for skill: {skill_id}")

    async with async_session_factory() as session:
        skill = await session.get(Skill, sid)
        if not skill:
            logger.warning(f"Skill {skill_id} already deleted or not found")
            return

        try:
            # 1. Delete files from MinIO (prefix: skills/{skill_id}/)
            prefix = f"skills/{skill_id}/"
            storage_service.delete_prefix(prefix)
            
            # 2. Delete skill from DB (cascades to SkillVersion if configured, 
            # but let's be explicit if needed or trust the model relationship)
            await session.delete(skill)
            await session.commit()
            
            logger.success(f"Skill {skill_id} and all assets deleted successfully")

        except Exception as e:
            logger.exception(f"Failed to delete skill {skill_id}: {e}")
            raise


async def cleanup_temp_uploads_cron(ctx: dict):
    """
    Cronjob: Quét và dọn các file rác trong temp_uploads do server crash để lại (cũ hơn 1 giờ).
    """
    import os
    import time
    
    temp_dir = "temp_uploads"
    if not os.path.exists(temp_dir):
        return
        
    cutoff_time = time.time() - 3600  # 1 hour ago
    
    for filename in os.listdir(temp_dir):
        file_path = os.path.join(temp_dir, filename)
        if os.path.isfile(file_path):
            if os.path.getmtime(file_path) < cutoff_time:
                try:
                    os.remove(file_path)
                    logger.info(f"Cronjob: Cleaned up orphaned temp file {filename}")
                except Exception as e:
                    logger.debug(f"Cronjob: Failed to clean {filename}: {e}")


class WorkerSettings:
    """arq worker configuration."""

    functions = [
        ingest_file_task,
        ingest_url_task,
        reingest_file_task,
        ingest_map_reduce_task,
        ingest_refine_task,
        revise_compilation_plan_task,
        task_assignment_notification,
        scan_aging_tasks,
        capture_flow_snapshots_job,
    ]
    cron_jobs = [
        # Scan for tasks due in ~1 day every 15 minutes; service is idempotent
        # per (task, recipient, UTC calendar day) so multiple runs are safe.
        cron(task_due_soon_scan, minute={0, 15, 30, 45}),
        # Scan for aging tasks every hour; service short-circuits when the
        # Phase 1 feature flag is off, and dedupes per task within 24h.
        cron(scan_aging_tasks, minute=5),
        # Capture Phase 5 flow snapshots once per day at 01:00.
        cron(capture_flow_snapshots_job, hour=1, minute=0),
    ]
    redis_settings = _get_redis_settings()
    max_jobs = settings.worker_max_jobs
    job_timeout = settings.worker_job_timeout
    max_tries = 3
    retry_delay = 10
    health_check_interval = 30

    @staticmethod
    async def on_startup(ctx: dict):
        logger.info("arq worker started — listening for ingestion jobs...")

    @staticmethod
    async def on_shutdown(ctx: dict):
        logger.info("arq worker shutting down...")


class SkillWorkerSettings:
    """arq worker configuration dedicated to Skills."""

    functions = [ingest_skill_task, delete_skill_task]
    queue_name = "skills_queue"
    redis_settings = _get_redis_settings()
    max_jobs = settings.worker_max_jobs
    job_timeout = settings.worker_job_timeout
    max_tries = 3
    retry_delay = 10
    health_check_interval = 30
    
    cron_jobs = [
        cron(cleanup_temp_uploads_cron, minute=0)
    ]

    @staticmethod
    async def on_startup(ctx: dict):
        logger.info("arq skills worker started — listening for skill jobs...")

    @staticmethod
    async def on_shutdown(ctx: dict):
        logger.info("arq skills worker shutting down...")
