# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false
"""T7 — Legacy wiki ingest hooks the taxonomy classifier.

Verifies the legacy ``wiki_agent_tools.create_page`` write seam:
    1. Calls ``classify_page_candidate`` exactly once per create.
    2. Persists the classifier slugs into ``WikiPage.knowledge_type_slugs``.
    3. Threads the four taxonomy audit kwargs through to ``wiki_service.apply_create``.

Both tests stub ``classify_page_candidate`` at the import site used by the
agent tools so no live provider traffic is needed. The fallback test mirrors
the dict that ``app.services.wiki_taxonomy_classifier._safe_fallback`` returns
internally on provider failure — T6 guarantees the classifier never raises.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.wiki_agent_tools import AgentState, build_tool_handlers
from app.database.models import Source, WikiPage

pytestmark = pytest.mark.asyncio


def _make_source(session: AsyncSession) -> Source:
    source = Source(
        id=uuid.uuid4(),
        title="Legacy ingest taxonomy fixture",
        full_text="Legacy ingest source body kept verbatim for taxonomy tests.\n",
        source_type="file",
        scope_type="global",
        status="done",
        progress=100,
        file_name="legacy-ingest.md",
    )
    session.add(source)
    return source


async def test_legacy_create_persists_taxonomy_classification(
    db_session: AsyncSession,
) -> None:
    """High-confidence classifier output is persisted via the legacy create seam."""
    source = _make_source(db_session)
    await db_session.flush()

    state = AgentState(source=source, full_text=source.full_text or "")

    classifier_payload = {
        "slugs": ["business_object.product_service"],
        "confidence": 0.92,
        "rationale": "product page",
        "needs_review": False,
        "classifier_version": "taxonomy-v1",
    }

    with patch(
        "app.ai.wiki_agent_tools.classify_page_candidate",
        new_callable=AsyncMock,
        return_value=classifier_payload,
    ) as mock_classify:
        handlers = build_tool_handlers(
            session=db_session,
            source=source,
            kt_slug=None,
            embedding_provider=None,
            state=state,
        )
        slug = f"entity/legacy-product-{uuid.uuid4().hex[:8]}"
        result = await handlers["create_page"](
            slug=slug,
            title="Legacy product page",
            page_type="entity",
            content_md=(
                "# Legacy product page\n\n"
                "Gói tín dụng SME stays verbatim in the body to confirm no translation.\n"
            ),
            summary="Legacy product page for T7 integration coverage.",
        )

    assert result.get("created") == slug.strip().lower()
    assert mock_classify.await_count == 1

    fetched = (
        await db_session.execute(
            select(WikiPage).where(WikiPage.slug == slug.strip().lower())
        )
    ).scalar_one()

    assert "business_object.product_service" in (fetched.knowledge_type_slugs or [])
    assert fetched.taxonomy_classifier_version == "taxonomy-v1"
    assert fetched.taxonomy_confidence == pytest.approx(0.92)
    assert fetched.taxonomy_needs_review is False
    assert fetched.taxonomy_rationale == "product page"


async def test_legacy_classifier_failure_safe_fallback(
    db_session: AsyncSession,
) -> None:
    """Safe-fallback classifier output still produces a page flagged for review."""
    source = _make_source(db_session)
    await db_session.flush()

    state = AgentState(source=source, full_text=source.full_text or "")

    fallback_payload = {
        "slugs": ["supporting_knowledge.other"],
        "confidence": 0.0,
        "rationale": "Classifier provider error; safe fallback.",
        "needs_review": True,
        "classifier_version": "taxonomy-v1",
    }

    with patch(
        "app.ai.wiki_agent_tools.classify_page_candidate",
        new_callable=AsyncMock,
        return_value=fallback_payload,
    ) as mock_classify:
        handlers = build_tool_handlers(
            session=db_session,
            source=source,
            kt_slug=None,
            embedding_provider=None,
            state=state,
        )
        slug = f"concept/legacy-fallback-{uuid.uuid4().hex[:8]}"
        result = await handlers["create_page"](
            slug=slug,
            title="Legacy fallback page",
            page_type="concept",
            content_md=(
                "# Legacy fallback page\n\n"
                "Working capital loan stays verbatim for fallback fixture.\n"
            ),
            summary="Legacy fallback page covering classifier failure path.",
        )

    assert result.get("created") == slug.strip().lower()
    assert mock_classify.await_count == 1

    fetched = (
        await db_session.execute(
            select(WikiPage).where(WikiPage.slug == slug.strip().lower())
        )
    ).scalar_one()

    assert "supporting_knowledge.other" in (fetched.knowledge_type_slugs or [])
    assert fetched.taxonomy_needs_review is True
    assert fetched.taxonomy_classifier_version == "taxonomy-v1"
    assert fetched.taxonomy_confidence == pytest.approx(0.0)
