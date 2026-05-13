"""Phase 0 triage and Phase 1 MAP extraction for the MRP pipeline."""

import asyncio
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.base import LLMProvider
from app.utils.progress import ProgressTracker

CHUNK_TARGET_CHARS = 20_000
OVERLAP_CHARS = 1_000
MAX_MAP_CONCURRENCY = 6
EXTRACT_TIMEOUT = 120
OVERLAP_SEPARATOR = "[…context from previous section…]\n"


@dataclass
class DocumentChunk:
    index: int
    start_char: int
    end_char: int
    section_path: str
    text: str
    overlap_prefix_len: int = field(default=0)


def classify_strategy(full_text: str, outline_json: Optional[list]) -> str:
    """Return the MRP strategy based on document size."""
    del outline_json
    text_len = len(full_text)
    if text_len < 30_000:
        return "single_pass"
    if text_len <= 200_000:
        return "standard"
    return "hierarchical"


def _flatten_outline(nodes: list, depth: int = 0) -> list[dict]:
    result: list[dict] = []
    for node in nodes:
        result.append({**node, "_depth": depth})
        children = node.get("children") or []
        if children:
            result.extend(_flatten_outline(children, depth + 1))
    return result


def build_chunks(
    full_text: str,
    outline_json: Optional[list],
    strategy: str,
) -> list[DocumentChunk]:
    """Split source text into deterministic chunks, preferring outline sections."""
    del strategy
    flat = _flatten_outline(outline_json or [])
    nodes = [
        node for node in flat
        if node.get("level", 99) <= 2
        and isinstance(node.get("char_start"), int)
        and isinstance(node.get("char_end"), int)
    ]
    nodes.sort(key=lambda node: node["char_start"])
    if not nodes:
        return _sliding_window_chunks(full_text)

    chunks: list[DocumentChunk] = []
    current_start: Optional[int] = None
    current_end = 0
    current_sections: list[str] = []
    previous_body_end = 0

    def _make_chunk(index: int, start: int, end: int, sections: list[str]) -> DocumentChunk:
        nonlocal previous_body_end
        body = full_text[start:end]
        if index > 0 and previous_body_end > 0 and previous_body_end <= start:
            overlap_start = max(0, previous_body_end - OVERLAP_CHARS)
            prefix = OVERLAP_SEPARATOR + full_text[overlap_start:previous_body_end] + "\n"
        else:
            prefix = ""
        return DocumentChunk(
            index=index,
            start_char=start,
            end_char=end,
            section_path=" > ".join(sections) if sections else f"chunk_{index}",
            text=prefix + body,
            overlap_prefix_len=len(prefix),
        )

    for node in nodes:
        start = max(0, node["char_start"])
        end = min(node["char_end"], len(full_text))
        title = str(node.get("title") or f"section_{len(chunks)}")
        if current_start is None:
            current_start = start
            current_end = end
            current_sections = [title]
            continue

        if current_end - current_start + (end - start) > CHUNK_TARGET_CHARS:
            chunk = _make_chunk(len(chunks), current_start, current_end, current_sections)
            chunks.append(chunk)
            previous_body_end = current_end
            current_start = start
            current_end = end
            current_sections = [title]
        else:
            current_end = max(current_end, end)
            current_sections.append(title)

    if current_start is not None:
        chunk = _make_chunk(len(chunks), current_start, len(full_text), current_sections)
        chunks.append(chunk)

    return chunks or _sliding_window_chunks(full_text)


def _sliding_window_chunks(full_text: str) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    previous_end = 0
    for index, start in enumerate(range(0, len(full_text), CHUNK_TARGET_CHARS)):
        end = min(start + CHUNK_TARGET_CHARS, len(full_text))
        if index > 0:
            overlap_start = max(0, previous_end - OVERLAP_CHARS)
            prefix = OVERLAP_SEPARATOR + full_text[overlap_start:previous_end] + "\n"
        else:
            prefix = ""
        chunks.append(DocumentChunk(
            index=index,
            start_char=start,
            end_char=end,
            section_path=f"chunk_{index}",
            text=prefix + full_text[start:end],
            overlap_prefix_len=len(prefix),
        ))
        previous_end = end
    return chunks


EXTRACTION_SYSTEM = """You are a deterministic knowledge extraction engine. Return only valid JSON matching the requested schema. Preserve the source language and do not invent facts."""

EXTRACTION_PROMPT_TEMPLATE = """## Document section
Section path: {section_path}
Character range in full document: {start_char}-{end_char}
{context_note}

## Text
{chunk_text}

Extract structured knowledge and return this exact JSON shape:
{{
  "entities": [{{"name": "string", "type": "person|org|product|regulation|location|system|equipment|other", "aliases": ["string"], "local_offset": 0}}],
  "concepts": [{{"term": "string", "definition_excerpt": "string", "local_offset": 0}}],
  "claims": [{{"statement": "string", "subject": "string", "local_offset": 0, "evidence_length": 200, "confidence": "explicit"}}],
  "relations": [{{"from": "string", "to": "string", "type": "string"}}],
  "topics": ["string"]
}}

Rules:
- local_offset starts at the first character of the actual document section body, not the overlap context.
- Absolute offset will be computed as {start_char} + local_offset.
- confidence must be explicit or inferred.
- Return empty arrays when nothing is found.
- Return only JSON.
"""


