# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAny=false, reportUnknownParameterType=false
"""Shared wiki page taxonomy classifier service."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import TypeAlias, cast

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.registry import ProviderRegistry

CLASSIFIER_VERSION = "taxonomy-v1"
CONFIDENCE_AUTO_APPLY = 0.80
CONFIDENCE_REVIEW_FLOOR = 0.60
BODY_EXCERPT_CHARS = 600
FALLBACK_SLUG = "supporting_knowledge.other"
MAX_TAXONOMY_SLUGS = 2
MIXED_TIER_REVIEW_RATIONALE = "Hỗn hợp business/supporting cần review."

ClassifierResult: TypeAlias = dict[str, object]
JsonPayload: TypeAlias = dict[str, object]

VALID_TAXONOMY_SLUGS = frozenset(
    {
        "business_object.product_service",
        "business_object.target_customer",
        "business_object.non_credit_development_tool",
        "business_object.credit_development_tool",
        "business_object.campaign_program",
        "business_object.policy_mechanism",
        "business_object.eligibility_condition",
        "business_object.process_form",
        "business_object.risk_compliance",
        "business_object.industry_segment",
        "business_object.region_channel",
        "business_object.other",
        "supporting_knowledge.general_context",
        "supporting_knowledge.term_explanation",
        "supporting_knowledge.operational_guidance",
        "supporting_knowledge.source_background",
        FALLBACK_SLUG,
    }
)

SYSTEM_PROMPT = """\
You classify wiki page candidates into the seeded BIDV KHDN taxonomy.
Do not translate body content. Only output JSON.
Return exactly: slugs, confidence, rationale, needs_review, classifier_version.
The rationale must be concise and must not quote or repeat body text.
"""

PROMPT_TEMPLATE = """\
## Candidate page
Title: {title}
Summary: {summary}
Page type: {page_type}
Rule linked: {rule_linked}

## Source taxonomy slugs
{source_taxonomy_slugs}

## Source IDs
{source_ids}

## Existing page taxonomy slugs
{existing_slugs}

## Body excerpt, truncated to {excerpt_chars} chars
{body_excerpt}

## Valid taxonomy slugs
{valid_slugs}

