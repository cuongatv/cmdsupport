"""
Consulting Rules Router — quy tắc tư vấn theo 3 chiều.

Mount: /api/cmd-support/rules
Permissions:
  - cmd:rules:read  → list/get
  - cmd:rules:write → create/update/delete + AI assist
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee
from app.services import consulting_rule_service as svc
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission

router = APIRouter(prefix="/cmd-support/rules")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class _UserBrief(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class ProductSourceOut(BaseModel):
    id: str
    slug: str
    title: str
    knowledge_type_slugs: list[str]


class KnowledgeTypeOut(BaseModel):
    slug: str
    name: str
    color: Optional[str] = None


class ProvinceOption(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    short_name: str


class ProductRuleOut(BaseModel):
    id: uuid.UUID
    wiki_page_id: Optional[uuid.UUID]
    wiki_page_title: Optional[str] = None
    wiki_page_slug: Optional[str] = None
    product_name_custom: Optional[str]
    basic_info: Optional[str]
    customer_persona: str
    created_by: Optional[_UserBrief] = None
    updated_by: Optional[_UserBrief] = None
    created_at: datetime
    updated_at: datetime


class ProductRuleUpsert(BaseModel):
    wiki_page_id: Optional[uuid.UUID] = None
    product_name_custom: Optional[str] = Field(None, max_length=300)
    basic_info: Optional[str] = Field(None, max_length=10000)
    customer_persona: str = Field(min_length=1, max_length=10000)


class SegmentRuleOut(BaseModel):
    id: uuid.UUID
    segment: str
    basic_info: Optional[str]
    segment_specifics: str
    created_by: Optional[_UserBrief] = None
    updated_by: Optional[_UserBrief] = None
    created_at: datetime
    updated_at: datetime


class SegmentRuleUpsert(BaseModel):
    segment: str = Field(min_length=1, max_length=30)
    basic_info: Optional[str] = Field(None, max_length=10000)
    segment_specifics: str = Field(min_length=1, max_length=10000)


class ProvinceRuleOut(BaseModel):
    id: uuid.UUID
    province_id: uuid.UUID
    province_name: Optional[str] = None
    province_code: Optional[str] = None
    basic_info: Optional[str]
    province_specifics: str
    created_by: Optional[_UserBrief] = None
    updated_by: Optional[_UserBrief] = None
    created_at: datetime
    updated_at: datetime


class ProvinceRuleUpsert(BaseModel):
    province_id: uuid.UUID
    basic_info: Optional[str] = Field(None, max_length=10000)
    province_specifics: str = Field(min_length=1, max_length=10000)


class AiAssistProductRequest(BaseModel):
    product_name: str = Field(min_length=1, max_length=300)
    basic_info: str = Field(min_length=1, max_length=10000)


class AiAssistSegmentRequest(BaseModel):
    segment: str = Field(min_length=1, max_length=30)
    basic_info: str = Field(min_length=1, max_length=10000)


class AiAssistProvinceRequest(BaseModel):
    province_id: uuid.UUID
    basic_info: str = Field(min_length=1, max_length=10000)


class AiAssistResponse(BaseModel):
    generated_text: str


# ---------------------------------------------------------------------------
# Mappers
# ---------------------------------------------------------------------------


def _map_product(rule) -> ProductRuleOut:
    return ProductRuleOut(
        id=rule.id,
        wiki_page_id=rule.wiki_page_id,
        wiki_page_title=rule.wiki_page.title if rule.wiki_page else None,
        wiki_page_slug=rule.wiki_page.slug if rule.wiki_page else None,
        product_name_custom=rule.product_name_custom,
        basic_info=rule.basic_info,
        customer_persona=rule.customer_persona,
        created_by=_UserBrief.model_validate(rule.created_by) if rule.created_by else None,
        updated_by=_UserBrief.model_validate(rule.updated_by) if rule.updated_by else None,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _map_segment(rule) -> SegmentRuleOut:
    return SegmentRuleOut(
        id=rule.id,
        segment=rule.segment,
        basic_info=rule.basic_info,
        segment_specifics=rule.segment_specifics,
        created_by=_UserBrief.model_validate(rule.created_by) if rule.created_by else None,
        updated_by=_UserBrief.model_validate(rule.updated_by) if rule.updated_by else None,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _map_province(rule) -> ProvinceRuleOut:
    return ProvinceRuleOut(
        id=rule.id,
        province_id=rule.province_id,
        province_name=rule.province.name if rule.province else None,
        province_code=rule.province.code if rule.province else None,
        basic_info=rule.basic_info,
        province_specifics=rule.province_specifics,
        created_by=_UserBrief.model_validate(rule.created_by) if rule.created_by else None,
        updated_by=_UserBrief.model_validate(rule.updated_by) if rule.updated_by else None,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


# ---------------------------------------------------------------------------
# Source helpers
# ---------------------------------------------------------------------------


@router.get("/sources/wiki-pages", response_model=list[ProductSourceOut])
async def list_wiki_sources(
    knowledge_type_slug: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: Employee = require_permission("cmd:rules:read"),
):
    return await svc.list_product_sources(
        db, knowledge_type_slug=knowledge_type_slug, search=search
    )


@router.get("/sources/knowledge-types", response_model=list[KnowledgeTypeOut])
async def list_knowledge_types(
    db: AsyncSession = Depends(get_db),
    _: Employee = require_permission("cmd:rules:read"),
):
    return await svc.list_knowledge_types(db)


@router.get("/sources/provinces", response_model=list[ProvinceOption])
async def list_provinces_with_id(
    db: AsyncSession = Depends(get_db),
    _: Employee = require_permission("cmd:rules:read"),
):
    """Trả về danh sách tỉnh/thành kèm id để dùng cho rule province."""
    from sqlalchemy import select as _sel

    from app.database.models import Province

    rows = (
        await db.execute(_sel(Province).order_by(Province.sort_order))
    ).scalars().all()
    return [
        ProvinceOption(
            id=p.id, code=p.code, name=p.name, short_name=p.short_name
        )
        for p in rows
    ]


# ---------------------------------------------------------------------------
# Product rules CRUD
# ---------------------------------------------------------------------------


@router.get("/products", response_model=list[ProductRuleOut])
async def list_products(
    db: AsyncSession = Depends(get_db),
    _: Employee = require_permission("cmd:rules:read"),
):
    rules = await svc.list_product_rules(db)
    return [_map_product(r) for r in rules]


@router.post("/products", response_model=ProductRuleOut)
async def create_product(
    body: ProductRuleUpsert,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("cmd:rules:write"),
):
    rule = await svc.upsert_product_rule(
        db,
        user,
        wiki_page_id=body.wiki_page_id,
        product_name_custom=body.product_name_custom,
        basic_info=body.basic_info,
        customer_persona=body.customer_persona,
    )
    await log_audit(
        db, user,
        action="create",
        resource_type="consulting_rule_product",
        resource_id=str(rule.id),
        reason=f"wiki_page_id={rule.wiki_page_id}; custom={rule.product_name_custom}",
    )
    # Reload with relationships for response
    rules = await svc.list_product_rules(db)
    found = next((r for r in rules if r.id == rule.id), rule)
    return _map_product(found)


@router.put("/products/{rule_id}", response_model=ProductRuleOut)
async def update_product(
    rule_id: uuid.UUID,
    body: ProductRuleUpsert,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("cmd:rules:write"),
):
    rule = await svc.upsert_product_rule(
        db,
        user,
        wiki_page_id=body.wiki_page_id,
        product_name_custom=body.product_name_custom,
        basic_info=body.basic_info,
        customer_persona=body.customer_persona,
        rule_id=rule_id,
    )
    await log_audit(
        db, user,
        action="update",
        resource_type="consulting_rule_product",
        resource_id=str(rule.id),
        reason=f"wiki_page_id={rule.wiki_page_id}; custom={rule.product_name_custom}",
    )
    rules = await svc.list_product_rules(db)
    found = next((r for r in rules if r.id == rule.id), rule)
    return _map_product(found)


@router.delete("/products/{rule_id}", status_code=204)
async def delete_product(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("cmd:rules:write"),
):
    await svc.delete_product_rule(db, rule_id)
    await log_audit(
        db, user,
        action="delete",
        resource_type="consulting_rule_product",
        resource_id=str(rule_id),
        reason="deleted",
    )


@router.post("/products/ai-assist", response_model=AiAssistResponse)
async def ai_assist_product(
    body: AiAssistProductRequest,
    db: AsyncSession = Depends(get_db),
    _: Employee = require_permission("cmd:rules:write"),
):
    text = await svc.ai_assist_product(
        db, product_name=body.product_name, basic_info=body.basic_info
    )
    return AiAssistResponse(generated_text=text)


# ---------------------------------------------------------------------------
# Segment rules CRUD
# ---------------------------------------------------------------------------


@router.get("/segments", response_model=list[SegmentRuleOut])
async def list_segments(
    db: AsyncSession = Depends(get_db),
    _: Employee = require_permission("cmd:rules:read"),
):
    rules = await svc.list_segment_rules(db)
    return [_map_segment(r) for r in rules]


@router.post("/segments", response_model=SegmentRuleOut)
async def upsert_segment(
    body: SegmentRuleUpsert,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("cmd:rules:write"),
):
    rule = await svc.upsert_segment_rule(
        db,
        user,
        segment=body.segment,
        basic_info=body.basic_info,
        segment_specifics=body.segment_specifics,
    )
    await log_audit(
        db, user,
        action="upsert",
        resource_type="consulting_rule_segment",
        resource_id=str(rule.id),
        reason=f"segment={rule.segment}",
    )
    return _map_segment(rule)


@router.delete("/segments/{rule_id}", status_code=204)
async def delete_segment(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("cmd:rules:write"),
):
    await svc.delete_segment_rule(db, rule_id)
    await log_audit(
        db, user,
        action="delete",
        resource_type="consulting_rule_segment",
        resource_id=str(rule_id),
        reason="deleted",
    )


@router.post("/segments/ai-assist", response_model=AiAssistResponse)
async def ai_assist_segment(
    body: AiAssistSegmentRequest,
    db: AsyncSession = Depends(get_db),
    _: Employee = require_permission("cmd:rules:write"),
):
    text = await svc.ai_assist_segment(
        db, segment=body.segment, basic_info=body.basic_info
    )
    return AiAssistResponse(generated_text=text)


# ---------------------------------------------------------------------------
# Province rules CRUD
# ---------------------------------------------------------------------------


@router.get("/provinces", response_model=list[ProvinceRuleOut])
async def list_provinces(
    db: AsyncSession = Depends(get_db),
    _: Employee = require_permission("cmd:rules:read"),
):
    rules = await svc.list_province_rules(db)
    return [_map_province(r) for r in rules]


@router.post("/provinces", response_model=ProvinceRuleOut)
async def upsert_province(
    body: ProvinceRuleUpsert,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("cmd:rules:write"),
):
    rule = await svc.upsert_province_rule(
        db,
        user,
        province_id=body.province_id,
        basic_info=body.basic_info,
        province_specifics=body.province_specifics,
    )
    await log_audit(
        db, user,
        action="upsert",
        resource_type="consulting_rule_province",
        resource_id=str(rule.id),
        reason=f"province_id={rule.province_id}",
    )
    rules = await svc.list_province_rules(db)
    found = next((r for r in rules if r.id == rule.id), rule)
    return _map_province(found)


@router.delete("/provinces/{rule_id}", status_code=204)
async def delete_province(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("cmd:rules:write"),
):
    await svc.delete_province_rule(db, rule_id)
    await log_audit(
        db, user,
        action="delete",
        resource_type="consulting_rule_province",
        resource_id=str(rule_id),
        reason="deleted",
    )


@router.post("/provinces/ai-assist", response_model=AiAssistResponse)
async def ai_assist_province(
    body: AiAssistProvinceRequest,
    db: AsyncSession = Depends(get_db),
    _: Employee = require_permission("cmd:rules:write"),
):
    text = await svc.ai_assist_province(
        db, province_id=body.province_id, basic_info=body.basic_info
    )
    return AiAssistResponse(generated_text=text)
