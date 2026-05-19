# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false
"""T10 — Apply wiki taxonomy reclassification previews safely."""

from __future__ import annotations

import uuid
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ConsultingRuleProduct, WikiPage
from app.services.wiki_reclassification_service import (
    apply_reclassification,
    preview_reclassification,
)
from tests.fixtures.wiki_taxonomy import (
    create_rule_linked_page,
    create_sentinel_employee,
)

pytestmark = pytest.mark.asyncio


async def _rule_link_count(session: AsyncSession, page_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(ConsultingRuleProduct)
        .where(ConsultingRuleProduct.wiki_page_id == page_id)
    )
    return int(result.scalar_one())


async def test_apply_preserves_page_and_rule_invariants(
    db_session: AsyncSession,
) -> None:
    employee = await create_sentinel_employee(db_session)
    page, _rule = await create_rule_linked_page(db_session, employee.id)
    await db_session.flush()

    page_id = page.id
    source_ids_before = list(page.source_ids or [])
    rule_count_before = await _rule_link_count(db_session, page_id)
    classifier_payload = {
        "slugs": ["business_object.policy_mechanism"],
        "confidence": 0.89,
        "rationale": "same-tier policy mechanism classification",
        "needs_review": False,
        "classifier_version": "taxonomy-v1",
    }

    with patch(
        "app.services.wiki_reclassification_service.classify_page_candidate",
        new_callable=AsyncMock,
        return_value=classifier_payload,
    ):
        preview = await preview_reclassification(db_session, page_ids=[page_id])

    first_apply = await apply_reclassification(db_session, preview=preview)
    assert first_apply["applied_count"] == 1
    assert first_apply["skipped_count"] == 0
    assert first_apply["unchanged_count"] == 0
    assert first_apply["applied_page_ids"] == [str(page_id)]

    db_session.expire_all()
    stored_page = (
        await db_session.execute(select(WikiPage).where(WikiPage.id == page_id))
    ).scalar_one()
    assert stored_page.id == page_id
    assert stored_page.source_ids == source_ids_before
    assert await _rule_link_count(db_session, page_id) == rule_count_before
    assert stored_page.knowledge_type_slugs == ["business_object.policy_mechanism"]
    assert stored_page.taxonomy_confidence == pytest.approx(0.89)
    assert stored_page.taxonomy_rationale == "same-tier policy mechanism classification"
    assert stored_page.taxonomy_needs_review is False
    assert stored_page.taxonomy_classifier_version == "taxonomy-v1"

    second_apply = await apply_reclassification(db_session, preview=preview)
    assert second_apply["applied_count"] == 0
    assert second_apply["skipped_count"] == 0
    assert second_apply["unchanged_count"] == 1
    assert second_apply["applied_page_ids"] == []
    assert await _rule_link_count(db_session, page_id) == rule_count_before


async def test_apply_blocks_risky_rule_linked_move_to_other(
    db_session: AsyncSession,
) -> None:
    employee = await create_sentinel_employee(db_session)
    page, _rule = await create_rule_linked_page(db_session, employee.id)
    await db_session.flush()

    page_id = page.id
    old_slugs = list(page.knowledge_type_slugs or [])
    old_confidence = page.taxonomy_confidence
    old_rationale = page.taxonomy_rationale
    old_needs_review = page.taxonomy_needs_review
    old_classifier_version = page.taxonomy_classifier_version
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
    ):
        preview = await preview_reclassification(db_session, page_ids=[page_id])

    preview_pages = cast(list[dict[str, object]], preview["pages"])
    impact_flags = cast(list[str], preview_pages[0]["impact_flags"])
    assert "rule_linked_tier_change" in impact_flags
    assert "to_other" in impact_flags

    apply_result = await apply_reclassification(db_session, preview=preview)
    assert apply_result["applied_count"] == 0
    assert apply_result["skipped_count"] == 1
    assert apply_result["unchanged_count"] == 0
    assert apply_result["skipped_reasons"] == {
        str(page_id): ["needs_review", "rule_linked_tier_change"]
    }

    db_session.expire_all()
    stored_page = (
        await db_session.execute(select(WikiPage).where(WikiPage.id == page_id))
    ).scalar_one()
    assert stored_page.knowledge_type_slugs == old_slugs
    assert stored_page.taxonomy_confidence == old_confidence
    assert stored_page.taxonomy_rationale == old_rationale
    assert stored_page.taxonomy_needs_review is old_needs_review
    assert stored_page.taxonomy_classifier_version == old_classifier_version

    second_apply = await apply_reclassification(db_session, preview=preview)
    assert second_apply["applied_count"] == 0
    assert second_apply["skipped_count"] == 1
    assert second_apply["unchanged_count"] == 0


async def test_force_does_not_bypass_needs_review(
    db_session: AsyncSession,
) -> None:
    employee = await create_sentinel_employee(db_session)
    page, _rule = await create_rule_linked_page(db_session, employee.id)
    await db_session.flush()

    page_id = page.id
    old_slugs = list(page.knowledge_type_slugs or [])
    classifier_payload = {
        "slugs": ["supporting_knowledge.other"],
        "confidence": 0.55,
        "rationale": "low-confidence fallback requires review",
        "needs_review": True,
        "classifier_version": "taxonomy-v1",
    }

    with patch(
        "app.services.wiki_reclassification_service.classify_page_candidate",
        new_callable=AsyncMock,
        return_value=classifier_payload,
    ):
        preview = await preview_reclassification(db_session, page_ids=[page_id])

    preview_pages = cast(list[dict[str, object]], preview["pages"])
    assert preview_pages[0]["needs_review"] is True
    assert "rule_linked_tier_change" in cast(list[str], preview_pages[0]["impact_flags"])

    apply_result = await apply_reclassification(
        db_session,
        preview=preview,
        force_rule_linked_tier_change=True,
    )

    assert apply_result["applied_count"] == 0
    assert apply_result["skipped_count"] == 1
    assert apply_result["unchanged_count"] == 0
    assert str(page_id) not in cast(list[str], apply_result["applied_page_ids"])
    skipped_reasons = cast(dict[str, list[str]], apply_result["skipped_reasons"])
    assert skipped_reasons[str(page_id)] == ["needs_review"]

    db_session.expire_all()
    stored_page = (
        await db_session.execute(select(WikiPage).where(WikiPage.id == page_id))
    ).scalar_one()
    assert stored_page.knowledge_type_slugs == old_slugs
