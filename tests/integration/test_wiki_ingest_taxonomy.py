# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false
"""T18 — End-to-end source ingest classification QA.

Verifies that BOTH the legacy compile path (T7) and the MRP commit path (T8)
actually invoke ``classify_page_candidate`` during real ingestion, persist the
returned taxonomy slugs/audit metadata onto ``WikiPage``, leave ``page_type``
untouched, AND preserve the bilingual body content verbatim (no translation).

Strategy mirrors T7/T8 unit-style mocking: ``classify_page_candidate`` is
patched at the IMPORT SITE used by each ingest path so no live provider
traffic is needed. Body fixtures contain both ``Working capital loan``
(English) and ``Gói tín dụng SME`` (Vietnamese) so a single grep proves the
no-translation invariant the wiki agent prompts enforce.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.mrp.pipeline import run_commit_phase
from app.ai.mrp.writer import PageWriteResult
from app.ai.wiki_agent_tools import AgentState, build_tool_handlers
from app.database.models import Source, SourceCompilationPlan, WikiPage
from app.utils.progress import ProgressTracker

pytestmark = pytest.mark.asyncio

# Body fixture — must contain BOTH languages verbatim so the no-translation
# invariant can be asserted with simple substring checks.
BILINGUAL_BODY = (
    "# Working capital loan\n\n"
    "Gói tín dụng SME dành cho doanh nghiệp nhỏ và vừa cần vốn quay vòng.\n\n"
    "Working capital loan helps SMEs manage short-term cash flow.\n"
)


class _NoEmbeddingRegistry:
    async def get_embedding(self, task: str = "document"):
        del task
        raise RuntimeError("embedding disabled for test")

    async def get_llm(self):
        raise RuntimeError("merge LLM disabled for test")


class _StubProgressTracker(ProgressTracker):
    def __init__(self) -> None:
        super().__init__(uuid.uuid4())

    async def update(self, progress: int, message: str) -> None:
        del progress, message


def _make_legacy_source(session: AsyncSession) -> Source:
    source = Source(
        id=uuid.uuid4(),
        title="T18 legacy ingest fixture",
        full_text=BILINGUAL_BODY,
        source_type="file",
        scope_type="global",
        status="done",
        progress=100,
        file_name="t18-legacy-ingest.md",
    )
    session.add(source)
    return source


def _make_mrp_source(session: AsyncSession) -> Source:
    source = Source(
        id=uuid.uuid4(),
        title="T18 MRP ingest fixture",
        full_text=BILINGUAL_BODY,
        source_type="file",
        scope_type="global",
        status="processing",
        progress=90,
        file_name="t18-mrp-ingest.md",
        pipeline_phase="commit",
        metadata_={"ingestion_pipeline": "mrp"},
    )
    session.add(source)
    return source


def _make_plan(session: AsyncSession, source: Source) -> SourceCompilationPlan:
    plan = SourceCompilationPlan(
        source_id=source.id,
        plan_json={"pages": []},
        status="approved",
        version=1,
    )
    session.add(plan)
    return plan


async def test_legacy_ingest_classifies_product_document_page(
    db_session: AsyncSession,
) -> None:
    """Legacy ``create_page`` writes classifier slugs + audit; body & type stay put."""
    source = _make_legacy_source(db_session)
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
        slug = f"entity/t18-legacy-product-{uuid.uuid4().hex[:8]}"
        result = await handlers["create_page"](
            slug=slug,
            title="Working capital loan",
            page_type="entity",
            content_md=BILINGUAL_BODY,
            summary="T18 legacy product page for ingest classification QA.",
        )

    assert result.get("created") == slug.strip().lower()
    # Legacy handler echoes the page_type unchanged.
    assert result.get("page_type") == "entity"
    assert mock_classify.await_count == 1

    fetched = (
        await db_session.execute(
            select(WikiPage).where(WikiPage.slug == slug.strip().lower())
        )
    ).scalar_one()

    # Taxonomy classification persisted.
    assert "business_object.product_service" in (fetched.knowledge_type_slugs or [])
    assert fetched.taxonomy_classifier_version == "taxonomy-v1"
    assert fetched.taxonomy_confidence == pytest.approx(0.92)
    assert fetched.taxonomy_needs_review is False
    assert fetched.taxonomy_rationale == "product page"

    # page_type unchanged from what the legacy path produced.
    assert fetched.page_type == "entity"

    # Bilingual body preserved EXACTLY — no translation either direction.
    assert "Working capital loan" in fetched.content_md
    assert "Gói tín dụng SME" in fetched.content_md
    assert fetched.content_md == BILINGUAL_BODY


async def test_mrp_ingest_classifies_supporting_context_page(
    db_session: AsyncSession,
) -> None:
    """MRP commit writes supporting-knowledge slugs + needs_review; body & type stay put."""
    source = _make_mrp_source(db_session)
    plan = _make_plan(db_session, source)
    await db_session.flush()

    page_slug = f"topic/t18-mrp-context-{uuid.uuid4().hex[:8]}"
    page_results = [
        PageWriteResult(
            slug=page_slug,
            title="Working capital loan context",
            page_type="topic",
            action="CREATE",
            content_md=BILINGUAL_BODY,
            summary="T18 MRP supporting-context page for ingest classification QA.",
        )
    ]
    classifier_payload = {
        "slugs": ["supporting_knowledge.general_context"],
        "confidence": 0.65,
        "rationale": "background context",
        "needs_review": True,
        "classifier_version": "taxonomy-v1",
    }

    with patch(
        "app.ai.mrp.pipeline.classify_page_candidate",
        new_callable=AsyncMock,
        return_value=classifier_payload,
    ) as mock_classify:
        result = await run_commit_phase(
            session=db_session,
            source=source,
            page_results=page_results,
            plan=plan,
            registry=_NoEmbeddingRegistry(),
            kt_slug=None,
            tracker=_StubProgressTracker(),
        )

    assert result == {"pages_created": 1, "pages_updated": 0}
    assert mock_classify.await_count == 1

    fetched = (
        await db_session.execute(select(WikiPage).where(WikiPage.slug == page_slug))
    ).scalar_one()

    # Taxonomy classification persisted with needs_review True.
    assert "supporting_knowledge.general_context" in (fetched.knowledge_type_slugs or [])
    assert fetched.taxonomy_classifier_version == "taxonomy-v1"
    assert fetched.taxonomy_confidence == pytest.approx(0.65)
    assert fetched.taxonomy_needs_review is True
    assert fetched.taxonomy_rationale == "background context"

    # page_type matches the MRP-supplied writer plan (topic).
    assert fetched.page_type == "topic"

    # Bilingual body preserved EXACTLY — no translation either direction.
    assert "Working capital loan" in fetched.content_md
    assert "Gói tín dụng SME" in fetched.content_md
    assert fetched.content_md == BILINGUAL_BODY
