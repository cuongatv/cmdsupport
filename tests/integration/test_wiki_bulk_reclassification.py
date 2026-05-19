# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false
"""T17 — Bulk wiki taxonomy reclassification orchestration."""

from __future__ import annotations

import uuid
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WikiPage
from app.services.wiki_reclassification_service import (
    apply_reclassification,
    preview_reclassification,
)
from tests.fixtures.wiki_taxonomy import (
    create_bulk_taxonomy_pages,
    create_sentinel_employee,
)

pytestmark = pytest.mark.asyncio


async def _stored_slugs(
    session: AsyncSession,
    page_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[str]]:
    result = await session.execute(
        select(WikiPage).where(WikiPage.id.in_(page_ids)).order_by(WikiPage.id)
    )
    return {page.id: list(page.knowledge_type_slugs or []) for page in result.scalars()}


def _bulk_classifier_payload(slug: str) -> dict[str, object]:
    return {
        "slugs": [slug],
        "confidence": 0.92,
        "rationale": "bulk deterministic classifier",
        "needs_review": False,
        "classifier_version": "taxonomy-v1",
    }


async def test_bulk_preview_paginates_without_mutation(
    db_session: AsyncSession,
) -> None:
    pages = await create_bulk_taxonomy_pages(
        db_session,
        count=55,
        slug_prefix="bulk-preview-pagination",
    )
    await db_session.flush()

    page_ids = [page.id for page in pages]
    before_slugs = await _stored_slugs(db_session, page_ids)

    with patch(
        "app.services.wiki_reclassification_service.classify_page_candidate",
        new_callable=AsyncMock,
        return_value=_bulk_classifier_payload("business_object.product_service"),
    ) as mock_classify:
        previews = [
            await preview_reclassification(
                db_session,
                page_ids=page_ids,
                page_size=20,
                page=page_number,
            )
            for page_number in (1, 2, 3)
        ]

    assert [preview["page_count"] for preview in previews] == [20, 20, 15]
    assert [preview["page"] for preview in previews] == [1, 2, 3]
    assert all(preview["page_size"] == 20 for preview in previews)
    assert all(preview["total_pages"] == 3 for preview in previews)
    assert all(preview["total_pages_estimated"] is False for preview in previews)
    assert [preview["has_more"] for preview in previews] == [True, True, False]
    assert mock_classify.await_count == 55

    db_session.expire_all()
    assert await _stored_slugs(db_session, page_ids) == before_slugs


async def test_bulk_apply_is_idempotent(db_session: AsyncSession) -> None:
    employee = await create_sentinel_employee(db_session)
    pages = await create_bulk_taxonomy_pages(
        db_session,
        count=10,
        slug_prefix="bulk-apply-idempotent",
    )
    await db_session.flush()

    page_ids = [page.id for page in pages]
    with patch(
        "app.services.wiki_reclassification_service.classify_page_candidate",
        new_callable=AsyncMock,
        return_value=_bulk_classifier_payload("business_object.customer_segment"),
    ):
        preview = await preview_reclassification(db_session, page_ids=page_ids, actor=employee)

    preview_pages = cast(list[dict[str, object]], preview["pages"])
    assert len(preview_pages) == 10
    assert all(
        item["new_slugs"] == ["business_object.customer_segment"]
        for item in preview_pages
    )

    first_apply = await apply_reclassification(db_session, preview_id=preview["preview_id"], actor=employee)
    assert first_apply["applied_count"] == 10
    assert first_apply["skipped_count"] == 0
    assert first_apply["unchanged_count"] == 0
    assert sorted(cast(list[str], first_apply["applied_page_ids"])) == sorted(
        str(page_id) for page_id in page_ids
    )

    second_apply = await apply_reclassification(db_session, preview_id=preview["preview_id"], actor=employee)
    assert second_apply["applied_count"] == 0
    assert second_apply["skipped_count"] == 0
    assert second_apply["unchanged_count"] == 10
    assert second_apply["applied_page_ids"] == []
