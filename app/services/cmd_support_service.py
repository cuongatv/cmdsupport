"""
CMD Support Service — advisory session creation, retrieval, and listing.
"""

import json
import re
import time
import uuid
from typing import Optional

from fastapi import HTTPException
from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.cmd_support_prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT_VI,
    build_user_prompt,
)
from app.database.models import (
    AuditLog,
    CmdAdvisorySession,
    Employee,
    Industry,
    Province,
)
from app.services.audit_service import log_audit

# Sentinel UUID for anonymous audit log entries (principal_id is NOT NULL)
_ANONYMOUS_UUID = uuid.UUID("00000000-0000-0000-0000-000000000000")


async def _log_anonymous_audit(
    db: AsyncSession,
    resource_id: str,
    reason: str,
) -> None:
    """Log an audit entry for anonymous (unauthenticated) advisory requests."""
    entry = AuditLog(
        principal_id=_ANONYMOUS_UUID,
        principal_type="anonymous",
        action="create",
        resource_type="cmd_advisory",
        resource_id=resource_id,
        decision="ALLOW",
        reason=reason,
    )
    db.add(entry)


# ---------------------------------------------------------------------------
# Options helpers
# ---------------------------------------------------------------------------

async def list_provinces(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Province).order_by(Province.sort_order)
    )
    rows = result.scalars().all()
    return [
        {"code": r.code, "name": r.name, "short_name": r.short_name,
         "type": r.type, "region": r.region}
        for r in rows
    ]


async def list_industries(
    db: AsyncSession,
    level: Optional[int] = None,
    parent_code: Optional[str] = None,
) -> list[dict]:
    stmt = select(Industry).order_by(Industry.sort_order)
    if level is not None:
        stmt = stmt.where(Industry.level == level)
    if parent_code is not None:
        stmt = stmt.where(Industry.parent_code == parent_code)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {"code": r.code, "name": r.name, "level": r.level, "parent_code": r.parent_code}
        for r in rows
    ]


async def list_options(db: AsyncSession) -> dict:
    provinces = await list_provinces(db)
    industries_l1 = await list_industries(db, level=1)
    industries_l2 = await list_industries(db, level=2)
    return {
        "provinces": provinces,
        "industries_level1": industries_l1,
        "industries_level2": industries_l2,
    }


# ---------------------------------------------------------------------------
# Advisory CRUD
# ---------------------------------------------------------------------------

SEGMENT_LABELS_VI = {
    "sme": "Doanh nghiệp nhỏ và vừa (SME)",
    "midcom": "Doanh nghiệp trung lớn (Midcom)",
    "public_admin": "Hành chính sự nghiệp",
}


