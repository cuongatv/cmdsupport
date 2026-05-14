"""
Implementation tests for the CMD advisory fingerprint (W2-T6).

The sibling ``test_advisory_fingerprint_contract.py`` pins the *contract* via an
inline reference SHA-256 implementation. This module tests the *real* functions
in ``app.services.cmd_advisory_fingerprint`` and bridges the two by asserting
the real impl produces the same digest as the reference on the documented base
case (so the contract tests stay authoritative).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Optional

from app.services.cmd_advisory_fingerprint import (
    compute_advisory_fingerprint,
    compute_source_snapshot_hash,
)

# ---------------------------------------------------------------------------
# Helpers: explicit-kwarg wrappers so basedpyright sees every arg's exact type
# (dict-spread + None overrides would widen str-typed fields to str | None and
# fail strict argument checking).
# ---------------------------------------------------------------------------

_BASE_CUSTOMER_SEGMENT: Optional[str] = "sme"
_BASE_PROVINCE_CODE: Optional[str] = "01"
_BASE_INDUSTRY_CODE: Optional[str] = "6201"
_BASE_NEEDS: str = "Cần vay vốn lưu động mở rộng kho"
_BASE_ADDITIONAL_CONTEXT: Optional[str] = "Khách hàng có 3 năm doanh thu ổn định"
_BASE_ADVICE_LANGUAGE: str = "vi"
_BASE_PROMPT_VERSION: str = "v1.2"
_BASE_MODEL_PROVIDER: Optional[str] = "google"
_BASE_MODEL_ID: Optional[str] = "gemini-2.0-flash"


def _fp(
    *,
    customer_segment: Optional[str] = _BASE_CUSTOMER_SEGMENT,
    province_code: Optional[str] = _BASE_PROVINCE_CODE,
    industry_code: Optional[str] = _BASE_INDUSTRY_CODE,
    needs: str = _BASE_NEEDS,
    additional_context: Optional[str] = _BASE_ADDITIONAL_CONTEXT,
    advice_language: str = _BASE_ADVICE_LANGUAGE,
    prompt_version: str = _BASE_PROMPT_VERSION,
    model_provider: Optional[str] = _BASE_MODEL_PROVIDER,
    model_id: Optional[str] = _BASE_MODEL_ID,
) -> str:
    """Call the real fingerprint with base values + per-test overrides."""
    return compute_advisory_fingerprint(
        customer_segment=customer_segment,
        province_code=province_code,
        industry_code=industry_code,
        needs=needs,
        additional_context=additional_context,
        advice_language=advice_language,
        prompt_version=prompt_version,
        model_provider=model_provider,
        model_id=model_id,
    )


def _reference_fingerprint(
    *,
    customer_segment: Optional[str] = _BASE_CUSTOMER_SEGMENT,
    province_code: Optional[str] = _BASE_PROVINCE_CODE,
    industry_code: Optional[str] = _BASE_INDUSTRY_CODE,
    needs: str = _BASE_NEEDS,
    additional_context: Optional[str] = _BASE_ADDITIONAL_CONTEXT,
    advice_language: str = _BASE_ADVICE_LANGUAGE,
    prompt_version: str = _BASE_PROMPT_VERSION,
    model_provider: Optional[str] = _BASE_MODEL_PROVIDER,
    model_id: Optional[str] = _BASE_MODEL_ID,
) -> str:
    """Mirror of the algorithm in the contract test — used as a cross-check."""
    payload: dict[str, object] = {
        "customer_segment": (customer_segment or "").lower() or None,
        "province_code": province_code,
        "industry_code": industry_code,
        "needs": (needs or "").strip(),
        "additional_context": (additional_context or "").strip() or None,
        "advice_language": advice_language,
        "prompt_version": prompt_version,
        "model_provider": model_provider,
        "model_id": model_id,
    }
    serialized = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Bridge to the contract: real impl must match the reference on the base case.
# ---------------------------------------------------------------------------

def test_real_impl_matches_reference_on_base_case() -> None:
    assert _fp() == _reference_fingerprint()


def test_real_impl_matches_reference_with_none_optionals() -> None:
    assert _fp(
        additional_context=None, model_provider=None, model_id=None
    ) == _reference_fingerprint(
        additional_context=None, model_provider=None, model_id=None
    )


# ---------------------------------------------------------------------------
# compute_advisory_fingerprint — stability & format
# ---------------------------------------------------------------------------

def test_fingerprint_is_stable_for_same_input() -> None:
    """Same kwargs → same digest, called repeatedly."""
    first = _fp()
    second = _fp()
    third = _fp()
    assert first == second == third


def test_fingerprint_is_sha256_hex() -> None:
    """Returned value is a 64-char lowercase hex string."""
    fp = _fp()
    assert isinstance(fp, str)
    assert len(fp) == 64
    _ = int(fp, 16)  # raises ValueError if not hex


def test_fingerprint_distinguishes_none_from_empty_string() -> None:
    """``None`` and ``""`` are materially different for code-shaped fields.

    Empty string is a valid (if unusual) value; None means "absent". The hash
    must treat them differently so an advisory submitted with province_code=""
    is NOT considered the same input as one submitted with province_code=None.
    """
    assert _fp(province_code=None) != _fp(province_code=""), (
        "province_code None must differ from ''"
    )
    assert _fp(industry_code=None) != _fp(industry_code=""), (
        "industry_code None must differ from ''"
    )


def test_fingerprint_collapses_blank_additional_context_to_none() -> None:
    """``additional_context`` strips to empty → collapses to None per the contract.

    Documented in the module docstring as a normalization rule, and asserted
    here against the real implementation directly.
    """
    none_fp = _fp(additional_context=None)
    blank_fp = _fp(additional_context="   ")
    empty_fp = _fp(additional_context="")
    assert none_fp == blank_fp == empty_fp


def test_fingerprint_collapses_blank_segment_to_none() -> None:
    """``customer_segment`` lower-cases then collapses to None when blank."""
    none_fp = _fp(customer_segment=None)
    empty_fp = _fp(customer_segment="")
    assert none_fp == empty_fp


# ---------------------------------------------------------------------------
# compute_source_snapshot_hash — order, dedup-shape, format
# ---------------------------------------------------------------------------

_UUID_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
_UUID_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
_UUID_C = uuid.UUID("33333333-3333-3333-3333-333333333333")


def _t(uid: uuid.UUID, version: int = 1):
    """Helper: build a (page_id, version, updated_at) tuple for snapshot tests."""
    return (uid, version, None)


def test_source_snapshot_is_order_insensitive() -> None:
    """Same set in different orders → same digest."""
    a = compute_source_snapshot_hash([_t(_UUID_A), _t(_UUID_B), _t(_UUID_C)])
    b = compute_source_snapshot_hash([_t(_UUID_C), _t(_UUID_A), _t(_UUID_B)])
    c = compute_source_snapshot_hash([_t(_UUID_B), _t(_UUID_C), _t(_UUID_A)])
    assert a == b == c


def test_source_snapshot_accepts_any_iterable() -> None:
    """Tuples, lists, generators — all yield the same digest for equal sets."""
    from_list = compute_source_snapshot_hash([_t(_UUID_A), _t(_UUID_B)])
    from_tuple = compute_source_snapshot_hash((_t(_UUID_A), _t(_UUID_B)))
    from_gen = compute_source_snapshot_hash(_t(uid) for uid in [_UUID_A, _UUID_B])
    assert from_list == from_tuple == from_gen


def test_source_snapshot_empty_is_stable() -> None:
    """An empty iterable hashes to a stable, well-defined value (not an error)."""
    first = compute_source_snapshot_hash([])
    second = compute_source_snapshot_hash(())
    assert first == second
    assert len(first) == 64


def test_source_snapshot_distinguishes_different_sets() -> None:
    """Different page sets → different digests."""
    one = compute_source_snapshot_hash([_t(_UUID_A), _t(_UUID_B)])
    two = compute_source_snapshot_hash([_t(_UUID_A), _t(_UUID_C)])
    three = compute_source_snapshot_hash([_t(_UUID_A), _t(_UUID_B), _t(_UUID_C)])
    assert one != two
    assert one != three
    assert two != three


def test_source_snapshot_is_sha256_hex() -> None:
    """Returned value is a 64-char lowercase hex string."""
    digest = compute_source_snapshot_hash([_t(_UUID_A)])
    assert isinstance(digest, str)
    assert len(digest) == 64
    _ = int(digest, 16)


def test_source_snapshot_invalidates_when_version_changes() -> None:
    """Same UUID with different version → different digest (Fix #2: content-blind hash)."""
    v1 = compute_source_snapshot_hash([_t(_UUID_A, version=1)])
    v2 = compute_source_snapshot_hash([_t(_UUID_A, version=2)])
    assert v1 != v2


def test_source_snapshot_invalidates_when_updated_at_changes() -> None:
    """Same UUID + version with different updated_at → different digest."""
    from datetime import datetime, timezone
    t0 = (
        _UUID_A,
        1,
        datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    t1 = (
        _UUID_A,
        1,
        datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    assert compute_source_snapshot_hash([t0]) != compute_source_snapshot_hash([t1])
