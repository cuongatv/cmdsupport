"""Phase 4 VERIFY checks for MRP page results."""

import asyncio
import json
from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.mrp.writer import PageWriteResult
from app.ai.providers.base import EmbeddingProvider, LLMProvider
from app.utils.progress import ProgressTracker

CONFLICT_SIM_THRESHOLD = 0.80


def check_coverage(
    chunk_extracts: list,
    page_results: list[PageWriteResult],
    min_mentions: int = 3,
) -> list[str]:
    """Return significant extracted entities not covered by written pages."""
    mention_counts: dict[str, int] = {}
    for row in chunk_extracts:
        for entity in (row.extract_json or {}).get("entities", []) or []:
            name = str(entity.get("name") or "").lower()
            if name:
                mention_counts[name] = mention_counts.get(name, 0) + 1

    covered: set[str] = set()
    for page in page_results:
        covered.update(name.lower() for name in page.entity_names)
        covered.add(page.title.lower())

    uncovered = [
        name for name, count in mention_counts.items()
        if count >= min_mentions and name not in covered
    ]
    if uncovered:
        logger.warning(f"MRP VERIFY coverage gaps: {', '.join(uncovered[:10])}")
    return uncovered


async def check_conflicts(
    session: AsyncSession,
    page_results: list[PageWriteResult],
    embedding_provider: EmbeddingProvider,
    llm: LLMProvider,
    source,
) -> list[dict]:
    """Check nearby wiki pages for possible contradictions. Non-blocking."""
    from app.services import wiki_service

    conflicts: list[dict] = []
    for page_result in page_results:
        try:
            vector = await embedding_provider.embed(
                f"{page_result.title}\n\n{page_result.summary}\n\n{page_result.content_md[:3000]}"
            )
            hits = await wiki_service.search_pages_semantic(
                session,
                vector,
                top_k=3,
                scope_type=source.scope_type or "global",
                scope_id=source.scope_id,
            )
        except Exception:
            continue

        for page, similarity in hits:
            if similarity < CONFLICT_SIM_THRESHOLD or page.slug == page_result.slug:
                continue
            prompt = (
                "Do these texts contain contradictory factual statements? "
                "Return JSON {\"contradicts\": true|false, \"description\": \"string\"}.\n\n"
                f"Text A:\n{page_result.content_md[:1500]}\n\n"
                f"Text B ({page.slug}):\n{(page.content_md or '')[:1500]}"
            )
            try:
                raw = await asyncio.wait_for(
                    llm.generate(prompt, system="You are a fact checker. Return only JSON.", temperature=0.0),
                    timeout=30,
                )
                result = json.loads(raw.strip().strip("```json").strip("```").strip())
            except Exception:
                continue
            if result.get("contradicts"):
                conflicts.append({
                    "new_slug": page_result.slug,
                    "existing_slug": page.slug,
                    "similarity": similarity,
                    "description": result.get("description", ""),
                })
    return conflicts


async def run_verify_phase(
    session: AsyncSession,
    source,
    page_results: list[PageWriteResult],
    chunk_extracts: list,
    full_text: str,
    llm: LLMProvider,
    embedding_provider: Optional[EmbeddingProvider],
    tracker: ProgressTracker,
) -> list[PageWriteResult]:
    """Run non-blocking coverage and conflict checks."""
    del full_text
    await tracker.update(88, "Checking coverage...")
    check_coverage(chunk_extracts, page_results)
    await tracker.update(91, "Checking for conflicts...")
    if embedding_provider:
        try:
            await check_conflicts(session, page_results, embedding_provider, llm, source)
        except Exception as exc:
            logger.warning(f"MRP VERIFY conflict check failed: {exc}")
    return page_results
