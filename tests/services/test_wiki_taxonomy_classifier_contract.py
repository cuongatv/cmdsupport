"""Contract tests for the future wiki taxonomy classifier service.

These tests pin the shared result contract and the fallback policy before the
implementation lands. The module is skipped cleanly until T6 exists.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

wiki_taxonomy_classifier = pytest.importorskip(
    "app.services.wiki_taxonomy_classifier", reason="T6 not yet landed"
)
from app.services.wiki_taxonomy_classifier import classify_page_candidate

pytestmark = pytest.mark.asyncio

BODY_SECRET_MARKER = "BODY_SECRET_MARKER_321"
BODY_EXCERPT = (
    "# Working capital loan\n\n"
    "Gói tín dụng SME dành cho doanh nghiệp nhỏ và vừa cần vốn quay vòng.\n\n"
    f"Fixture body contains {BODY_SECRET_MARKER} for no-leak assertions.\n\n"
    "Working capital loan helps SMEs manage cash flow and short-term funding.\n"
)


def _candidate_kwargs() -> dict[str, object]:
    return {
        "title": "Working capital loan for SMEs",
        "summary": "Bilingual SME product page fixture.",
        "page_type": "entity",
        "body_excerpt": BODY_EXCERPT,
        "source_taxonomy_slugs": ["supporting_knowledge.source_background"],
        "source_ids": ["source-123"],
        "existing_slugs": [],
        "rule_linked": False,
    }


def _assert_contract_shape(result: object) -> dict[str, object]:
    assert isinstance(result, dict), f"expected dict-like result, got {type(result)!r}"

    expected_keys = {
        "slugs",
        "confidence",
        "rationale",
        "needs_review",
        "classifier_version",
    }
    assert expected_keys.issubset(result.keys())

    slugs = result["slugs"]
    confidence = result["confidence"]
    rationale = result["rationale"]
    needs_review = result["needs_review"]
    classifier_version = result["classifier_version"]

    assert isinstance(slugs, list)
    assert slugs, "slugs must not be empty"
    assert all(isinstance(slug, str) and slug for slug in slugs)

    assert isinstance(confidence, (float, int))
    assert 0.0 <= float(confidence) <= 1.0

    assert isinstance(rationale, str)
    assert rationale.strip(), "rationale must be non-empty"

    assert isinstance(needs_review, bool)

    assert isinstance(classifier_version, str)
    assert classifier_version.strip(), "classifier_version must be non-empty"

    return result


async def _call_classifier(provider_payload: str) -> dict[str, object]:
    mock_llm = Mock()
    mock_llm.generate = AsyncMock(return_value=provider_payload)
    mock_llm.generate_with_tools = AsyncMock(return_value=provider_payload)

    mock_registry = Mock()
    mock_registry.get_llm = AsyncMock(return_value=mock_llm)

    session = Mock()

    with patch.object(
        wiki_taxonomy_classifier,
        "ProviderRegistry",
        return_value=mock_registry,
    ):
        result = await classify_page_candidate(
            session,
            **_candidate_kwargs(),
        )

    return _assert_contract_shape(result)


async def test_classify_page_candidate_high_confidence_product_page():
    payload = json.dumps(
        {
            "slugs": ["business_object.product_service"],
            "confidence": 0.92,
            "rationale": "Clear SME working capital product page.",
            "needs_review": False,
            "classifier_version": "taxonomy-v1",
        },
        ensure_ascii=False,
    )

    result = await _call_classifier(payload)

    assert result["slugs"] == ["business_object.product_service"]
    assert float(result["confidence"]) >= 0.80
    assert result["needs_review"] is False
    assert BODY_SECRET_MARKER not in result["rationale"]


async def test_classify_page_candidate_low_confidence_falls_back_to_other():
    payload = json.dumps(
        {
            "slugs": ["supporting_knowledge.other"],
            "confidence": 0.41,
            "rationale": "Ambiguous content; use safe fallback.",
            "needs_review": True,
            "classifier_version": "taxonomy-v1",
        },
        ensure_ascii=False,
    )

    result = await _call_classifier(payload)

    assert result["slugs"] == ["supporting_knowledge.other"]
    assert float(result["confidence"]) < 0.60
    assert result["needs_review"] is True
    assert BODY_SECRET_MARKER not in result["rationale"]


async def test_classify_page_candidate_provider_failure_falls_back_to_other():
    mock_llm = Mock()
    mock_llm.generate = AsyncMock(side_effect=RuntimeError("provider exploded"))
    mock_llm.generate_with_tools = AsyncMock(side_effect=RuntimeError("provider exploded"))

    mock_registry = Mock()
    mock_registry.get_llm = AsyncMock(return_value=mock_llm)

    with patch.object(
        wiki_taxonomy_classifier,
        "ProviderRegistry",
        return_value=mock_registry,
    ):
        result = await classify_page_candidate(
            mock_registry,
            **_candidate_kwargs(),
        )

    result = _assert_contract_shape(result)
    assert result["slugs"] == ["supporting_knowledge.other"]
    assert result["needs_review"] is True
    assert BODY_SECRET_MARKER not in result["rationale"]


async def test_classify_page_candidate_rationale_never_leaks_body_marker():
    payload = json.dumps(
        {
            "slugs": ["business_object.product_service"],
            "confidence": 0.88,
            "rationale": "Bilingual product page with clear product signals.",
            "needs_review": False,
            "classifier_version": "taxonomy-v1",
        },
        ensure_ascii=False,
    )

    result = await _call_classifier(payload)

    assert BODY_SECRET_MARKER in BODY_EXCERPT
    assert BODY_SECRET_MARKER not in result["rationale"]


async def test_classify_mixed_tier_forces_review():
    payload = json.dumps(
        {
            "slugs": [
                "business_object.product_service",
                "supporting_knowledge.general_context",
            ],
            "confidence": 0.91,
            "rationale": "Primary product page with context.",
            "needs_review": False,
            "classifier_version": "taxonomy-v1",
        },
        ensure_ascii=False,
    )

    result = await _call_classifier(payload)

    assert result["slugs"] == [
        "business_object.product_service",
        "supporting_knowledge.general_context",
    ]
    assert result["needs_review"] is True
    assert "business/supporting" in str(result["rationale"])


async def test_classify_caps_slug_count_at_two():
    payload = json.dumps(
        {
            "slugs": [
                "business_object.product_service",
                "business_object.target_customer",
                "business_object.process_form",
                "business_object.risk_compliance",
                "supporting_knowledge.general_context",
            ],
            "confidence": 0.93,
            "rationale": "Over-broad but valid classifier response.",
            "needs_review": False,
            "classifier_version": "taxonomy-v1",
        },
        ensure_ascii=False,
    )

    result = await _call_classifier(payload)

    assert len(result["slugs"]) <= 2
    assert result["slugs"] == [
        "business_object.product_service",
        "business_object.target_customer",
    ]
