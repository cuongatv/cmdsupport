# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAny=false, reportUnknownParameterType=false
"""Non-mutating preview for wiki taxonomy reclassification."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from typing import cast

from loguru import logger
from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ConsultingRuleProduct, WikiPage
from app.services import wiki_service
from app.services.wiki_taxonomy_classifier import (
    CLASSIFIER_VERSION,
    classify_page_candidate,
)

PREVIEW_NAMESPACE = uuid.UUID("8c2ec3ce-3e3b-4ca0-a64e-b0d08e2f99c5")
PREVIEW_TIMESTAMP_BUCKET = "static-v1"
BUSINESS_PREFIX = "business_object."
SUPPORTING_PREFIX = "supporting_knowledge."
OTHER_SUFFIX = ".other"


def _scope_filter(scope_type: str, scope_id: uuid.UUID | None):
    if scope_id is None:
        return and_(WikiPage.scope_type == scope_type, WikiPage.scope_id.is_(None))
    return and_(WikiPage.scope_type == scope_type, WikiPage.scope_id == scope_id)


def _coerce_uuid(value: uuid.UUID | str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _result_slugs(result: dict[str, object]) -> list[str]:
    raw_slugs = result.get("slugs")
    if not isinstance(raw_slugs, list):
        return []
    return [slug for slug in raw_slugs if isinstance(slug, str)]


def _result_confidence(result: dict[str, object]) -> float:
    raw_confidence = result.get("confidence", 0.0)
    if isinstance(raw_confidence, int | float | str):
        try:
            return float(raw_confidence)
        except ValueError:
            return 0.0
    return 0.0


def _result_string(result: dict[str, object], key: str, fallback: str = "") -> str:
    value = result.get(key)
    if isinstance(value, str):
        return value
    return fallback


def _result_bool(result: dict[str, object], key: str) -> bool:
    return bool(result.get(key))


def _preview_pages(preview: dict[str, object]) -> list[dict[str, object]]:
    raw_pages = preview.get("pages")
    if not isinstance(raw_pages, list):
        return []
    return [page for page in raw_pages if isinstance(page, dict)]


def _preview_string(preview: dict[str, object], key: str, fallback: str = "") -> str:
    value = preview.get(key)
    if isinstance(value, str):
        return value
    return fallback


def _preview_item_string(item: dict[str, object], key: str, fallback: str = "") -> str:
    value = item.get(key)
    if isinstance(value, str):
        return value
    return fallback


def _preview_item_bool(item: dict[str, object], key: str) -> bool:
    return bool(item.get(key))


def _preview_item_float(item: dict[str, object], key: str) -> float | None:
    value = item.get(key)
    if value is None:
        return None
    if isinstance(value, int | float | str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _preview_item_slugs(item: dict[str, object], key: str) -> list[str]:
    value = item.get(key)
    if not isinstance(value, list):
        return []
    return [slug for slug in value if isinstance(slug, str)]


def _preview_item_flags(item: dict[str, object]) -> list[str]:
    value = item.get("impact_flags")
    if not isinstance(value, list):
        return []
    return [flag for flag in value if isinstance(flag, str)]


def _has_tier(slugs: Sequence[str], prefix: str) -> bool:
    return any(slug.startswith(prefix) for slug in slugs)


def _only_tier(slugs: Sequence[str], prefix: str) -> bool:
    return bool(slugs) and all(slug.startswith(prefix) for slug in slugs)


def _tier_set(slugs: Sequence[str]) -> set[str]:
    tiers: set[str] = set()
    for slug in slugs:
        if slug.startswith(BUSINESS_PREFIX):
            tiers.add("business")
        elif slug.startswith(SUPPORTING_PREFIX):
            tiers.add("supporting")
        elif slug.endswith(OTHER_SUFFIX):
            tiers.add("other")
    return tiers


def _rule_linked_tier_change(
    old_slugs: Sequence[str],
    new_slugs: Sequence[str],
    rule_link_count: int,
) -> bool:
    if rule_link_count < 1:
        return False
    old_tiers = _tier_set(old_slugs)
    new_tiers = _tier_set(new_slugs)
    if "business" in old_tiers and new_tiers <= {"supporting"}:
        return True
    if "business" in old_tiers and any(slug.endswith(OTHER_SUFFIX) for slug in new_slugs):
        return True
    return old_tiers != new_tiers


def _impact_flags(
    *,
    old_slugs: Sequence[str],
    new_slugs: Sequence[str],
    confidence: float,
    rule_link_count: int,
) -> list[str]:
    flags: list[str] = []
    if confidence < 0.60:
        flags.append("low_confidence")
    if any(slug.endswith(OTHER_SUFFIX) for slug in new_slugs):
        flags.append("to_other")
    if _has_tier(old_slugs, BUSINESS_PREFIX) and _only_tier(new_slugs, SUPPORTING_PREFIX):
        flags.append("business_to_supporting")
    if _rule_linked_tier_change(old_slugs, new_slugs, rule_link_count):
        flags.append("rule_linked_tier_change")
    return flags


def _preview_id(page_ids: Sequence[uuid.UUID], classifier_version: str) -> str:
    """Stable uuid5 over sorted page ids, classifier version, and a static bucket.

    The bucket is intentionally static for T9 so repeated previews of the same
    page set/classifier version reuse the same id until the classifier contract
    changes. A future apply/orchestration layer can replace this with a time
    window bucket if previews need scheduled expiry semantics.
    """
    sorted_ids = ",".join(str(page_id) for page_id in sorted(page_ids, key=str))
    seed = f"{sorted_ids}|{classifier_version}|{PREVIEW_TIMESTAMP_BUCKET}"
    return str(uuid.uuid5(PREVIEW_NAMESPACE, seed))


async def _rule_link_counts(
    session: AsyncSession,
    page_ids: Sequence[uuid.UUID],
) -> dict[uuid.UUID, int]:
    if not page_ids:
        return {}
    result = await session.execute(
        select(ConsultingRuleProduct.wiki_page_id, func.count(ConsultingRuleProduct.id))
        .where(ConsultingRuleProduct.wiki_page_id.in_(page_ids))
        .group_by(ConsultingRuleProduct.wiki_page_id)
    )
    return {
        cast(uuid.UUID, wiki_page_id): int(count)
        for wiki_page_id, count in result.all()
        if wiki_page_id is not None
    }


def _base_pages_stmt(
    *,
    source_id: uuid.UUID | str | None,
    page_ids: Sequence[uuid.UUID | str] | None,
    scope_type: str,
    scope_id: uuid.UUID | None,
) -> Select[tuple[WikiPage]]:
    stmt = select(WikiPage).order_by(WikiPage.updated_at.desc(), WikiPage.id)
    if page_ids:
        coerced_page_ids = [_coerce_uuid(page_id) for page_id in page_ids]
        stmt = stmt.where(WikiPage.id.in_(coerced_page_ids))
    elif source_id is not None:
        stmt = stmt.where(WikiPage.source_ids.any(_coerce_uuid(source_id)))
    else:
        stmt = stmt.where(_scope_filter(scope_type, scope_id))
    return stmt


async def _count_pages(
    session: AsyncSession,
    *,
    source_id: uuid.UUID | str | None,
    page_ids: Sequence[uuid.UUID | str] | None,
    scope_type: str,
    scope_id: uuid.UUID | None,
    limit: int | None,
) -> int:
    base_stmt = _base_pages_stmt(
        source_id=source_id,
        page_ids=page_ids,
        scope_type=scope_type,
        scope_id=scope_id,
    ).order_by(None)
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = int((await session.execute(count_stmt)).scalar_one())
    if limit is not None:
        return min(total, max(0, int(limit)))
    return total


async def _load_pages(
    session: AsyncSession,
    *,
    source_id: uuid.UUID | str | None,
    page_ids: Sequence[uuid.UUID | str] | None,
    scope_type: str,
    scope_id: uuid.UUID | None,
    limit: int | None,
    page_size: int | None = None,
    page: int = 1,
) -> list[WikiPage]:
    stmt = _base_pages_stmt(
        source_id=source_id,
        page_ids=page_ids,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    if page_size is not None:
        normalized_page_size = max(1, int(page_size))
        normalized_page = max(1, int(page))
        offset = (normalized_page - 1) * normalized_page_size
        effective_limit = normalized_page_size
        if limit is not None:
            remaining = max(0, int(limit)) - offset
            if remaining <= 0:
                return []
            effective_limit = min(effective_limit, remaining)
        stmt = stmt.limit(effective_limit).offset(offset)
    elif limit is not None:
        stmt = stmt.limit(max(0, int(limit)))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def preview_reclassification(
    session: AsyncSession,
    *,
    source_id: uuid.UUID | str | None = None,
    page_ids: Sequence[uuid.UUID | str] | None = None,
    scope_type: str = "global",
    scope_id: uuid.UUID | None = None,
    limit: int | None = None,
    page_size: int | None = None,
    page: int = 1,
) -> dict[str, object]:
    """Compute a dry-run taxonomy reclassification diff for existing wiki pages.

    This service performs SELECT-only reads, invokes the shared classifier, and
    returns the old-vs-new taxonomy slugs plus impact flags. It never calls wiki
    write helpers and never mutates ``WikiPage`` rows.
    """
    normalized_page_size = max(1, int(page_size)) if page_size is not None else None
    normalized_page = max(1, int(page))
    total_count = None
    if normalized_page_size is not None:
        total_count = await _count_pages(
            session,
            source_id=source_id,
            page_ids=page_ids,
            scope_type=scope_type,
            scope_id=scope_id,
            limit=limit,
        )

    pages = await _load_pages(
        session,
        source_id=source_id,
        page_ids=page_ids,
        scope_type=scope_type,
        scope_id=scope_id,
        limit=limit,
        page_size=normalized_page_size,
        page=normalized_page,
    )
    rule_counts = await _rule_link_counts(session, [page.id for page in pages])

    preview_pages: list[dict[str, object]] = []
    classifier_versions: set[str] = set()
    for page in pages:
        old_slugs = list(page.knowledge_type_slugs or [])
        rule_link_count = rule_counts.get(page.id, 0)
        result = await classify_page_candidate(
            session,
            title=page.title,
            summary=page.summary,
            page_type=page.page_type,
            body_excerpt=(page.content_md or "")[:1200],
            source_taxonomy_slugs=None,
            source_ids=[str(source_id) for source_id in (page.source_ids or [])],
            existing_slugs=old_slugs,
            rule_linked=rule_link_count >= 1,
        )
        new_slugs = _result_slugs(result)
        confidence = _result_confidence(result)
        classifier_version = _result_string(
            result,
            "classifier_version",
            CLASSIFIER_VERSION,
        )
        classifier_versions.add(classifier_version)
        flags = _impact_flags(
            old_slugs=old_slugs,
            new_slugs=new_slugs,
            confidence=confidence,
            rule_link_count=rule_link_count,
        )
        preview_pages.append(
            {
                "wiki_page_id": str(page.id),
                "slug": page.slug,
                "title": page.title,
                "page_type": page.page_type,
                "old_slugs": old_slugs,
                "new_slugs": new_slugs,
                "confidence": confidence,
                "rationale": _result_string(result, "rationale"),
                "needs_review": _result_bool(result, "needs_review"),
                "classifier_version": classifier_version,
                "rule_link_count": rule_link_count,
                "impact_flags": flags,
            }
        )

    version_seed = ",".join(sorted(classifier_versions)) or CLASSIFIER_VERSION
    result: dict[str, object] = {
        "preview_id": _preview_id([page.id for page in pages], version_seed),
        "page_count": len(preview_pages),
        "flagged_count": sum(1 for page in preview_pages if page["impact_flags"]),
        "pages": preview_pages,
    }
    if normalized_page_size is not None:
        total_pages = (
            (total_count + normalized_page_size - 1) // normalized_page_size
            if total_count is not None
            else 0
        )
        result["page"] = normalized_page
        result["page_size"] = normalized_page_size
        result["total_pages"] = total_pages
        result["total_pages_estimated"] = False
        result["has_more"] = normalized_page < total_pages
    return result


async def iter_preview_pages(
    session: AsyncSession,
    *,
    source_id: uuid.UUID | str | None = None,
    page_ids: Sequence[uuid.UUID | str] | None = None,
    scope_type: str = "global",
    scope_id: uuid.UUID | None = None,
    page_size: int = 20,
) -> AsyncIterator[dict[str, object]]:
    """Yield paginated preview chunks until the selected wiki page set is exhausted."""
    normalized_page_size = max(1, int(page_size))
    current_page = 1
    while True:
        preview = await preview_reclassification(
            session,
            source_id=source_id,
            page_ids=page_ids,
            scope_type=scope_type,
            scope_id=scope_id,
            page_size=normalized_page_size,
            page=current_page,
        )
        yield preview
        if not preview.get("has_more"):
            break
        current_page += 1


async def apply_reclassification(
    session: AsyncSession,
    *,
    preview: dict[str, object],
    force_rule_linked_tier_change: bool = False,
    actor: object | None = None,
) -> dict[str, object]:
    """Apply taxonomy-only changes from a reclassification preview.

    The function is intentionally conservative: it re-loads every page by
    ``wiki_page_id`` and compares the desired taxonomy state to the current DB
    row before mutating. Writes go through ``wiki_service.apply_update`` so page
    ids, source ids, consulting rule links, wikilinks, and revisions keep using
    the normal wiki service path.
    """
    del actor  # Reserved for router/audit wiring in a later task.

    pages = _preview_pages(preview)
    result: dict[str, object] = {
        "preview_id": _preview_string(preview, "preview_id"),
        "applied_count": 0,
        "skipped_count": 0,
        "flagged_count": 0,
        "unchanged_count": 0,
        "applied_page_ids": [],
        "skipped_reasons": {},
    }
    applied_page_ids = cast(list[str], result["applied_page_ids"])
    skipped_reasons = cast(dict[str, list[str]], result["skipped_reasons"])
    applied_count = 0
    skipped_count = 0
    flagged_count = 0
    unchanged_count = 0

    for item in pages:
        page_id = _preview_item_string(item, "wiki_page_id")
        if not page_id:
            skipped_count += 1
            skipped_reasons.setdefault("<missing>", []).append("missing_wiki_page_id")
            continue

        reasons: list[str] = []
        flags = _preview_item_flags(item)
        if flags:
            flagged_count += 1
        if _preview_item_bool(item, "needs_review"):
            reasons.append("needs_review")
        if "rule_linked_tier_change" in flags and not force_rule_linked_tier_change:
            reasons.append("rule_linked_tier_change")
        if reasons:
            skipped_count += 1
            skipped_reasons[page_id] = reasons
            continue

        try:
            page_uuid = _coerce_uuid(page_id)
            page = await session.get(WikiPage, page_uuid)
            if page is None:
                skipped_count += 1
                skipped_reasons.setdefault(page_id, []).append("page_not_found")
                continue

            new_slugs = _preview_item_slugs(item, "new_slugs")
            confidence = _preview_item_float(item, "confidence")
            rationale = _preview_item_string(item, "rationale")
            needs_review = _preview_item_bool(item, "needs_review")
            classifier_version = _preview_item_string(
                item,
                "classifier_version",
                CLASSIFIER_VERSION,
            )

            current_slugs = list(page.knowledge_type_slugs or [])
            if current_slugs == new_slugs:
                unchanged_count += 1
                continue

            old_slugs = _preview_item_slugs(item, "old_slugs")
            if current_slugs != old_slugs:
                skipped_count += 1
                skipped_reasons.setdefault(page_id, []).append("stale_preview")
                continue

            updated = await wiki_service.apply_update(
                session,
                slug=page.slug,
                new_content_md=page.content_md or "",
                scope_type=page.scope_type,
                scope_id=page.scope_id,
                knowledge_type_slugs=new_slugs,
                taxonomy_confidence=confidence,
                taxonomy_rationale=rationale,
                taxonomy_needs_review=needs_review,
                taxonomy_classifier_version=classifier_version,
            )
            if updated is None:
                skipped_count += 1
                skipped_reasons.setdefault(page_id, []).append("page_not_found")
                continue
            applied_count += 1
            applied_page_ids.append(page_id)
        except Exception:
            logger.exception("apply_reclassification failed for wiki_page_id={}", page_id)
            raise

    result["applied_count"] = applied_count
    result["skipped_count"] = skipped_count
    result["flagged_count"] = flagged_count
    result["unchanged_count"] = unchanged_count
    return result