Choose the best primary taxonomy slug. Use at most two slugs only when a secondary
classification is genuinely useful and non-conflicting. Return raw JSON only:
{{
  "slugs": ["<one of the valid taxonomy slugs>"],
  "confidence": 0.0,
  "rationale": "<short reason without body quotes>",
  "needs_review": true,
  "classifier_version": "{classifier_version}"
}}
"""


def _synthesize_rationale(
    *,
    slugs: Sequence[str],
    confidence: float,
    needs_review: bool,
    fallback_reason: str | None = None,
    mixed_tier: bool = False,
) -> str:
    if fallback_reason is not None:
        return f"Fallback {FALLBACK_SLUG} (lý do: {fallback_reason})."
    if mixed_tier:
        return MIXED_TIER_REVIEW_RATIONALE

    slug_text = ", ".join(slugs)
    review_suffix = "; cần review" if needs_review else ""
    return f"Phân loại {slug_text} với độ tin cậy {confidence:.2f}{review_suffix}."


def _safe_fallback(reason: str = "provider error") -> ClassifierResult:
    confidence = 0.0
    needs_review = True
    return {
        "slugs": [FALLBACK_SLUG],
        "confidence": confidence,
        "rationale": _synthesize_rationale(
            slugs=[FALLBACK_SLUG],
            confidence=confidence,
            needs_review=needs_review,
            fallback_reason=reason,
        ),
        "needs_review": needs_review,
        "classifier_version": CLASSIFIER_VERSION,
    }


def _format_list(values: Sequence[str] | None) -> str:
    if not values:
        return "  (none)"
    return "\n".join(f"  - {value}" for value in values)


def _truncate_excerpt(body_excerpt: str | None) -> str:
    return (body_excerpt or "")[:BODY_EXCERPT_CHARS]


def _strip_json_fences(raw: str) -> str:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _parse_provider_json(raw: object) -> JsonPayload | None:
    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, str):
        return None
    try:
        parsed = json.loads(_strip_json_fences(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, Mapping):
        return None
    return dict(cast(Mapping[str, object], parsed))


def _coerce_string_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    slugs = [item for item in value if isinstance(item, str) and item]
    return slugs or None


def _slug_tier(slug: str) -> str | None:
    if slug.startswith("business_object."):
        return "business"
    if slug.startswith("supporting_knowledge."):
        return "supporting"
    return None


def _has_mixed_business_supporting_tiers(slugs: Sequence[str]) -> bool:
    tiers = {_slug_tier(slug) for slug in slugs}
    return "business" in tiers and "supporting" in tiers


def _normalize_result(payload: JsonPayload) -> ClassifierResult:
    slugs = _coerce_string_list(payload.get("slugs"))
    if slugs is None:
        logger.warning("Wiki taxonomy classifier returned missing or invalid slugs")
        return _safe_fallback(reason="invalid slugs")

    invalid_slugs = [slug for slug in slugs if slug not in VALID_TAXONOMY_SLUGS]
    if invalid_slugs:
        logger.warning(
            "Wiki taxonomy classifier returned invalid taxonomy slugs: {}",
            invalid_slugs,
        )
        return _safe_fallback(reason="invalid slug")

    slugs = slugs[:MAX_TAXONOMY_SLUGS]

    confidence_value = payload.get("confidence")
    if isinstance(confidence_value, bool) or not isinstance(
        confidence_value,
        int | float | str,
    ):
        logger.warning("Wiki taxonomy classifier returned missing or invalid confidence")
        return _safe_fallback(reason="non-numeric confidence")
    try:
        confidence = float(confidence_value)
    except ValueError:
        logger.warning("Wiki taxonomy classifier returned missing or invalid confidence")
        return _safe_fallback(reason="non-numeric confidence")

    if not 0.0 <= confidence <= 1.0:
        logger.warning("Wiki taxonomy classifier confidence out of range: {}", confidence)
        return _safe_fallback(reason="confidence out of range")

    if "rationale" not in payload or "needs_review" not in payload:
        logger.warning("Wiki taxonomy classifier returned JSON missing required keys")
        return _safe_fallback(reason="missing required keys")

    has_mixed_tiers = _has_mixed_business_supporting_tiers(slugs)

    if confidence < CONFIDENCE_REVIEW_FLOOR:
        needs_review = True
        if slugs != [FALLBACK_SLUG]:
            logger.warning(
                "Wiki taxonomy classifier low confidence {}; coercing to safe fallback",
                confidence,
            )
            slugs = [FALLBACK_SLUG]
            confidence = 0.0
    elif confidence < CONFIDENCE_AUTO_APPLY:
        needs_review = True
    else:
        needs_review = False

    if has_mixed_tiers:
        needs_review = True

    rationale = _synthesize_rationale(
        slugs=slugs,
        confidence=confidence,
        needs_review=needs_review,
        mixed_tier=has_mixed_tiers,
    )

    return {
        "slugs": slugs,
        "confidence": confidence,
        "rationale": rationale,
        "needs_review": needs_review,
        "classifier_version": CLASSIFIER_VERSION,
    }


async def classify_page_candidate(
    session: AsyncSession,
    *,
    title: str,
    summary: str,
    page_type: str,
    body_excerpt: str,
    source_taxonomy_slugs: Sequence[str] | None = None,
    source_ids: Sequence[str] | None = None,
    existing_slugs: Sequence[str] | None = None,
    rule_linked: bool = False,
) -> ClassifierResult:
    """Classify a candidate wiki page into the shared BIDV taxonomy."""
    excerpt = _truncate_excerpt(body_excerpt)
    prompt = PROMPT_TEMPLATE.format(
        title=title or "(untitled)",
        summary=summary or "(none)",
        page_type=page_type or "(unknown)",
        rule_linked=bool(rule_linked),
        source_taxonomy_slugs=_format_list(source_taxonomy_slugs),
        source_ids=_format_list(source_ids),
        existing_slugs=_format_list(existing_slugs),
        body_excerpt=excerpt,
        excerpt_chars=BODY_EXCERPT_CHARS,
        valid_slugs=_format_list(sorted(VALID_TAXONOMY_SLUGS)),
        classifier_version=CLASSIFIER_VERSION,
    )

    try:
        llm = await ProviderRegistry(session).get_llm()
        raw = await llm.generate(
            prompt=prompt,
            system=SYSTEM_PROMPT,
            max_tokens=512,
            temperature=0,
        )
    except Exception as exc:
        logger.warning("Wiki taxonomy classifier provider error: {}", exc)
        return _safe_fallback()

    payload = _parse_provider_json(raw)
    if payload is None:
        logger.warning("Wiki taxonomy classifier returned invalid JSON")
        return _safe_fallback()

    return _normalize_result(payload)
