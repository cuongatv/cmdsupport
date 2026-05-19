# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAny=false, reportUnknownParameterType=false
"""Non-mutating preview for wiki taxonomy reclassification."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import cast

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ConsultingRuleProduct, WikiPage
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


async def _load_pages(
    session: AsyncSession,
    *,
    source_id: uuid.UUID | str | None,
    page_ids: Sequence[uuid.UUID | str] | None,
    scope_type: str,
    scope_id: uuid.UUID | None,
    limit: int | None,
) -> list[WikiPage]:
    stmt = select(WikiPage).order_by(WikiPage.updated_at.desc(), WikiPage.id)
    if page_ids:
        coerced_page_ids = [_coerce_uuid(page_id) for page_id in page_ids]
        stmt = stmt.where(WikiPage.id.in_(coerced_page_ids))
    elif source_id is not None:
        stmt = stmt.where(WikiPage.source_ids.any(_coerce_uuid(source_id)))
    else:
        stmt = stmt.where(_scope_filter(scope_type, scope_id))
    if limit is not None:
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
) -> dict[str, object]:
    """Compute a dry-run taxonomy reclassification diff for existing wiki pages.

    This service performs SELECT-only reads, invokes the shared classifier, and
    returns the old-vs-new taxonomy slugs plus impact flags. It never calls wiki
    write helpers and never mutates ``WikiPage`` rows.
    """
    pages = await _load_pages(
        session,
        source_id=source_id,
        page_ids=page_ids,
        scope_type=scope_type,
        scope_id=scope_id,
        limit=limit,
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
    return {
        "preview_id": _preview_id([page.id for page in pages], version_seed),
        "page_count": len(preview_pages),
        "flagged_count": sum(1 for page in preview_pages if page["impact_flags"]),
        "pages": preview_pages,
    }
