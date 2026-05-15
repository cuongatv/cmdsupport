"""
Consulting Rule Service — quy tắc tư vấn theo 3 chiều: sản phẩm, phân khúc, địa bàn.

Rules được admin tạo/sửa và được tự động bơm vào prompt advisory của
`cmd_support_service.create_advice` để bổ sung ngữ cảnh ngoài tri thức wiki.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.consulting_rule_prompts import (
    SYSTEM_PROMPT_VI,
    build_product_persona_prompt,
    build_province_specifics_prompt,
    build_segment_specifics_prompt,
)
from app.database.models import (
    ConsultingRuleProduct,
    ConsultingRuleProvince,
    ConsultingRuleSegment,
    Employee,
    KnowledgeType,
    Province,
    WikiPage,
)

# Hardcoded: phải khớp `CUSTOMER_SEGMENTS` ở app/routers/cmd_support.py
ALLOWED_SEGMENTS: set[str] = {"sme", "midcom", "public_admin"}

SEGMENT_LABELS_VI = {
    "sme": "Doanh nghiệp nhỏ và vừa (SME)",
    "midcom": "Doanh nghiệp trung lớn (Midcom)",
    "public_admin": "Hành chính sự nghiệp",
}


# ---------------------------------------------------------------------------
# Source dropdown — wiki pages + knowledge types
# ---------------------------------------------------------------------------


async def list_product_sources(
    db: AsyncSession,
    knowledge_type_slug: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    """List wiki pages dùng làm dropdown nguồn cho rule sản phẩm.

    `knowledge_type_slug`: nếu truyền, chỉ trả về pages có slug này trong
    `knowledge_type_slugs` array. Nếu None, trả tất cả global pages.
    `search`: filter theo title (ILIKE).
    """
    stmt = (
        select(WikiPage.id, WikiPage.slug, WikiPage.title, WikiPage.knowledge_type_slugs)
        .where(WikiPage.scope_type == "global", WikiPage.orphaned.is_(False))
    )
    if knowledge_type_slug:
        stmt = stmt.where(
            WikiPage.knowledge_type_slugs.any(knowledge_type_slug)
        )
    if search:
        stmt = stmt.where(WikiPage.title.ilike(f"%{search}%"))
    stmt = stmt.order_by(WikiPage.title).limit(limit)
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": str(row.id),
            "slug": row.slug,
            "title": row.title,
            "knowledge_type_slugs": list(row.knowledge_type_slugs or []),
        }
        for row in rows
    ]


async def list_knowledge_types(db: AsyncSession) -> list[dict]:
    """Trả về danh sách knowledge types để filter dropdown nguồn sản phẩm."""
    rows = (
        await db.execute(
            select(KnowledgeType).order_by(KnowledgeType.sort_order, KnowledgeType.name)
        )
    ).scalars().all()
    return [
        {"slug": k.slug, "name": k.name, "color": k.color} for k in rows
    ]


# ---------------------------------------------------------------------------
# Product rules
# ---------------------------------------------------------------------------


async def list_product_rules(db: AsyncSession) -> list[ConsultingRuleProduct]:
    rows = (
        await db.execute(
            select(ConsultingRuleProduct)
            .options(
                selectinload(ConsultingRuleProduct.wiki_page),
                selectinload(ConsultingRuleProduct.created_by),
                selectinload(ConsultingRuleProduct.updated_by),
            )
            .order_by(ConsultingRuleProduct.updated_at.desc())
        )
    ).scalars().all()
    return list(rows)


async def upsert_product_rule(
    db: AsyncSession,
    user: Employee,
    *,
    wiki_page_id: Optional[uuid.UUID],
    product_name_custom: Optional[str],
    basic_info: Optional[str],
    customer_persona: str,
    rule_id: Optional[uuid.UUID] = None,
) -> ConsultingRuleProduct:
    if (wiki_page_id is None) == (product_name_custom is None):
        raise HTTPException(
            status_code=400,
            detail="Phải chọn 1 trong 2: wiki_page_id hoặc product_name_custom",
        )

    if wiki_page_id is not None:
        exists = (
            await db.execute(select(WikiPage.id).where(WikiPage.id == wiki_page_id))
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=404, detail="Wiki page không tồn tại")

    if rule_id is not None:
        rule = (
            await db.execute(
                select(ConsultingRuleProduct).where(ConsultingRuleProduct.id == rule_id)
            )
        ).scalar_one_or_none()
        if rule is None:
            raise HTTPException(status_code=404, detail="Quy tắc không tồn tại")
        rule.wiki_page_id = wiki_page_id
        rule.product_name_custom = (
            product_name_custom.strip() if product_name_custom else None
        )
        rule.basic_info = basic_info
        rule.customer_persona = customer_persona
        rule.updated_by_id = user.id
    else:
        # Tránh insert trùng — kiểm tra trước
        if wiki_page_id is not None:
            dup = (
                await db.execute(
                    select(ConsultingRuleProduct.id).where(
                        ConsultingRuleProduct.wiki_page_id == wiki_page_id
                    )
                )
            ).scalar_one_or_none()
        else:
            assert product_name_custom is not None  # XOR check above guarantees this
            dup = (
                await db.execute(
                    select(ConsultingRuleProduct.id).where(
                        ConsultingRuleProduct.product_name_custom
                        == product_name_custom.strip()
                    )
                )
            ).scalar_one_or_none()
        if dup is not None:
            raise HTTPException(
                status_code=409,
                detail="Đã tồn tại quy tắc cho sản phẩm này (1-1)",
            )
        rule = ConsultingRuleProduct(
            wiki_page_id=wiki_page_id,
            product_name_custom=(
                product_name_custom.strip() if product_name_custom else None
            ),
            basic_info=basic_info,
            customer_persona=customer_persona,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


async def delete_product_rule(
    db: AsyncSession, rule_id: uuid.UUID
) -> None:
    rule = (
        await db.execute(
            select(ConsultingRuleProduct).where(ConsultingRuleProduct.id == rule_id)
        )
    ).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Quy tắc không tồn tại")
    await db.delete(rule)
    await db.flush()


# ---------------------------------------------------------------------------
# Segment rules
# ---------------------------------------------------------------------------


async def list_segment_rules(db: AsyncSession) -> list[ConsultingRuleSegment]:
    rows = (
        await db.execute(
            select(ConsultingRuleSegment)
            .options(
                selectinload(ConsultingRuleSegment.created_by),
                selectinload(ConsultingRuleSegment.updated_by),
            )
            .order_by(ConsultingRuleSegment.segment)
        )
    ).scalars().all()
    return list(rows)


async def upsert_segment_rule(
    db: AsyncSession,
    user: Employee,
    *,
    segment: str,
    basic_info: Optional[str],
    segment_specifics: str,
) -> ConsultingRuleSegment:
    seg = segment.lower().strip()
    if seg not in ALLOWED_SEGMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"segment phải thuộc {sorted(ALLOWED_SEGMENTS)}",
        )
    rule = (
        await db.execute(
            select(ConsultingRuleSegment).where(ConsultingRuleSegment.segment == seg)
        )
    ).scalar_one_or_none()
    if rule is None:
        rule = ConsultingRuleSegment(
            segment=seg,
            basic_info=basic_info,
            segment_specifics=segment_specifics,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(rule)
    else:
        rule.basic_info = basic_info
        rule.segment_specifics = segment_specifics
        rule.updated_by_id = user.id
    await db.flush()
    await db.refresh(rule)
    return rule


async def delete_segment_rule(db: AsyncSession, rule_id: uuid.UUID) -> None:
    rule = (
        await db.execute(
            select(ConsultingRuleSegment).where(ConsultingRuleSegment.id == rule_id)
        )
    ).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Quy tắc không tồn tại")
    await db.delete(rule)
    await db.flush()


# ---------------------------------------------------------------------------
# Province rules
# ---------------------------------------------------------------------------


async def list_province_rules(db: AsyncSession) -> list[ConsultingRuleProvince]:
    rows = (
        await db.execute(
            select(ConsultingRuleProvince)
            .options(
                selectinload(ConsultingRuleProvince.province),
                selectinload(ConsultingRuleProvince.created_by),
                selectinload(ConsultingRuleProvince.updated_by),
            )
            .order_by(ConsultingRuleProvince.updated_at.desc())
        )
    ).scalars().all()
    return list(rows)


async def upsert_province_rule(
    db: AsyncSession,
    user: Employee,
    *,
    province_id: uuid.UUID,
    basic_info: Optional[str],
    province_specifics: str,
) -> ConsultingRuleProvince:
    province = (
        await db.execute(select(Province).where(Province.id == province_id))
    ).scalar_one_or_none()
    if province is None:
        raise HTTPException(status_code=404, detail="Tỉnh/thành không tồn tại")

    rule = (
        await db.execute(
            select(ConsultingRuleProvince).where(
                ConsultingRuleProvince.province_id == province_id
            )
        )
    ).scalar_one_or_none()
    if rule is None:
        rule = ConsultingRuleProvince(
            province_id=province_id,
            basic_info=basic_info,
            province_specifics=province_specifics,
            created_by_id=user.id,
            updated_by_id=user.id,
        )
        db.add(rule)
    else:
        rule.basic_info = basic_info
        rule.province_specifics = province_specifics
        rule.updated_by_id = user.id
    await db.flush()
    await db.refresh(rule)
    return rule


async def delete_province_rule(db: AsyncSession, rule_id: uuid.UUID) -> None:
    rule = (
        await db.execute(
            select(ConsultingRuleProvince).where(ConsultingRuleProvince.id == rule_id)
        )
    ).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="Quy tắc không tồn tại")
    await db.delete(rule)
    await db.flush()


# ---------------------------------------------------------------------------
# AI assist (gọi LLM để gợi ý nội dung)
# ---------------------------------------------------------------------------


async def _call_llm(db: AsyncSession, prompt: str) -> str:
    from app.ai.registry import ProviderRegistry

    registry = ProviderRegistry(db)
    try:
        llm = await registry.get_advisor_llm()
    except ValueError:
        raise HTTPException(
            status_code=503,
            detail="Chưa cấu hình AI provider trong Cài đặt",
        )
    try:
        return await llm.generate(
            prompt=prompt,
            system=SYSTEM_PROMPT_VI,
            max_tokens=1024,
            temperature=0.3,
        )
    except Exception as exc:
        logger.error(f"Consulting rule AI assist error: {exc}")
        raise HTTPException(
            status_code=502,
            detail=f"Lỗi gọi LLM: {exc}",
        ) from exc


async def ai_assist_product(
    db: AsyncSession, *, product_name: str, basic_info: str
) -> str:
    if not basic_info.strip():
        raise HTTPException(
            status_code=400, detail="Thông tin cơ bản là bắt buộc khi dùng AI hỗ trợ"
        )
    prompt = build_product_persona_prompt(
        product_name=product_name.strip() or "(không rõ tên)",
        basic_info=basic_info.strip(),
    )
    return (await _call_llm(db, prompt)).strip()


async def ai_assist_segment(
    db: AsyncSession, *, segment: str, basic_info: str
) -> str:
    if not basic_info.strip():
        raise HTTPException(
            status_code=400, detail="Thông tin cơ bản là bắt buộc khi dùng AI hỗ trợ"
        )
    seg = segment.lower().strip()
    label = SEGMENT_LABELS_VI.get(seg, seg)
    prompt = build_segment_specifics_prompt(
        segment_label=label, basic_info=basic_info.strip()
    )
    return (await _call_llm(db, prompt)).strip()


async def ai_assist_province(
    db: AsyncSession, *, province_id: uuid.UUID, basic_info: str
) -> str:
    if not basic_info.strip():
        raise HTTPException(
            status_code=400, detail="Thông tin cơ bản là bắt buộc khi dùng AI hỗ trợ"
        )
    province = (
        await db.execute(select(Province).where(Province.id == province_id))
    ).scalar_one_or_none()
    if province is None:
        raise HTTPException(status_code=404, detail="Tỉnh/thành không tồn tại")
    prompt = build_province_specifics_prompt(
        province_name=province.name, basic_info=basic_info.strip()
    )
    return (await _call_llm(db, prompt)).strip()


# ---------------------------------------------------------------------------
# Resolution helpers — used by cmd_support_service to inject rules into prompt
# ---------------------------------------------------------------------------


async def gather_applicable_rules_text(
    db: AsyncSession,
    *,
    segment: Optional[str],
    province_code: Optional[str],
    wiki_page_ids: Optional[list[uuid.UUID]] = None,
) -> str:
    """Build the `### QUY TẮC TƯ VẤN ÁP DỤNG` block injected into advisory prompt.

    Returns empty string if no rules match — caller should skip the block.
    Rules là policy do admin định nghĩa, KHÔNG cần citation, nhưng prompt sẽ
    hướng dẫn LLM coi đây là ngữ cảnh bổ sung (không phải nguồn để cite).
    """
    blocks: list[str] = []

    # Segment rule
    if segment:
        seg_rule = (
            await db.execute(
                select(ConsultingRuleSegment).where(
                    ConsultingRuleSegment.segment == segment.lower()
                )
            )
        ).scalar_one_or_none()
        if seg_rule and seg_rule.segment_specifics.strip():
            label = SEGMENT_LABELS_VI.get(seg_rule.segment, seg_rule.segment)
            blocks.append(
                f"#### Theo phân khúc khách hàng — {label}\n"
                f"{seg_rule.segment_specifics.strip()}"
            )

    # Province rule
    if province_code:
        province = (
            await db.execute(
                select(Province).where(Province.code == province_code)
            )
        ).scalar_one_or_none()
        if province:
            prov_rule = (
                await db.execute(
                    select(ConsultingRuleProvince).where(
                        ConsultingRuleProvince.province_id == province.id
                    )
                )
            ).scalar_one_or_none()
            if prov_rule and prov_rule.province_specifics.strip():
                blocks.append(
                    f"#### Theo địa bàn — {province.name}\n"
                    f"{prov_rule.province_specifics.strip()}"
                )

    # Product rules — match via wiki pages retrieved by RAG
    if wiki_page_ids:
        prod_rules = (
            await db.execute(
                select(ConsultingRuleProduct)
                .options(selectinload(ConsultingRuleProduct.wiki_page))
                .where(ConsultingRuleProduct.wiki_page_id.in_(wiki_page_ids))
            )
        ).scalars().all()
        for pr in prod_rules:
            if not pr.customer_persona.strip():
                continue
            name = (
                pr.wiki_page.title
                if pr.wiki_page is not None
                else (pr.product_name_custom or "Sản phẩm")
            )
            blocks.append(
                f"#### Theo sản phẩm/chính sách — {name}\n"
                f"Chân dung khách hàng tiềm năng:\n{pr.customer_persona.strip()}"
            )

    if not blocks:
        return ""
    return (
        "### QUY TẮC TƯ VẤN ÁP DỤNG\n"
        "Các quy tắc dưới đây do admin BIDV định nghĩa, dùng LÀM NGỮ CẢNH BỔ "
        "SUNG khi tư vấn (không phải tài liệu để cite trong citations).\n\n"
        + "\n\n".join(blocks)
    )