async def create_advice(
    db: AsyncSession,
    user: Optional[Employee],
    customer_name: str,
    province_code: Optional[str],
    industry_code: Optional[str],
    needs: str,
    additional_context: Optional[str],
    customer_segment: Optional[str] = "sme",
) -> CmdAdvisorySession:
    t0 = time.time()
    segment = (customer_segment or "sme").lower()
    segment_label = SEGMENT_LABELS_VI.get(segment, SEGMENT_LABELS_VI["sme"])

    # Resolve province
    province_name: Optional[str] = None
    if province_code:
        row = (await db.execute(
            select(Province).where(Province.code == province_code)
        )).scalar_one_or_none()
        if row:
            province_name = row.name

    # Resolve industry
    industry_name: Optional[str] = None
    if industry_code:
        row = (await db.execute(
            select(Industry).where(Industry.code == industry_code)
        )).scalar_one_or_none()
        if row:
            industry_name = row.name

    # Check AI providers
    from app.ai.registry import ProviderRegistry
    registry = ProviderRegistry(db)
    try:
        emb_provider = await registry.get_embedding(task="search_query")
    except ValueError:
        raise HTTPException(
            status_code=503,
            detail="Chưa cấu hình AI provider trong Cài đặt",
        )
    try:
        llm = await registry.get_llm()
    except ValueError:
        raise HTTPException(
            status_code=503,
            detail="Chưa cấu hình AI provider trong Cài đặt",
        )

    # Build search query
    query_parts = [segment_label]
    if industry_name:
        query_parts.append(industry_name)
    if province_name:
        query_parts.append(province_name)
    query_parts.append(needs)
    search_query = " ".join(query_parts)

    # Embed query
    query_embedding = await emb_provider.embed(search_query)

    # Semantic search wiki (top_k=10)
    from app.services.wiki_service import search_pages_semantic
    results = await search_pages_semantic(
        db, query_embedding, top_k=10, scope_type="global", scope_id=None,
    )

    # Build context blocks (max 1500 chars per page excerpt)
    context_blocks = []
    all_source_ids: set[uuid.UUID] = set()
    for idx, (page, sim) in enumerate(results, 1):
        excerpt = (page.content_md or "")[:1500]
        context_blocks.append({
            "index": idx,
            "slug": page.slug,
            "title": page.title,
            "summary": page.summary or "",
            "excerpt": excerpt,
        })
        if page.source_ids:
            all_source_ids.update(page.source_ids)

    retrieved_page_ids = [page.id for page, _ in results]
    retrieved_source_ids = list(all_source_ids)

    _default_disclaimer = "Cần RM xác minh điều kiện cấp tín dụng theo quy định BIDV hiện hành. Kết quả tư vấn chỉ mang tính tham khảo."

    # Short-circuit: no wiki results → skip LLM call
    if len(results) == 0:
        duration_ms = int((time.time() - t0) * 1000)
        result_json = {
            "customer_context": {
                "name": customer_name,
                "province": province_name,
                "industry": industry_name,
                "detected_needs": [needs],
            },
            "analysis": "Chưa có tài liệu liên quan trong kho tri thức nội bộ để phân tích nhu cầu khách hàng.",
            "recommendations": [],
            "red_flags": [],
            "offer_materials": [],
            "follow_up_questions": [],
            "coverage_gaps": ["Chưa có tài liệu liên quan trong kho tri thức nội bộ"],
            "rm_disclaimer": _default_disclaimer,
        }
        session_obj = CmdAdvisorySession(
            created_by_id=user.id if user else None,
            customer_name=customer_name,
            province_code=province_code,
            province_name=province_name,
            industry_code=industry_code,
            industry_name=industry_name,
            customer_segment=segment,
            needs=needs,
            additional_context=additional_context,
            retrieved_wiki_page_ids=[],
            retrieved_source_ids=[],
            result_json=result_json,
            model_provider=None,
            model_id=None,
            prompt_version=PROMPT_VERSION,
            scope_type="global",
            status="ready",
            error_message=None,
            duration_ms=duration_ms,
        )
        db.add(session_obj)
        if user:
            await log_audit(
                db, user,
                action="create",
                resource_type="cmd_advisory",
                resource_id=str(session_obj.id),
                reason=f"customer={customer_name}; segment={segment}; province={province_code}; industry={industry_code}; top_k=0; status=ready",
            )
        else:
            await _log_anonymous_audit(
                db,
                resource_id=str(session_obj.id),
                reason=f"anonymous public advisory; customer={customer_name}; segment={segment}; province={province_code}; industry={industry_code}; top_k=0; status=ready",
            )
        await db.flush()
        await db.refresh(session_obj)
        return session_obj

    # Build prompts
    user_prompt = build_user_prompt(
        customer_name=customer_name,
        province_name=province_name,
        industry_name=industry_name,
        segment_label=segment_label,
        needs=needs,
        additional_context=additional_context,
        context_blocks=context_blocks,
    )

    # Call LLM
    status = "ready"
    error_message = None
    result_json = None

    try:
        raw_output = await llm.generate(
            prompt=user_prompt,
            system=SYSTEM_PROMPT_VI,
            max_tokens=4096,
            temperature=0.2,
        )
        # Strip markdown fences if present
        cleaned = raw_output.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        result_json = json.loads(cleaned)
    except json.JSONDecodeError:
        status = "failed"
        error_message = "LLM output không hợp lệ JSON"
        result_json = {"raw": raw_output}
    except Exception as e:
        status = "failed"
        error_message = f"Lỗi gọi LLM: {str(e)}"
        logger.error(f"CMD advice LLM error: {e}")

    # Post-LLM validation (grounding hardening)
    if status == "ready" and isinstance(result_json, dict):
        # Ensure customer_context exists
        if "customer_context" not in result_json:
            result_json["customer_context"] = {
                "name": customer_name,
                "province": province_name,
                "industry": industry_name,
                "detected_needs": [needs],
            }
        # Ensure analysis exists
        if not result_json.get("analysis"):
            result_json["analysis"] = ""

        # Drop recommendations without citations
        recs = result_json.get("recommendations", [])
        if isinstance(recs, list):
            valid_recs = []
            dropped = 0
            for rec in recs:
                citations = rec.get("citations")
                if isinstance(citations, list) and len(citations) > 0:
                    # Validate confidence
                    if rec.get("confidence") not in ("low", "medium", "high"):
                        rec["confidence"] = "low"
                    valid_recs.append(rec)
                else:
                    dropped += 1
            result_json["recommendations"] = valid_recs
            if dropped > 0:
                logger.warning(f"CMD advice: loại {dropped} recommendation(s) vì thiếu citation")
                gaps = result_json.get("coverage_gaps", []) or []
                gaps.append(f"Đã loại {dropped} gợi ý vì thiếu trích dẫn")
                result_json["coverage_gaps"] = gaps

        # Ensure rm_disclaimer has default value
        if not result_json.get("rm_disclaimer"):
            result_json["rm_disclaimer"] = _default_disclaimer

        # Ensure red_flags field exists
        if "red_flags" not in result_json:
            result_json["red_flags"] = []

    duration_ms = int((time.time() - t0) * 1000)

    # Get provider info
    llm_config = await registry._load_config("llm")

    # Persist session
    session_obj = CmdAdvisorySession(
        created_by_id=user.id if user else None,
        customer_name=customer_name,
        province_code=province_code,
        province_name=province_name,
        industry_code=industry_code,
        industry_name=industry_name,
        customer_segment=segment,
        needs=needs,
        additional_context=additional_context,
        retrieved_wiki_page_ids=retrieved_page_ids,
        retrieved_source_ids=retrieved_source_ids,
        result_json=result_json,
        model_provider=llm_config.provider.value,
        model_id=llm_config.model_id,
        prompt_version=PROMPT_VERSION,
        scope_type="global",
        status=status,
        error_message=error_message,
        duration_ms=duration_ms,
    )
    db.add(session_obj)

    # Audit log (chi tiết)
    if user:
        await log_audit(
            db, user,
            action="create",
            resource_type="cmd_advisory",
            resource_id=str(session_obj.id),
            reason=f"customer={customer_name}; segment={segment}; province={province_code}; industry={industry_code}; top_k={len(results)}; status={status}",
        )
    else:
        await _log_anonymous_audit(
            db,
            resource_id=str(session_obj.id),
            reason=f"anonymous public advisory; customer={customer_name}; segment={segment}; province={province_code}; industry={industry_code}; top_k={len(results)}; status={status}",
        )

    await db.flush()
    await db.refresh(session_obj)
    return session_obj


