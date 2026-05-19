# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false
"""T8 — MRP wiki ingest persists taxonomy classification metadata."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.mrp.pipeline import run_commit_phase
from app.ai.mrp.writer import PageWriteResult
from app.database.models import Source, SourceCompilationPlan, WikiPage
from app.utils.progress import ProgressTracker

pytestmark = pytest.mark.asyncio


class NoEmbeddingRegistry:
    async def get_embedding(self, task: str = "document"):
        del task
        raise RuntimeError("embedding disabled for test")

    async def get_llm(self):
        raise RuntimeError("merge LLM disabled for test")


class StubProgressTracker(ProgressTracker):
    def __init__(self) -> None:
        super().__init__(uuid.uuid4())

    async def update(self, progress: int, message: str) -> None:
        del progress, message


def _make_source(session: AsyncSession) -> Source:
    source = Source(
        id=uuid.uuid4(),
        title="MRP ingest taxonomy fixture",
        full_text="MRP ingest source body kept verbatim for taxonomy tests.\n",
        source_type="file",
        scope_type="global",
        status="processing",
        progress=90,
        file_name="mrp-ingest.md",
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


async def test_mrp_commit_persists_high_confidence_taxonomy(
    db_session: AsyncSession,
) -> None:
    """High-confidence classifier output is persisted by the MRP commit seam."""
    source = _make_source(db_session)
    plan = _make_plan(db_session, source)
    await db_session.flush()

    page_slug = f"entity/mrp-product-{uuid.uuid4().hex[:8]}"
    page_results = [
        PageWriteResult(
            slug=page_slug,
            title="MRP product page",
            page_type="entity",
            action="CREATE",
            content_md=(
                "# MRP product page\n\n"
                "Gói tín dụng SME stays verbatim in the MRP body.\n"
            ),
            summary="MRP product page for taxonomy integration coverage.",
        )
    ]
    classifier_payload = {
        "slugs": ["business_object.product_service"],
        "confidence": 0.93,
        "rationale": "product/service page",
        "needs_review": False,
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
            registry=NoEmbeddingRegistry(),
            kt_slug=None,
            tracker=StubProgressTracker(),
        )

    assert result == {"pages_created": 1, "pages_updated": 0}
    assert mock_classify.await_count == 1
    mock_classify.assert_awaited_once()

    fetched = (
        await db_session.execute(select(WikiPage).where(WikiPage.slug == page_slug))
    ).scalar_one()

    assert "business_object.product_service" in (fetched.knowledge_type_slugs or [])
    assert fetched.taxonomy_classifier_version == "taxonomy-v1"
    assert fetched.taxonomy_confidence == pytest.approx(0.93)
    assert fetched.taxonomy_needs_review is False
    assert fetched.taxonomy_rationale == "product/service page"
    assert plan.status == "done"
    assert source.status == "ready"


async def test_mrp_commit_persists_supporting_fallback_needs_review(
    db_session: AsyncSession,
) -> None:
    """Fallback classifier output still creates an MRP page flagged for review."""
    source = _make_source(db_session)
    plan = _make_plan(db_session, source)
    await db_session.flush()

    page_slug = f"concept/mrp-fallback-{uuid.uuid4().hex[:8]}"
    page_results = [
        PageWriteResult(
            slug=page_slug,
            title="MRP fallback page",
            page_type="concept",
            action="CREATE",
            content_md=(
                "# MRP fallback page\n\n"
                "Working capital loan stays verbatim in the fallback fixture.\n"
            ),
            summary="MRP fallback page covering classifier safe fallback.",
        )
    ]
    fallback_payload = {
        "slugs": ["supporting_knowledge.other"],
        "confidence": 0.0,
        "rationale": "Classifier provider error; safe fallback.",
        "needs_review": True,
        "classifier_version": "taxonomy-v1",
    }

    with patch(
        "app.ai.mrp.pipeline.classify_page_candidate",
        new_callable=AsyncMock,
        return_value=fallback_payload,
    ) as mock_classify:
        result = await run_commit_phase(
            session=db_session,
            source=source,
            page_results=page_results,
            plan=plan,
            registry=NoEmbeddingRegistry(),
            kt_slug=None,
            tracker=StubProgressTracker(),
        )

    assert result == {"pages_created": 1, "pages_updated": 0}
    assert mock_classify.await_count == 1

    fetched = (
        await db_session.execute(select(WikiPage).where(WikiPage.slug == page_slug))
    ).scalar_one()

    assert "supporting_knowledge.other" in (fetched.knowledge_type_slugs or [])
    assert fetched.taxonomy_needs_review is True
    assert fetched.taxonomy_classifier_version == "taxonomy-v1"
    assert fetched.taxonomy_confidence == pytest.approx(0.0)
    assert fetched.taxonomy_rationale == "Classifier provider error; safe fallback."
