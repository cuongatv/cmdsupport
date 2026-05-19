# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false
"""Wiki classification audit metadata persistence (T3).

Verifies that ``wiki_service.apply_create`` persists the four taxonomy audit
columns added by migration ``038_wiki_taxonomy_classification`` and that
``page_type`` plus the slugs list stay exactly as supplied. Also asserts the
no-body-leak invariant: a sentinel marker placed in the page body MUST NOT
appear in any classification audit field.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WikiPage
from app.services import wiki_service

pytestmark = pytest.mark.asyncio

BODY_SECRET_MARKER = "BODY_SECRET_MARKER_123"


async def test_wiki_classification_metadata_persists(db_session: AsyncSession):
    slug = f"test-classification-{uuid.uuid4().hex[:8]}"
    body = (
        "# Sản phẩm tiền gửi\n\n"
        f"Trang test chứa marker {BODY_SECRET_MARKER} ở phần thân để kiểm tra "
        "ràng buộc không-rò-rỉ-nội-dung.\n"
    )

    page = await wiki_service.apply_create(
        db_session,
        slug=slug,
        title="Sản phẩm tiền gửi",
        page_type="entity",
        content_md=body,
        summary="Trang sản phẩm test cho T3.",
        knowledge_type_slugs=["business_object.product_service"],
        source_ids=[],
        taxonomy_confidence=0.91,
        taxonomy_rationale="product page",
        taxonomy_needs_review=False,
        taxonomy_classifier_version="v1",
    )
    await db_session.flush()

    # Reload from DB to confirm columns actually persisted, not just instance attrs.
    stmt = select(WikiPage).where(WikiPage.id == page.id)
    fetched = (await db_session.execute(stmt)).scalar_one()

    # page_type stays exactly entity — no new taxonomy-driven page types.
    assert fetched.page_type == "entity"

    # Slug list stays in knowledge_type_slugs; not duplicated elsewhere.
    assert fetched.knowledge_type_slugs == ["business_object.product_service"]

    # Audit columns persisted with the values we supplied.
    assert fetched.taxonomy_confidence == pytest.approx(0.91)
    assert fetched.taxonomy_rationale == "product page"
    assert fetched.taxonomy_needs_review is False
    assert fetched.taxonomy_classifier_version == "v1"

    # Sanity: the body still contains the marker so the leak check is meaningful.
    assert BODY_SECRET_MARKER in fetched.content_md

    # No body excerpt leaks into any classification audit field.
    audit_fields = (
        fetched.taxonomy_rationale or "",
        fetched.taxonomy_classifier_version or "",
    )
    for value in audit_fields:
        assert BODY_SECRET_MARKER not in value, (
            f"Body marker leaked into classification audit field: {value!r}"
        )


async def test_apply_create_without_classification_kwargs_still_works(
    db_session: AsyncSession,
):
    """Backward-compatibility: callers that don't classify must keep working."""
    slug = f"test-backcompat-{uuid.uuid4().hex[:8]}"
    page = await wiki_service.apply_create(
        db_session,
        slug=slug,
        title="Trang không phân loại",
        page_type="concept",
        content_md="# Concept page",
        summary="",
        knowledge_type_slugs=[],
        source_ids=[],
    )
    await db_session.flush()

    stmt = select(WikiPage).where(WikiPage.id == page.id)
    fetched = (await db_session.execute(stmt)).scalar_one()

    assert fetched.page_type == "concept"
    assert fetched.taxonomy_confidence is None
    assert fetched.taxonomy_rationale is None
    assert fetched.taxonomy_needs_review is False  # NOT NULL default
    assert fetched.taxonomy_classifier_version is None