async def get_advice(
    db: AsyncSession,
    user: Employee,
    advisory_id: uuid.UUID,
) -> CmdAdvisorySession:
    result = await db.execute(
        select(CmdAdvisorySession)
        .options(selectinload(CmdAdvisorySession.created_by))
        .where(CmdAdvisorySession.id == advisory_id)
    )
    session_obj = result.scalar_one_or_none()
    if not session_obj:
        raise HTTPException(status_code=404, detail="Phiên tư vấn không tồn tại")

    # Permission check
    if user.role == "admin":
        return session_obj

    from app.services.permission_engine import _get_user_permissions
    perms = _get_user_permissions(user)

    if "cmd:advice:read:all" in perms:
        return session_obj
    if "cmd:advice:read:own" in perms and session_obj.created_by_id == user.id:
        return session_obj

    raise HTTPException(status_code=403, detail="Không có quyền xem phiên tư vấn này")


async def list_advices(
    db: AsyncSession,
    user: Employee,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    base_stmt = select(CmdAdvisorySession)
    count_stmt = select(func.count(CmdAdvisorySession.id))

    # Filter by permission
    if user.role != "admin":
        from app.services.permission_engine import _get_user_permissions
        perms = _get_user_permissions(user)
        if "cmd:advice:read:all" not in perms:
            base_stmt = base_stmt.where(CmdAdvisorySession.created_by_id == user.id)
            count_stmt = count_stmt.where(CmdAdvisorySession.created_by_id == user.id)

    # Count
    total = (await db.execute(count_stmt)).scalar() or 0

    # Fetch page
    offset = (page - 1) * page_size
    stmt = (
        base_stmt
        .options(selectinload(CmdAdvisorySession.created_by))
        .order_by(desc(CmdAdvisorySession.created_at))
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }
