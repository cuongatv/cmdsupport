# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false
"""T9 — Existing wiki reclassification preview is non-mutating."""

from __future__ import annotations

import uuid
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import WikiPage
from app.services import wiki_service
from app.services.wiki_reclassification_service import preview_reclassification
from tests.fixtures.wiki_taxonomy import (
    create_rule_linked_page,
    create_sentinel_employee,
)

pytestmark = pytest.mark.asyncio


async def test_preview_is_non_mutating(db_session: AsyncSession) -> None:
    page = await wiki_service.apply_create(
        db_session,
        slug=f"preview-non-mutating-{uuid.uuid4().hex[:8]}",
        title="Preview non-mutating fixture",
        page_type="entity",
        content_md=(
            "# Preview non-mutating fixture\n\n"
            "Gói tín dụng SME keeps source body untouched during preview.\n"
        ),
        summary="Preview fixture with an existing policy mechanism classification.",
        knowledge_type_slugs=["business_object.policy_mechanism"],
        source_ids=[],
        taxonomy_confidence=0.82,
        taxonomy_rationale="Existing classification before preview.",
        taxonomy_needs_review=False,
        taxonomy_classifier_version="taxonomy-v1",
    )
    await db_session.flush()

    classifier_payload = {
        "slugs": ["business_object.product_service"],
        "confidence": 0.91,
        "rationale": "product page",
        "needs_review": False,
        "classifier_version": "taxonomy-v1",
    }

    with patch(
        "app.services.wiki_reclassification_service.classify_page_candidate",
        new_callable=AsyncMock,
        return_value=classifier_payload,
    ) as mock_classify:
        result = await preview_reclassification(db_session, page_ids=[page.id])

    assert result["page_count"] == 1
    assert mock_classify.await_count == 1
    preview_pages = cast(list[dict[str, object]], result["pages"])
    preview_page = preview_pages[0]
    assert preview_page["old_slugs"] == ["business_object.policy_mechanism"]
    assert preview_page["new_slugs"] == ["business_object.product_service"]

    page_id = page.id
    db_session.expire_all()
    stored_page = (
        await db_session.execute(select(WikiPage).where(WikiPage.id == page_id))
    ).scalar_one()
    assert stored_page.knowledge_type_slugs == ["business_object.policy_mechanism"]
    assert stored_page.taxonomy_confidence == pytest.approx(0.82)
    assert stored_page.taxonomy_rationale == "Existing classification before preview."
    assert stored_page.taxonomy_needs_review is False
    assert stored_page.taxonomy_classifier_version == "taxonomy-v1"


async def test_preview_rule_linked_tier_change_flagged(
    db_session: AsyncSession,
) -> None:
    employee = await create_sentinel_employee(db_session)
    page, _rule = await create_rule_linked_page(db_session, employee.id)
    await db_session.flush()

    classifier_payload = {
        "slugs": ["supporting_knowledge.other"],
        "confidence": 0.74,
        "rationale": "supporting fallback",
        "needs_review": True,
        "classifier_version": "taxonomy-v1",
    }

    with patch(
        "app.services.wiki_reclassification_service.classify_page_candidate",
        new_callable=AsyncMock,
        return_value=classifier_payload,
    ) as mock_classify:
        result = await preview_reclassification(db_session, page_ids=[page.id])

    assert result["page_count"] == 1
    assert mock_classify.await_count == 1
    preview_pages = cast(list[dict[str, object]], result["pages"])
    preview_page = preview_pages[0]
    assert preview_page["wiki_page_id"] == str(page.id)
    assert preview_page["rule_link_count"] == 1
    impact_flags = cast(list[str], preview_page["impact_flags"])
    assert "rule_linked_tier_change" in impact_flags
    assert "to_other" in impact_flags
