"""
CMD Support Service — advisory session creation, retrieval, and listing.
"""

import copy
import json
import re
import time
import uuid
from typing import Optional

from fastapi import HTTPException
from loguru import logger
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import object_session, selectinload

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
from app.services.cmd_advisory_fingerprint import (
    compute_advisory_fingerprint,
    compute_source_snapshot_hash,
)

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
# Advisory reuse helpers (Fix #1, #5)
# ---------------------------------------------------------------------------

# Fix #4: every v2 product array carries a citations[] list; items missing
# citations are dropped into coverage_gaps to prevent prompt-injection cache
# poisoning of unauthenticated advisory submissions.
_V2_CITED_ARRAYS: tuple[str, ...] = (
    "primary_products",
    "cross_sell_products",
    "upsell_products",
    "operations_products",
    "digital_channels",
    "policies_incentives",
)


async def _find_reusable_session(
    db: AsyncSession,
    input_fingerprint: str,
    source_snapshot_hash: str,
) -> Optional[CmdAdvisorySession]:
    """Find a ready, non-NULL-result session whose snapshot matches exactly.

    Fix #5: ``result_json IS NOT NULL`` guard prevents the reuse path from
    returning a session that would crash the frontend on render.

    Eager-load ``created_by`` so ``_build_reused_response`` can ``expunge``
    the row without breaking the router's later access to ``obj.created_by.name``
    (which would otherwise lazy-load and raise ``DetachedInstanceError``).
    """
    return (
        await db.execute(
            select(CmdAdvisorySession)
            .options(selectinload(CmdAdvisorySession.created_by))
            .where(
                CmdAdvisorySession.input_fingerprint == input_fingerprint,
                CmdAdvisorySession.status == "ready",
                CmdAdvisorySession.result_json.isnot(None),
                CmdAdvisorySession.source_snapshot_hash == source_snapshot_hash,
            )
            .order_by(desc(CmdAdvisorySession.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()


async def _find_stale_snapshot_session(
    db: AsyncSession,
    input_fingerprint: str,
    source_snapshot_hash: str,
) -> Optional[CmdAdvisorySession]:
    """Find a fingerprint match whose snapshot is stale (drives reuse_status='refreshed')."""
    return (
        await db.execute(
            select(CmdAdvisorySession)
            .where(
                CmdAdvisorySession.input_fingerprint == input_fingerprint,
                CmdAdvisorySession.status == "ready",
                CmdAdvisorySession.source_snapshot_hash != source_snapshot_hash,
            )
            .order_by(desc(CmdAdvisorySession.created_at))
            .limit(1)
        )
    ).scalar_one_or_none()


def _build_reused_response(
    existing: CmdAdvisorySession,
    *,
    customer_name: str,
    province_name: Optional[str],
    industry_name: Optional[str],
    needs: str,
    language: str,
) -> CmdAdvisorySession:
    """Build a transient response object for a cache hit.

    Fix #1: ``customer_name`` is intentionally NOT part of the fingerprint
    (per cmd_advisory_fingerprint contract). Returning ``existing`` verbatim
    would leak the *original* requester's customer name and context to the
    current requester. We expunge the row from the session so SQLAlchemy
    won't UPDATE the persisted row, then deep-copy ``result_json`` and
    overwrite the customer-bound fields with the current request's values.
    """
    # Detach so subsequent attribute writes don't flush back to the original row
    db_session = object_session(existing)
    if db_session is not None:
        db_session.expunge(existing)

    if isinstance(existing.result_json, dict):
        cloned = copy.deepcopy(existing.result_json)
        cloned["advice_language"] = language
        ctx = cloned.get("customer_context")
        if not isinstance(ctx, dict):
            ctx = {}
        ctx["name"] = customer_name
        ctx["province"] = province_name
        ctx["industry"] = industry_name
        ctx["detected_needs"] = [needs]
        cloned["customer_context"] = ctx
        existing.result_json = cloned

    existing.customer_name = customer_name
    existing.province_name = province_name
    existing.industry_name = industry_name
    existing.needs = needs
    existing.reuse_status = "reused"
    return existing


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

DEFAULT_DISCLAIMERS = {
    "vi": "Cần RM xác minh điều kiện cấp tín dụng theo quy định BIDV hiện hành. Kết quả tư vấn chỉ mang tính tham khảo.",
    "en": "The RM must verify credit eligibility under current BIDV regulations. This advisory result is for reference only.",
}

V2_REQUIRED_DEFAULTS: dict[str, object] = {
    "executive_thesis": "",
    "primary_products": [],
    "cross_sell_products": [],
    "upsell_products": [],
    "operations_products": [],
    "digital_channels": [],
    "policies_incentives": [],
    "bundle_advantages": "",
    "schema_version": "v2.0",
}


def _normalize_v2_result(result_json: dict[str, object], language: str) -> dict[str, object]:
    """Ensure a CMD advisory result carries the v2 response contract."""
    normalized = dict(result_json)
    for key, default_value in V2_REQUIRED_DEFAULTS.items():
        if key not in normalized or normalized[key] is None:
            normalized[key] = list(default_value) if isinstance(default_value, list) else default_value
    normalized["schema_version"] = "v2.0"
    normalized["advice_language"] = language
    return normalized


async def create_advice(
    db: AsyncSession,
    user: Optional[Employee],
    customer_name: str,
    province_code: Optional[str],
    industry_code: Optional[str],
    needs: str,
    additional_context: Optional[str],
    customer_segment: Optional[str] = "sme",
    advice_language: str = "vi",
    force_refresh: bool = False,
) -> CmdAdvisorySession:
    t0 = time.time()
    segment = (customer_segment or "sme").lower()
    language = advice_language if advice_language in DEFAULT_DISCLAIMERS else "vi"
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

    # Check AI providers.
    # Operator note: advisory LLM/embedding providers are resolved from the
    # Settings-backed ProviderRegistry — there is no separate "advisory
    # provider" setting. Changing the active LLM provider/model in Admin →
    # Settings invalidates any prior advisory cache entry whose fingerprint
    # was bound to the old provider/model (see cmd_advisory_fingerprint.py).
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
    llm_config = await registry._load_config("llm")

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
    # Fix #2: include WikiPage.version + updated_at so an editor's content edit
    # invalidates the cache even when the set of retrieved page UUIDs is unchanged.
    retrieved_page_identity = [
        (page.id, page.version, page.updated_at) for page, _ in results
    ]
    input_fingerprint = compute_advisory_fingerprint(
        customer_segment=segment,
        province_code=province_code,
        industry_code=industry_code,
        needs=needs,
        additional_context=additional_context,
        advice_language=language,
        prompt_version=PROMPT_VERSION,
        model_provider=llm_config.provider.value,
        model_id=llm_config.model_id,
    )
    source_snapshot_hash = compute_source_snapshot_hash(retrieved_page_identity)
    reuse_status = "new"
    refresh_reason = None

    if not force_refresh:
        existing_session = await _find_reusable_session(
            db, input_fingerprint, source_snapshot_hash
        )
        if existing_session is not None:
            return _build_reused_response(
                existing_session,
                customer_name=customer_name,
                province_name=province_name,
                industry_name=industry_name,
                needs=needs,
                language=language,
            )
        # No exact match: was there a stale-snapshot row for this fingerprint?
        stale_session = await _find_stale_snapshot_session(
            db, input_fingerprint, source_snapshot_hash
        )
        if stale_session is not None:
            reuse_status = "refreshed"
            refresh_reason = "source_snapshot_hash_changed"

    _default_disclaimer = DEFAULT_DISCLAIMERS[language]

    # Short-circuit: no wiki results → skip LLM call
    if len(results) == 0:
        duration_ms = int((time.time() - t0) * 1000)
        result_json = {
            "advice_language": language,
            "customer_context": {
                "name": customer_name,
                "province": province_name,
                "industry": industry_name,
                "detected_needs": [needs],
            },
            "analysis": (
                "No related documents were found in the internal knowledge base to analyze this customer need."
                if language == "en"
                else "Chưa có tài liệu liên quan trong kho tri thức nội bộ để phân tích nhu cầu khách hàng."
            ),
            "recommendations": [],
            "red_flags": [],
            "offer_materials": [],
            "follow_up_questions": [],
            "coverage_gaps": [
                "No related documents were found in the internal knowledge base"
                if language == "en"
                else "Chưa có tài liệu liên quan trong kho tri thức nội bộ"
            ],
            "rm_disclaimer": _default_disclaimer,
        }
        result_json = _normalize_v2_result(result_json, language)
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
            model_provider=llm_config.provider.value,
            model_id=llm_config.model_id,
            prompt_version=PROMPT_VERSION,
            scope_type="global",
            status="ready",
            input_fingerprint=input_fingerprint,
            source_snapshot_hash=source_snapshot_hash,
            retrieval_snapshot=context_blocks,
            reuse_status=reuse_status,
            refresh_reason=refresh_reason,
            schema_version="v2.0",
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
        advice_language=language,
    )

    # Call LLM
    status = "ready"
    error_message = None
    result_json = None
    raw_output = ""

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
        if not isinstance(result_json, dict):
            raise json.JSONDecodeError("LLM output root is not a JSON object", cleaned, 0)
    except json.JSONDecodeError:
        status = "failed"
        error_message = "LLM output không hợp lệ JSON"
        result_json = {
            "schema_version": "v1",
            "advice_language": language,
            "customer_context": {
                "name": customer_name,
                "province": province_name,
                "industry": industry_name,
                "detected_needs": [needs],
            },
            "analysis": "",
            "recommendations": [],
            "red_flags": [],
            "offer_materials": [],
            "follow_up_questions": [],
            "coverage_gaps": ["LLM output không hợp lệ JSON"],
            "rm_disclaimer": _default_disclaimer,
            "raw": raw_output,
        }
    except Exception as e:
        status = "failed"
        error_message = f"Lỗi gọi LLM: {str(e)}"
        logger.error(f"CMD advice LLM error: {e}")

    # Post-LLM validation (grounding hardening)
    if status == "ready" and isinstance(result_json, dict):
        result_json["advice_language"] = language

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
                if not isinstance(rec, dict):
                    dropped += 1
                    continue
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
                existing_gaps = result_json.get("coverage_gaps", [])
                gaps = existing_gaps if isinstance(existing_gaps, list) else []
                if language == "en":
                    gaps.append(f"Removed {dropped} recommendation(s) because citations were missing")
                else:
                    gaps.append(f"Đã loại {dropped} gợi ý vì thiếu trích dẫn")
                result_json["coverage_gaps"] = gaps

        # Fix #4: drop items in v2 product arrays that lack citations.
        # Without this, prompt-injected v2 arrays (e.g. fake "primary_products"
        # with empty citations) would poison the cache for downstream RMs.
        for array_name in _V2_CITED_ARRAYS:
            items = result_json.get(array_name)
            if not isinstance(items, list):
                continue
            valid_items = []
            v2_dropped = 0
            for item in items:
                if not isinstance(item, dict):
                    v2_dropped += 1
                    continue
                v2_cits = item.get("citations")
                if isinstance(v2_cits, list) and len(v2_cits) > 0:
                    valid_items.append(item)
                else:
                    v2_dropped += 1
            result_json[array_name] = valid_items
            if v2_dropped > 0:
                logger.warning(
                    f"CMD advice v2: dropped {v2_dropped} item(s) from {array_name} (missing citations)"
                )
                existing_gaps = result_json.get("coverage_gaps", [])
                gaps = existing_gaps if isinstance(existing_gaps, list) else []
                if language == "en":
                    gaps.append(
                        f"Removed {v2_dropped} item(s) from {array_name} because citations were missing"
                    )
                else:
                    gaps.append(
                        f"Đã loại {v2_dropped} mục khỏi {array_name} vì thiếu trích dẫn"
                    )
                result_json["coverage_gaps"] = gaps

        # Ensure rm_disclaimer has default value
        if not result_json.get("rm_disclaimer"):
            result_json["rm_disclaimer"] = _default_disclaimer

        # Ensure red_flags field exists
        if "red_flags" not in result_json:
            result_json["red_flags"] = []

        result_json = _normalize_v2_result(result_json, language)

    duration_ms = int((time.time() - t0) * 1000)

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
        input_fingerprint=input_fingerprint,
        source_snapshot_hash=source_snapshot_hash,
        retrieval_snapshot=context_blocks,
        reuse_status=reuse_status,
        refresh_reason=refresh_reason,
        schema_version=result_json.get("schema_version") if isinstance(result_json, dict) else None,
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

    # Fix #3: partial UNIQUE on (input_fingerprint) WHERE status='ready' may
    # reject this insert if a parallel request committed first. In that case
    # roll back our row and reuse theirs (we already paid the LLM cost; logging
    # it as a near-miss is acceptable noise compared to a 500 to the client).
    try:
        await db.flush()
    except IntegrityError as exc:
        # Only the partial unique fingerprint index is expected here.
        if status != "ready" or input_fingerprint is None:
            raise
        await db.rollback()
        logger.warning(
            "CMD advice: lost reuse race for fingerprint=%s — reusing winner's session",
            input_fingerprint,
        )
        winner = await _find_reusable_session(
            db, input_fingerprint, source_snapshot_hash
        )
        if winner is not None:
            return _build_reused_response(
                winner,
                customer_name=customer_name,
                province_name=province_name,
                industry_name=industry_name,
                needs=needs,
                language=language,
            )
        # Winner row vanished between IntegrityError and re-query. Surface the
        # original conflict rather than silently inventing data.
        raise HTTPException(
            status_code=409,
            detail="Advisory generation conflict; please retry",
        ) from exc
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


async def get_hq_contact_for_province(
    db: AsyncSession,
    province_code: Optional[str],
) -> Optional[Employee]:
    """Resolve the HQ contact officer for a province code, eager-loaded.

    Returned object has `department` populated so callers can build a
    contact card without further queries. None when:
      - province_code is missing
      - province row not found
      - province has no assignee
      - assignee is inactive (we hide inactive officers from advisory output)
    """
    if not province_code:
        return None
    stmt = (
        select(Province)
        .options(
            selectinload(Province.assigned_employee).selectinload(Employee.department)
        )
        .where(Province.code == province_code)
    )
    province = (await db.execute(stmt)).scalar_one_or_none()
    if province is None:
        return None
    emp = province.assigned_employee
    if emp is None or not emp.is_active:
        return None
    return emp


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
