"""Phase 3 REFINE page writer for MRP."""

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.base import EmbeddingProvider, LLMProvider
from app.utils.progress import ProgressTracker

if TYPE_CHECKING:
    from app.database.models import SourceCompilationPlan

MAX_WRITER_CONCURRENCY = 4
WRITER_TIMEOUT = 300
SOURCE_CONTEXT_FALLBACK_CHARS = 60_000

_MODEL_CONTEXT_TOKENS: dict[str, int] = {
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.5-pro": 1_000_000,
    "gemini-2.0-flash": 1_000_000,
    "gpt-4.1-mini": 1_000_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "claude-sonnet-4-20250514": 1_000_000,
    "claude-haiku-4-20250514": 200_000,
}


@dataclass
class PageWriteResult:
    slug: str
    title: str
    page_type: str
    action: str
    content_md: str
    summary: str
    citations: list[dict] = field(default_factory=list)
    entity_names: list[str] = field(default_factory=list)
    related_kb_pages: list[str] = field(default_factory=list)


def assemble_evidence(plan_item: dict, claims: list[dict], full_text: str) -> list[dict]:
    entity_names = {str(name).lower() for name in plan_item.get("entity_names", [])}
    evidence: list[dict] = []
    for claim in claims:
        subject = str(claim.get("subject") or "")
        subject_lower = subject.lower()
        if entity_names and not (subject_lower in entity_names or any(name in subject_lower for name in entity_names)):
            continue
        offset = max(0, int(claim.get("absolute_offset") or 0))
        length = min(max(50, int(claim.get("evidence_length") or 200)), 500)
        evidence.append({
            "statement": claim.get("statement", ""),
            "subject": subject,
            "confidence": claim.get("confidence", "explicit"),
            "source_excerpt": full_text[offset: offset + length] if full_text else "",
            "absolute_offset": offset,
            "evidence_length": length,
        })
    return evidence


WRITER_SYSTEM = """You are an enterprise knowledge wiki writer.

Mindset: compile, do not summarize. Preserve concrete details, numbers, procedures, regulations, examples, exceptions, roles, definitions, and cause-effect statements. Drop boilerplate and marketing filler.

Language rule: write in the SAME LANGUAGE as the source document. Never translate content.

Structure: opening paragraph, H2 sections, wikilinks only to allowed slugs, and a See also section when useful. Preserve image markers exactly. Do not include footnote or citation sections.
"""


def _source_context_budget(model_id: Optional[str]) -> int:
    if not model_id:
        return SOURCE_CONTEXT_FALLBACK_CHARS
    context_tokens = _MODEL_CONTEXT_TOKENS.get(model_id)
    if context_tokens is None:
        for prefix, tokens in _MODEL_CONTEXT_TOKENS.items():
            if model_id.startswith(prefix):
                context_tokens = tokens
                break
    if context_tokens is None:
        return SOURCE_CONTEXT_FALLBACK_CHARS
    return min(int(context_tokens * 4 * 0.60), 800_000)


def _build_source_context(full_text: str, evidence: list[dict], model_id: Optional[str]) -> str:
    budget = _source_context_budget(model_id)
    if len(full_text) <= budget:
        return full_text

    windows: list[tuple[int, int]] = [(0, min(2_000, len(full_text)))]
    for item in evidence[:80]:
        offset = max(0, int(item.get("absolute_offset") or 0))
        windows.append((max(0, offset - 1_000), min(len(full_text), offset + 3_000)))
    windows.sort()

    merged: list[tuple[int, int]] = []
    for start, end in windows:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    parts: list[str] = []
    total = 0
    for start, end in merged:
        if total >= budget:
            break
        excerpt = full_text[start:end]
        remaining = budget - total
        if len(excerpt) > remaining:
            excerpt = excerpt[:remaining]
        parts.append(f"\n\n[Source excerpt {start}-{start + len(excerpt)}]\n{excerpt}")
        total += len(excerpt)
    return "".join(parts).strip()


def _format_evidence(evidence: list[dict]) -> str:
    lines: list[str] = []
    for index, item in enumerate(evidence, 1):
        lines.append(
            f"{index}. [{str(item.get('confidence', 'explicit')).upper()}] {item.get('subject', '')}\n"
            f"   Claim: {item.get('statement', '')}\n"
            f"   Source excerpt: {item.get('source_excerpt', '')}"
        )
    return "\n\n".join(lines) or "(no pre-extracted evidence; use the source text)"


