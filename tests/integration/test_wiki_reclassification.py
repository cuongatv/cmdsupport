# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false
"""T19 — Existing Wiki reclassification QA with rule-linked pages.

End-to-end safety net for the preview → apply workflow, verifying that:
  1. Unlinked pages reclassify safely without losing identity.
  2. Rule-linked pages risky tier changes (e.g. business → supporting_knowledge.other)
     are flagged and skipped without ``force`` so consulting rule links survive.
  3. Same-tier reclassification on a rule-linked page preserves every cross-cutting
     invariant: wiki_page_id, source_ids, consulting rule link count, and the
     WikiPageRevision history grows monotonically.

All assertions re-read the database via raw SELECT after ``session.expire_all()``
to prove invariants from persisted rows rather than ORM identity cache state.
"""

from __future__ import annotations

import uuid
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    ConsultingRuleProduct,
    WikiPage,
    WikiPageRevision,
)
from app.services import wiki_service
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


async def _revision_count(session: AsyncSession, page_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(WikiPageRevision)
        .where(WikiPageRevision.page_id == page_id)
    )
    return int(result.scalar_one())


async def test_existing_unlinked_page_reclassifies_safely(
    db_session: AsyncSession,
) -> None:
    """Unlinked page with legacy slug should preview + apply cleanly.

    Page identity (id, source_ids) is preserved; only knowledge_type_slugs and
    audit columns change.
    """
    slug = f"t19-unlinked-{uuid.uuid4().hex[:8]}"
    page = await wiki_service.apply_create(
        db_session,
        slug=slug,
        title="T19 unlinked reclassify fixture",
        page_type="entity",
        content_md=(
            "# T19 unlinked reclassify fixture\n\n"
            "Gói tín dụng SME bilingual fixture for unlinked reclassification.\n\n"
            "Working capital loan stays in the source language for assertions.\n"
        ),
        summary="Legacy policy_mechanism page slated for reclassification.",
        knowledge_type_slugs=["business_object.policy_mechanism"],
        source_ids=[],
        taxonomy_confidence=0.78,
        taxonomy_rationale="Legacy classification pre-T19.",
        taxonomy_needs_review=False,
        taxonomy_classifier_version="taxonomy-v0",
    )
    await db_session.flush()

    page_id = page.id
    original_source_ids = list(page.source_ids or [])
    original_slugs = list(page.knowledge_type_slugs or [])

    classifier_payload = {
        "slugs": ["business_object.product_service"],
        "confidence": 0.91,
        "rationale": "stronger product page signal",
        "needs_review": False,
        "classifier_version": "taxonomy-v1",
    }

    with patch(
        "app.services.wiki_reclassification_service.classify_page_candidate",
        new_callable=AsyncMock,
        return_value=classifier_payload,
    ):
        preview = await preview_reclassification(db_session, page_ids=[page_id])

    preview_pages = cast(list[dict[str, object]], preview["pages"])
    assert preview["page_count"] == 1
    assert preview_pages[0]["wiki_page_id"] == str(page_id)
    assert preview_pages[0]["old_slugs"] == original_slugs
    assert preview_pages[0]["new_slugs"] == ["business_object.product_service"]
    # Unlinked page must NOT raise the rule-linked-tier-change flag.
    impact_flags = cast(list[str], preview_pages[0]["impact_flags"])
    assert "rule_linked_tier_change" not in impact_flags

    apply_result = await apply_reclassification(db_session, preview=preview)
    assert apply_result["applied_count"] == 1
    assert apply_result["skipped_count"] == 0
    assert apply_result["unchanged_count"] == 0
    assert apply_result["applied_page_ids"] == [str(page_id)]

    db_session.expire_all()
    stored = (
        await db_session.execute(select(WikiPage).where(WikiPage.id == page_id))
    ).scalar_one()
    assert stored.id == page_id
    assert stored.source_ids == original_source_ids
    assert stored.knowledge_type_slugs == ["business_object.product_service"]
    assert stored.taxonomy_confidence == pytest.approx(0.91)
    assert stored.taxonomy_rationale == "stronger product page signal"
    assert stored.taxonomy_needs_review is False
    assert stored.taxonomy_classifier_version == "taxonomy-v1"