def _build_extraction_prompt(chunk: DocumentChunk) -> str:
    context_note = (
        "The chunk starts with overlap context. local_offset must start after the separator."
        if chunk.overlap_prefix_len else ""
    )
    return EXTRACTION_PROMPT_TEMPLATE.format(
        section_path=chunk.section_path,
        start_char=chunk.start_char,
        end_char=chunk.end_char,
        context_note=context_note,
        chunk_text=chunk.text,
    )


def _parse_json_object(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        last_brace = cleaned.rfind("}")
        if last_brace < 0:
            raise
        parsed = json.loads(cleaned[: last_brace + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Extraction response must be a JSON object")
    return parsed


def _convert_offsets(extract: dict, chunk: DocumentChunk) -> dict:
    for key in ("entities", "concepts", "claims"):
        items = extract.get(key)
        if not isinstance(items, list):
            extract[key] = []
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            local_offset = item.pop("local_offset", 0) or 0
            try:
                offset_int = int(local_offset)
            except (TypeError, ValueError):
                offset_int = 0
            item["absolute_offset"] = chunk.start_char + max(0, offset_int)
    return extract


async def extract_chunk(llm: LLMProvider, chunk: DocumentChunk) -> dict:
    """Run the LLM extraction call for one chunk."""
    raw = await asyncio.wait_for(
        llm.generate(
            _build_extraction_prompt(chunk),
            system=EXTRACTION_SYSTEM,
            temperature=0.1,
        ),
        timeout=EXTRACT_TIMEOUT,
    )
    return _convert_offsets(_parse_json_object(raw), chunk)


async def run_map_phase(
    session: AsyncSession,
    source_id: uuid.UUID,
    full_text: str,
    outline_json: Optional[list],
    tracker: ProgressTracker,
    llm: LLMProvider,
) -> tuple[str, list]:
    """Run triage + MAP, persisting every chunk result for resume."""
    from app.database.models import Source, SourceChunkExtract

    strategy = classify_strategy(full_text, outline_json)
    chunks = build_chunks(full_text, outline_json, strategy)
    logger.info(f"MRP MAP: source={source_id} strategy={strategy} chunks={len(chunks)}")

    source = await session.get(Source, source_id)
    if source:
        source.pipeline_strategy = strategy
        source.pipeline_phase = "map"
        await session.commit()

    existing_rows = (await session.execute(
        select(SourceChunkExtract).where(SourceChunkExtract.source_id == source_id)
    )).scalars().all()
    rows_by_index = {row.chunk_index: row for row in existing_rows}

    for chunk in chunks:
        if chunk.index not in rows_by_index:
            row = SourceChunkExtract(
                source_id=source_id,
                chunk_index=chunk.index,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                section_path=chunk.section_path,
                status="pending",
            )
            session.add(row)
            rows_by_index[chunk.index] = row
    await session.commit()

    existing_rows = (await session.execute(
        select(SourceChunkExtract).where(SourceChunkExtract.source_id == source_id)
    )).scalars().all()
    rows_by_index = {row.chunk_index: row for row in existing_rows}
    pending_chunks = [chunk for chunk in chunks if rows_by_index[chunk.index].status != "done"]
    done_count = len(chunks) - len(pending_chunks)

    semaphore = asyncio.Semaphore(MAX_MAP_CONCURRENCY)
    commit_lock = asyncio.Lock()
    completed = done_count

    async def _run_one(chunk: DocumentChunk) -> None:
        nonlocal completed
        async with semaphore:
            row = rows_by_index[chunk.index]
            try:
                extract = await extract_chunk(llm, chunk)
                async with commit_lock:
                    row.extract_json = extract
                    row.status = "done"
                    row.error_message = None
                    await session.commit()
                    completed += 1
            except Exception as exc:
                logger.warning(f"MRP MAP chunk {chunk.index} failed: {exc}")
                async with commit_lock:
                    row.status = "error"
                    row.error_message = str(exc)[:500]
                    await session.commit()
            pct = 10 + int(40 * completed / max(len(chunks), 1))
            await tracker.update(pct, f"Extracting chunk {chunk.index + 1}/{len(chunks)}...")

    await asyncio.gather(*[_run_one(chunk) for chunk in pending_chunks])

    for chunk in [chunk for chunk in chunks if rows_by_index[chunk.index].status == "error"]:
        row = rows_by_index[chunk.index]
        try:
            row.extract_json = await extract_chunk(llm, chunk)
            row.status = "done"
            row.error_message = None
            await session.commit()
        except Exception as exc:
            logger.warning(f"MRP MAP chunk {chunk.index} retry failed: {exc}")

    done_rows = [rows_by_index[chunk.index] for chunk in chunks if rows_by_index[chunk.index].status == "done"]
    return strategy, done_rows
