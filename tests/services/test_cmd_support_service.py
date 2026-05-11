"""
Unit tests for ``app.services.cmd_support_service`` (W2-T10).

Verifies the cache reuse contract end-to-end through ``create_advice`` with a
fully mocked DB / ProviderRegistry / wiki retrieval stack — no Postgres and no
real LLM are required. Covers:

* reuse_status="new" on the first call for a fingerprint
* reuse_status="reused" when the same fingerprint AND source snapshot match
* reuse_status="refreshed" when the fingerprint matches but the source
  snapshot has changed (corpus drift)
* force_refresh=True bypasses the cache and always calls the LLM
* Different advice_language values produce different fingerprints → both miss
* ``_normalize_v2_result`` fills missing v2 fields whether the LLM emits a
  partial v2 payload or a legacy v1-shaped payload
* The ``AdviceDetail`` API response schema does NOT leak internal cache
  bookkeeping (input_fingerprint, source_snapshot_hash, retrieval_snapshot,
  refresh_reason)
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.cmd_support import AdviceDetail
from app.services.cmd_advisory_fingerprint import compute_source_snapshot_hash
from app.services.cmd_support_service import (
    V2_REQUIRED_DEFAULTS,
    _normalize_v2_result,
    create_advice,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------

def _make_wiki_page(
    *,
    page_id: Optional[uuid.UUID] = None,
    slug: str = "page-1",
    title: str = "Test Page",
    content: str = "Some context content about lending products.",
    source_ids: Optional[list[uuid.UUID]] = None,
) -> MagicMock:
    """Mock a WikiPage row with the attributes the service reads."""
    page = MagicMock()
    page.id = page_id or uuid.UUID("11111111-1111-1111-1111-111111111111")
    page.slug = slug
    page.title = title
    page.summary = "Test summary"
    page.content_md = content
    page.source_ids = source_ids or []
    return page


def _v2_llm_payload(language: str = "vi") -> dict[str, Any]:
    """A complete v2.0 JSON body for the mock LLM to return."""
    return {
        "schema_version": "v2.0",
        "advice_language": language,
        "customer_context": {
            "name": "ACME Corp",
            "province": None,
            "industry": None,
            "detected_needs": ["Vay vốn lưu động"],
        },
        "analysis": "Phân tích nhu cầu khách hàng.",
        "executive_thesis": "Tóm lược chiến lược.",
        "primary_products": [
            {"name": "Vay ngắn hạn", "rationale": "Phù hợp nhu cầu."},
        ],
        "cross_sell_products": [],
        "upsell_products": [],
        "operations_products": [],
        "digital_channels": [],
        "policies_incentives": [],
        "bundle_advantages": "Gói combo.",
        "recommendations": [
            {
                "title": "Vay vốn lưu động",
                "rationale": "Đáp ứng nhu cầu mở rộng kho.",
                "confidence": "high",
                "citations": [{"slug": "page-1", "title": "Test Page"}],
            }
        ],
        "red_flags": [],
        "offer_materials": [],
        "follow_up_questions": [],
        "coverage_gaps": [],
        "rm_disclaimer": "Disclaimer mẫu.",
    }


def _build_mock_db(existing_session: Any = None) -> AsyncMock:
    """Build an AsyncMock DB session whose ``execute`` returns a result whose
    ``scalar_one_or_none()`` yields ``existing_session``.

    ``db.add`` records every object added so tests can inspect what would have
    been persisted.
    """
    db = AsyncMock()
    added: list[Any] = []
    db.added = added
    db.add = MagicMock(side_effect=added.append)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=existing_session)
    db.execute = AsyncMock(return_value=mock_result)
    return db


class _MockEmbeddingProvider:
    """Stub embedding provider — returns a fixed vector for any input."""

    async def embed(self, text: str) -> list[float]:
        return [0.0] * 16


class _MockLLMProvider:
    """Stub LLM provider — returns a canned JSON string and counts calls."""

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls = 0

    async def generate(self, *args: Any, **kwargs: Any) -> str:
        self.calls += 1
        return self.payload


def _make_mock_registry(llm_provider: _MockLLMProvider) -> MagicMock:
    """Build a fake ProviderRegistry instance that hands out our stubs."""
    mock_config = MagicMock()
    mock_config.provider = MagicMock()
    mock_config.provider.value = "google"
    mock_config.model_id = "gemini-2.0-flash"

    registry = MagicMock()
    registry.get_embedding = AsyncMock(return_value=_MockEmbeddingProvider())
    registry.get_llm = AsyncMock(return_value=llm_provider)
    registry._load_config = AsyncMock(return_value=mock_config)
    return registry


def _patch_service(
    registry: MagicMock,
    wiki_results: list[tuple[Any, float]],
):
    """Compose all the service-level patches needed to run create_advice
    without any real infra. Returns a list of started patches; the caller is
    responsible for stopping them.
    """
    patches = [
        # ``cmd_support_service`` imports ProviderRegistry lazily inside
        # ``create_advice`` — patch the source module, not the service module.
        patch(
            "app.ai.registry.ProviderRegistry",
            return_value=registry,
        ),
        patch(
            "app.services.wiki_service.search_pages_semantic",
            new=AsyncMock(return_value=wiki_results),
        ),
        patch(
            "app.services.cmd_support_service.log_audit",
            new=AsyncMock(),
        ),
        patch(
            "app.services.cmd_support_service._log_anonymous_audit",
            new=AsyncMock(),
        ),
    ]
    return patches


# ---------------------------------------------------------------------------
# _normalize_v2_result — direct unit tests (no DB, no mocks)
# ---------------------------------------------------------------------------

async def test_v2_normalization_adds_missing_fields() -> None:
    """v2 JSON missing some v2 fields gets each default filled in."""
    incomplete: dict[str, object] = {
        "schema_version": "v2.0",
        "advice_language": "vi",
        "analysis": "x",
        "primary_products": [{"name": "Loan", "rationale": "fit"}],
        # missing executive_thesis, cross_sell_products, etc.
    }
    normalized = _normalize_v2_result(incomplete, "vi")

    for key in V2_REQUIRED_DEFAULTS:
        assert key in normalized, f"Missing v2 field after normalize: {key}"
    # Defaults applied for missing keys
    assert normalized["executive_thesis"] == ""
    assert normalized["cross_sell_products"] == []
    assert normalized["bundle_advantages"] == ""
    # Existing keys preserved
    assert normalized["primary_products"] == [
        {"name": "Loan", "rationale": "fit"}
    ]
    assert normalized["analysis"] == "x"
    # schema_version always forced to v2.0
    assert normalized["schema_version"] == "v2.0"
    assert normalized["advice_language"] == "vi"


async def test_v1_legacy_adapter_adds_v2_fields() -> None:
    """A v1-shaped payload (no schema_version, no v2 fields) is upgraded."""
    v1_payload: dict[str, object] = {
        "advice_language": "vi",
        "customer_context": {"name": "ACME"},
        "analysis": "y",
        "recommendations": [],
        "red_flags": [],
        "offer_materials": [],
        "follow_up_questions": [],
        "coverage_gaps": [],
        "rm_disclaimer": "d",
    }
    normalized = _normalize_v2_result(v1_payload, "en")

    # All v2 required fields are added
    for key in V2_REQUIRED_DEFAULTS:
        assert key in normalized
    assert normalized["schema_version"] == "v2.0"
    assert normalized["advice_language"] == "en"
    # v1 fields survive unchanged
    assert normalized["analysis"] == "y"
    assert normalized["customer_context"] == {"name": "ACME"}
    assert normalized["rm_disclaimer"] == "d"


# ---------------------------------------------------------------------------
# AdviceDetail schema — no internal cache fields leaked over the API
# ---------------------------------------------------------------------------

async def test_no_secrets_in_schema() -> None:
    """AdviceDetail (the public API response) must NOT expose internal
    cache/snapshot bookkeeping fields."""
    forbidden = {
        "input_fingerprint",
        "source_snapshot_hash",
        "retrieval_snapshot",
        "refresh_reason",
    }
    fields = set(AdviceDetail.model_fields.keys())
    leaked = forbidden & fields
    assert not leaked, f"AdviceDetail leaks internal fields: {leaked}"


# ---------------------------------------------------------------------------
# Cache behaviour — create_advice with mocked DB + LLM + retrieval
# ---------------------------------------------------------------------------

async def test_create_advice_new_call_no_cache() -> None:
    """First call for a fingerprint → reuse_status=='new' and the LLM was hit."""
    payload = json.dumps(_v2_llm_payload(language="vi"))
    llm = _MockLLMProvider(payload)
    registry = _make_mock_registry(llm)
    wiki_page = _make_wiki_page()
    db = _build_mock_db(existing_session=None)

    patches = _patch_service(registry, [(wiki_page, 0.9)])
    for p in patches:
        p.start()
    try:
        session_obj = await create_advice(
            db=db,
            user=None,
            customer_name="ACME",
            province_code=None,
            industry_code=None,
            needs="Cần vay vốn lưu động mở rộng kho",
            additional_context=None,
            customer_segment="sme",
            advice_language="vi",
        )
    finally:
        for p in patches:
            p.stop()

    assert llm.calls == 1, "LLM should be called for a fresh fingerprint"
    assert session_obj.reuse_status == "new"
    assert session_obj.status == "ready"
    assert session_obj.input_fingerprint is not None
    assert session_obj.source_snapshot_hash == compute_source_snapshot_hash(
        [wiki_page.id]
    )
    # Citation survived the post-LLM validation
    recs = session_obj.result_json["recommendations"]
    assert len(recs) == 1
    assert recs[0]["citations"] == [{"slug": "page-1", "title": "Test Page"}]
    # v2 normalization stamped the schema version
    assert session_obj.schema_version == "v2.0"


async def test_create_advice_reuse_on_same_fingerprint() -> None:
    """Second call with the same fingerprint + same source snapshot → 'reused'
    and the LLM is NOT called."""
    payload = json.dumps(_v2_llm_payload(language="vi"))
    llm = _MockLLMProvider(payload)
    registry = _make_mock_registry(llm)
    wiki_page = _make_wiki_page()
    matching_hash = compute_source_snapshot_hash([wiki_page.id])

    existing = MagicMock()
    existing.source_snapshot_hash = matching_hash
    existing.reuse_status = "new"
    existing.status = "ready"
    db = _build_mock_db(existing_session=existing)

    patches = _patch_service(registry, [(wiki_page, 0.9)])
    for p in patches:
        p.start()
    try:
        session_obj = await create_advice(
            db=db,
            user=None,
            customer_name="ACME",
            province_code=None,
            industry_code=None,
            needs="Cần vay vốn lưu động mở rộng kho",
            additional_context=None,
            customer_segment="sme",
            advice_language="vi",
        )
    finally:
        for p in patches:
            p.stop()

    assert llm.calls == 0, "LLM must NOT be called on a cache hit"
    assert session_obj is existing
    assert session_obj.reuse_status == "reused"
    db.refresh.assert_awaited_once_with(existing)


async def test_create_advice_refresh_on_source_change() -> None:
    """Same fingerprint but a different source snapshot → 'refreshed' and the
    LLM is re-called."""
    payload = json.dumps(_v2_llm_payload(language="vi"))
    llm = _MockLLMProvider(payload)
    registry = _make_mock_registry(llm)
    wiki_page = _make_wiki_page()

    existing = MagicMock()
    existing.source_snapshot_hash = "deadbeef" * 8  # 64 chars, but mismatched
    existing.reuse_status = "new"
    existing.status = "ready"
    db = _build_mock_db(existing_session=existing)

    patches = _patch_service(registry, [(wiki_page, 0.9)])
    for p in patches:
        p.start()
    try:
        session_obj = await create_advice(
            db=db,
            user=None,
            customer_name="ACME",
            province_code=None,
            industry_code=None,
            needs="Cần vay vốn lưu động mở rộng kho",
            additional_context=None,
            customer_segment="sme",
            advice_language="vi",
        )
    finally:
        for p in patches:
            p.stop()

    assert llm.calls == 1, "LLM must be re-called when source snapshot drifts"
    assert session_obj is not existing
    assert session_obj.reuse_status == "refreshed"
    assert session_obj.refresh_reason == "source_snapshot_hash_changed"


async def test_create_advice_force_refresh_bypasses_cache() -> None:
    """force_refresh=True skips the cache check entirely; LLM is always called
    and a brand-new session is created."""
    payload = json.dumps(_v2_llm_payload(language="vi"))
    llm = _MockLLMProvider(payload)
    registry = _make_mock_registry(llm)
    wiki_page = _make_wiki_page()

    # Even if a cached session existed, force_refresh must skip the lookup.
    poisoned = MagicMock()
    poisoned.source_snapshot_hash = compute_source_snapshot_hash([wiki_page.id])
    poisoned.reuse_status = "new"
    db = _build_mock_db(existing_session=poisoned)

    patches = _patch_service(registry, [(wiki_page, 0.9)])
    for p in patches:
        p.start()
    try:
        session_obj = await create_advice(
            db=db,
            user=None,
            customer_name="ACME",
            province_code=None,
            industry_code=None,
            needs="Cần vay vốn lưu động mở rộng kho",
            additional_context=None,
            customer_segment="sme",
            advice_language="vi",
            force_refresh=True,
        )
    finally:
        for p in patches:
            p.stop()

    assert llm.calls == 1, "force_refresh must always call the LLM"
    assert session_obj is not poisoned
    assert session_obj.reuse_status == "new"
    # The cache lookup query MUST NOT have been issued when force_refresh=True.
    assert db.execute.await_count == 0


async def test_create_advice_different_language_is_miss() -> None:
    """Two calls that differ only in advice_language produce different
    fingerprints — both must miss the cache (both 'new')."""
    payload_vi = json.dumps(_v2_llm_payload(language="vi"))
    payload_en = json.dumps(_v2_llm_payload(language="en"))

    llm_vi = _MockLLMProvider(payload_vi)
    llm_en = _MockLLMProvider(payload_en)
    wiki_page = _make_wiki_page()

    async def _call(llm: _MockLLMProvider, language: str):
        registry = _make_mock_registry(llm)
        db = _build_mock_db(existing_session=None)
        patches = _patch_service(registry, [(wiki_page, 0.9)])
        for p in patches:
            p.start()
        try:
            return await create_advice(
                db=db,
                user=None,
                customer_name="ACME",
                province_code=None,
                industry_code=None,
                needs="Cần vay vốn lưu động mở rộng kho",
                additional_context=None,
                customer_segment="sme",
                advice_language=language,
            )
        finally:
            for p in patches:
                p.stop()

    session_vi = await _call(llm_vi, "vi")
    session_en = await _call(llm_en, "en")

    assert session_vi.reuse_status == "new"
    assert session_en.reuse_status == "new"
    assert llm_vi.calls == 1
    assert llm_en.calls == 1
    # Most importantly: the fingerprints actually differ across languages, so
    # a future cache lookup with "en" would never collide with the "vi" row.
    assert session_vi.input_fingerprint != session_en.input_fingerprint