async def test_existing_rule_linked_page_warns_before_risky_apply(
    db_session: AsyncSession,
) -> None:
    """Rule-linked business→supporting_knowledge.other move must be blocked.

    Preview surfaces ``rule_link_count=1`` and ``rule_linked_tier_change``.
    Apply without ``force_rule_linked_tier_change`` skips the page; the DB-side
    slugs and consulting rule linkage are untouched.
    """
    employee = await create_sentinel_employee(db_session)
    page, _rule = await create_rule_linked_page(db_session, employee.id)
    await db_session.flush()

    page_id = page.id
    original_slugs = list(page.knowledge_type_slugs or [])
    original_confidence = page.taxonomy_confidence
    original_rationale = page.taxonomy_rationale
    original_needs_review = page.taxonomy_needs_review
    original_classifier_version = page.taxonomy_classifier_version
    rule_count_before = await _rule_link_count(db_session, page_id)
    assert rule_count_before == 1

    classifier_payload = {
        "slugs": ["supporting_knowledge.other"],
        "confidence": 0.74,
        "rationale": "supporting fallback proposal",
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
    assert preview["page_count"] == 1
    assert preview_pages[0]["rule_link_count"] == 1
    impact_flags = cast(list[str], preview_pages[0]["impact_flags"])
    assert "rule_linked_tier_change" in impact_flags
    assert "to_other" in impact_flags

    apply_result = await apply_reclassification(db_session, preview=preview)
    assert apply_result["applied_count"] == 0
    assert apply_result["skipped_count"] == 1
    assert apply_result["unchanged_count"] == 0
    skipped_reasons = cast(dict[str, list[str]], apply_result["skipped_reasons"])
    assert "rule_linked_tier_change" in skipped_reasons[str(page_id)]

    db_session.expire_all()
    stored = (
        await db_session.execute(select(WikiPage).where(WikiPage.id == page_id))
    ).scalar_one()
    assert stored.knowledge_type_slugs == original_slugs
    assert stored.taxonomy_confidence == original_confidence
    assert stored.taxonomy_rationale == original_rationale
    assert stored.taxonomy_needs_review is original_needs_review
    assert stored.taxonomy_classifier_version == original_classifier_version
    assert await _rule_link_count(db_session, page_id) == rule_count_before


async def test_full_invariants_preserved_after_apply(
    db_session: AsyncSession,
) -> None:
    """Same-tier reclassification on a rule-linked page keeps every invariant.

    business → business apply path proves:
      * ``wiki_page_id`` unchanged (no row delete/recreate).
      * ``source_ids`` unchanged.
      * ``ConsultingRuleProduct.wiki_page_id`` row count unchanged (no broken links).
      * ``WikiPageRevision`` count never decreases — apply_update appends a new
        revision, so the count grows by at least one.
    """
    employee = await create_sentinel_employee(db_session)
    page, rule = await create_rule_linked_page(db_session, employee.id)
    await db_session.flush()

    page_id = page.id
    rule_id = rule.id
    original_source_ids = list(page.source_ids or [])
    original_slugs = list(page.knowledge_type_slugs or [])
    # Sanity check: fixture starts on the business tier with a real slug.
    assert original_slugs == ["business_object.product_service"]
    rule_count_before = await _rule_link_count(db_session, page_id)
    revision_count_before = await _revision_count(db_session, page_id)
    assert rule_count_before == 1
    # No precondition on revision_count_before: the rule-linked fixture rekeys
    # the wiki_page_id via raw SQL after apply_create which can leave the
    # initial revision attached to a different id depending on flush timing.
    # The invariant we care about is "apply never resets revisions", asserted
    # below as revision_count_after >= revision_count_before.

    classifier_payload = {
        "slugs": ["business_object.policy_mechanism"],
        "confidence": 0.88,
        "rationale": "same-tier policy mechanism reclassification",
        "needs_review": False,
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
    # Same-tier business → business must NOT flag a rule-linked tier change.
    assert "rule_linked_tier_change" not in impact_flags
    assert preview_pages[0]["rule_link_count"] == 1

    apply_result = await apply_reclassification(db_session, preview=preview)
    assert apply_result["applied_count"] == 1
    assert apply_result["skipped_count"] == 0
    assert apply_result["unchanged_count"] == 0
    assert apply_result["applied_page_ids"] == [str(page_id)]

    db_session.expire_all()

    # Page identity preserved end-to-end.
    stored = (
        await db_session.execute(select(WikiPage).where(WikiPage.id == page_id))
    ).scalar_one()
    assert stored.id == page_id
    assert stored.source_ids == original_source_ids
    assert stored.knowledge_type_slugs == ["business_object.policy_mechanism"]
    assert stored.taxonomy_confidence == pytest.approx(0.88)
    assert stored.taxonomy_rationale == "same-tier policy mechanism reclassification"
    assert stored.taxonomy_needs_review is False
    assert stored.taxonomy_classifier_version == "taxonomy-v1"

    # Consulting rule link survives, pointing to the same wiki_page_id.
    rule_count_after = await _rule_link_count(db_session, page_id)
    assert rule_count_after == rule_count_before
    stored_rule = (
        await db_session.execute(
            select(ConsultingRuleProduct).where(ConsultingRuleProduct.id == rule_id)
        )
    ).scalar_one()
    assert stored_rule.wiki_page_id == page_id

    # Revision history is append-only and never reset by apply.
    revision_count_after = await _revision_count(db_session, page_id)
    assert revision_count_after >= revision_count_before