WRITER_PROMPT = """## Task
{action} this wiki page.

## Page specification
- Slug: {slug}
- Title: {title}
- Type: {page_type}

## Available pages
Only use these slugs for wikilinks:
{available_slugs}

{existing_section}
## Source document text
{source_context}

## Evidence checklist
{evidence_blocks}

Write the complete markdown page. Return only markdown.
"""


async def _write_page(
    llm: LLMProvider,
    plan_item: dict,
    evidence: list[dict],
    existing_content: Optional[str],
    all_plan_slugs: list[str],
    source_context: str,
) -> tuple[str, str, list[dict]]:
    own_slug = str(plan_item.get("slug") or "")
    available = [slug for slug in all_plan_slugs if slug and slug != own_slug]
    prompt = WRITER_PROMPT.format(
        action=str(plan_item.get("action") or "CREATE").upper(),
        slug=own_slug,
        title=plan_item.get("title") or own_slug,
        page_type=plan_item.get("page_type") or "concept",
        available_slugs="\n".join(f"- [[{slug}]]" for slug in available) or "(none)",
        existing_section=f"## Existing content\n{existing_content}\n\n" if existing_content else "",
        source_context=source_context or "(source text unavailable)",
        evidence_blocks=_format_evidence(evidence),
    )
    raw = await asyncio.wait_for(
        llm.generate(prompt, system=WRITER_SYSTEM, temperature=0.15),
        timeout=WRITER_TIMEOUT,
    )
    content = raw.strip()
    summary = ""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            summary = stripped[:300]
            break
    return content, summary or str(plan_item.get("title") or own_slug), []


async def run_refine_phase(
    session: AsyncSession,
    source,
    plan: "SourceCompilationPlan",
    chunk_extracts: list,
    full_text: str,
    llm: LLMProvider,
    embedding_provider: Optional[EmbeddingProvider],
    kt_slug: Optional[str],
    tracker: ProgressTracker,
) -> list[PageWriteResult]:
    del chunk_extracts, embedding_provider, kt_slug
    from app.services import wiki_service

    plan_dict = plan.plan_json or {}
    pages = sorted(plan_dict.get("pages", []) or [], key=lambda item: item.get("priority", 99))
    claims = plan_dict.get("_claims", []) or []
    all_plan_slugs = [str(item.get("slug") or "") for item in pages if item.get("slug")]
    scope_type = source.scope_type or "global"
    scope_id = source.scope_id

    await tracker.update(78, f"Writing {len(pages)} wiki pages...")
    semaphore = asyncio.Semaphore(MAX_WRITER_CONCURRENCY)

    async def _write_one(plan_item: dict) -> Optional[PageWriteResult]:
        async with semaphore:
            slug = str(plan_item.get("slug") or "")
            if not slug:
                return None
            action = str(plan_item.get("action") or "CREATE").upper()
            existing_content: Optional[str] = None
            if action == "UPDATE":
                page = await wiki_service.get_page_by_slug(
                    session, slug, scope_type=scope_type, scope_id=scope_id
                )
                if page:
                    existing_content = page.content_md

            evidence = assemble_evidence(plan_item, claims, full_text)
            source_context = _build_source_context(full_text, evidence, llm.config.model_id)
            try:
                content_md, summary, citations = await _write_page(
                    llm,
                    plan_item,
                    evidence,
                    existing_content,
                    all_plan_slugs,
                    source_context,
                )
            except Exception as exc:
                logger.error(f"MRP writer failed for {slug}: {exc}")
                title = str(plan_item.get("title") or slug)
                content_md = f"# {title}\n\n(Page generation failed: {type(exc).__name__}: {str(exc)[:200]})"
                summary = title
                citations = []

            return PageWriteResult(
                slug=slug,
                title=str(plan_item.get("title") or slug),
                page_type=str(plan_item.get("page_type") or "concept"),
                action=action,
                content_md=content_md,
                summary=summary,
                citations=citations,
                entity_names=[str(name) for name in plan_item.get("entity_names", [])],
                related_kb_pages=[str(slug) for slug in plan_item.get("related_kb_pages", [])],
            )

    results = await asyncio.gather(*[_write_one(item) for item in pages])
    page_results = [result for result in results if result is not None]
    logger.info(f"MRP REFINE complete: {len(page_results)} pages for source={source.id}")
    return page_results
