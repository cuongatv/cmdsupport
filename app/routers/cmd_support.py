"""
CMD Support Router — advisory endpoints for KHDN product recommendations.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee
from app.services import cmd_support_service
from app.services.auth_service import (
    get_current_user,
    get_current_user_optional,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

CUSTOMER_SEGMENTS = {"sme", "midcom", "public_admin"}
ADVICE_LANGUAGES = {"vi", "en"}


class AdviceCreateRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=500)
    province_code: Optional[str] = Field(None, max_length=10)
    industry_code: Optional[str] = Field(None, max_length=10)
    customer_segment: Optional[str] = Field(
        "sme",
        description="Phân khúc KHDN: sme | midcom | public_admin (mặc định sme)",
    )
    needs: str = Field(min_length=10, max_length=5000)
    additional_context: Optional[str] = Field(None, max_length=5000)
    advice_language: str = Field(
        "vi",
        description="Ngôn ngữ kết quả tư vấn: vi | en (mặc định vi)",
    )
    force_refresh: bool = Field(
        False,
        description="Forçar nova chamada LLM mesmo com cache hit",
    )


class AdviceSummary(BaseModel):
    id: uuid.UUID
    customer_name: str
    province_name: Optional[str] = None
    industry_name: Optional[str] = None
    customer_segment: Optional[str] = None
    status: str
    created_at: datetime
    created_by_name: Optional[str] = None

    model_config = {"from_attributes": True}


class AdviceDetail(AdviceSummary):
    needs: str
    additional_context: Optional[str] = None
    result_json: Optional[dict] = None
    prompt_version: Optional[str] = None
    model_provider: Optional[str] = None
    model_id: Optional[str] = None
    reuse_status: Optional[str] = None
    schema_version: Optional[str] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class AdviceListResponse(BaseModel):
    items: list[AdviceSummary]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_summary(obj) -> AdviceSummary:
    return AdviceSummary(
        id=obj.id,
        customer_name=obj.customer_name,
        province_name=obj.province_name,
        industry_name=obj.industry_name,
        customer_segment=obj.customer_segment,
        status=obj.status,
        created_at=obj.created_at,
        created_by_name=obj.created_by.name if obj.created_by else None,
    )


def _to_detail(obj) -> AdviceDetail:
    return AdviceDetail(
        id=obj.id,
        customer_name=obj.customer_name,
        province_name=obj.province_name,
        industry_name=obj.industry_name,
        customer_segment=obj.customer_segment,
        status=obj.status,
        created_at=obj.created_at,
        created_by_name=obj.created_by.name if obj.created_by else None,
        needs=obj.needs,
        additional_context=obj.additional_context,
        result_json=obj.result_json,
        prompt_version=obj.prompt_version,
        model_provider=obj.model_provider,
        model_id=obj.model_id,
        reuse_status=obj.reuse_status,
        schema_version=obj.schema_version,
        duration_ms=obj.duration_ms,
        error_message=obj.error_message,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/cmd-support/advice", response_model=AdviceDetail)
async def create_advice(
    body: AdviceCreateRequest,
    user: Optional[Employee] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    segment = (body.customer_segment or "sme").lower()
    if segment not in CUSTOMER_SEGMENTS:
        raise HTTPException(
            status_code=400,
            detail="Phân khúc khách hàng không hợp lệ (sme | midcom | public_admin)",
        )
    advice_language = body.advice_language.lower()
    if advice_language not in ADVICE_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="Ngôn ngữ tư vấn không hợp lệ (vi | en)",
        )
    session_obj = await cmd_support_service.create_advice(
        db=db,
        user=user,
        customer_name=body.customer_name,
        province_code=body.province_code,
        industry_code=body.industry_code,
        customer_segment=segment,
        needs=body.needs,
        additional_context=body.additional_context,
        advice_language=advice_language,
        force_refresh=body.force_refresh,
    )
    return _to_detail(session_obj)


@router.get("/cmd-support/advice/{advisory_id}", response_model=AdviceDetail)
async def get_advice(
    advisory_id: uuid.UUID,
    user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session_obj = await cmd_support_service.get_advice(db, user, advisory_id)
    return _to_detail(session_obj)


@router.get("/cmd-support/advice", response_model=AdviceListResponse)
async def list_advices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await cmd_support_service.list_advices(db, user, page, page_size)
    return AdviceListResponse(
        items=[_to_summary(item) for item in result["items"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
    )


@router.get("/cmd-support/options")
async def get_options(
    db: AsyncSession = Depends(get_db),
):
    return await cmd_support_service.list_options(db)


@router.get("/cmd-support/options/provinces")
async def get_provinces(
    db: AsyncSession = Depends(get_db),
):
    return await cmd_support_service.list_provinces(db)


@router.get("/cmd-support/options/industries")
async def get_industries(
    level: Optional[int] = Query(None, ge=1, le=2),
    parent_code: Optional[str] = Query(None, max_length=10),
    db: AsyncSession = Depends(get_db),
):
    return await cmd_support_service.list_industries(db, level=level, parent_code=parent_code)
