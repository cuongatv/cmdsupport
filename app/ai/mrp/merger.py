"""LLM-assisted merge for MRP UPDATE operations."""

import asyncio

from loguru import logger

from app.ai.providers.base import LLMProvider

BODY_SHRINK_THRESHOLD = 0.7
MERGE_TIMEOUT = 120
MERGE_SYSTEM = """You merge two versions of the same enterprise wiki page. Preserve all factual content, numbers, procedures, names, wikilinks, and image markers from both versions. Remove only exact duplicates. Return only merged markdown."""


async def merge_page_content(
    llm: LLMProvider,
    existing_content: str,
    new_content: str,
    slug: str,
) -> str:
    """Merge incoming page content with existing page content, with safe fallback."""
    if not existing_content or len(existing_content.strip()) < 50:
        return new_content
    if existing_content.strip() == new_content.strip():
        return new_content

    prompt = (
        f"Merge these two versions of wiki page `{slug}`.\n\n"
        f"## EXISTING\n\n{existing_content}\n\n---\n\n"
        f"## INCOMING\n\n{new_content}\n\nReturn only merged markdown."
    )
    try:
        merged = (await asyncio.wait_for(
            llm.generate(prompt, system=MERGE_SYSTEM, temperature=0.1),
            timeout=MERGE_TIMEOUT,
        )).strip()
    except Exception as exc:
        logger.warning(f"MRP MERGE failed for {slug}: {exc}")
        return new_content

    min_len = int(max(len(existing_content), len(new_content)) * BODY_SHRINK_THRESHOLD)
    if len(merged) < min_len:
        logger.warning(f"MRP MERGE rejected for {slug}: merged body too short")
        return new_content
    return merged
