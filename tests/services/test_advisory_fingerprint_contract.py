"""
Contract tests for the CMD advisory fingerprint.

These tests pin down the *contract* (which fields participate, which volatile
differences are tolerated) without depending on the final implementation —
they use an inline reference SHA-256 implementation that mirrors the algorithm
documented in ``app.services.cmd_advisory_fingerprint``.

When W2-T6 lands the real ``compute_advisory_fingerprint`` and these tests
should be re-pointed at it; until then they protect the contract.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from app.services.cmd_advisory_fingerprint import (
    FINGERPRINT_ENV_COMPONENTS,
    FINGERPRINT_INPUT_FIELDS,
)


def _reference_fingerprint(
    *,
    customer_segment: Optional[str],
    province_code: Optional[str],
    industry_code: Optional[str],
    needs: str,
    additional_context: Optional[str],
    advice_language: str,
    prompt_version: str,
    model_provider: Optional[str],
    model_id: Optional[str],
) -> str:
    """Reference SHA-256 implementation mirroring the documented algorithm.

    Lives inline (not imported from the production module) so the tests stay
    self-contained while the production stub is unimplemented.
    """
    payload: dict[str, object] = {
        "customer_segment": (customer_segment or "").lower() or None,
        "province_code": province_code,
        "industry_code": industry_code,
        "needs": (needs or "").strip(),
        "additional_context": (
            (additional_context or "").strip() or None
        ),
        "advice_language": advice_language,
        "prompt_version": prompt_version,
        "model_provider": model_provider,
        "model_id": model_id,
    }
    serialized = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


_BASE_KWARGS = dict(
    customer_segment="sme",
    province_code="01",
    industry_code="6201",
    needs="Cần vay vốn lưu động mở rộng kho",
    additional_context="Khách hàng có 3 năm doanh thu ổn định",
    advice_language="vi",
    prompt_version="v1.2",
    model_provider="google",
    model_id="gemini-2.0-flash",
)


# ---------------------------------------------------------------------------
# Material diff: different inputs → different fingerprints
# ---------------------------------------------------------------------------

def test_material_diff() -> None:
    """Any change to a FINGERPRINT_INPUT_FIELD produces a different fingerprint."""
    base = _reference_fingerprint(**_BASE_KWARGS)

    # Mutate `needs` — the most obviously material field.
    different_needs = _reference_fingerprint(
        **{**_BASE_KWARGS, "needs": "Cần bảo lãnh thanh toán hợp đồng xuất khẩu"}
    )
    assert base != different_needs, "different needs must yield different fingerprints"

    # Mutate `customer_segment`.
    different_segment = _reference_fingerprint(
        **{**_BASE_KWARGS, "customer_segment": "midcom"}
    )
    assert base != different_segment, "different segment must yield different fingerprints"

    # Mutate `province_code`.
    different_province = _reference_fingerprint(
        **{**_BASE_KWARGS, "province_code": "79"}
    )
    assert base != different_province, "different province must yield different fingerprints"

    # Mutate `industry_code`.
    different_industry = _reference_fingerprint(
        **{**_BASE_KWARGS, "industry_code": "4711"}
    )
    assert base != different_industry, "different industry must yield different fingerprints"

    # Mutate `advice_language`.
    different_lang = _reference_fingerprint(
        **{**_BASE_KWARGS, "advice_language": "en"}
    )
    assert base != different_lang, "different language must yield different fingerprints"

    # Mutate env component `prompt_version`.
    different_prompt = _reference_fingerprint(
        **{**_BASE_KWARGS, "prompt_version": "v1.3"}
    )
    assert base != different_prompt, "different prompt_version must yield different fingerprints"

    # Mutate env component `model_id`.
    different_model = _reference_fingerprint(
        **{**_BASE_KWARGS, "model_id": "gpt-4o"}
    )
    assert base != different_model, "different model_id must yield different fingerprints"


# ---------------------------------------------------------------------------
# Volatile equivalence: same material inputs → same fingerprint
# ---------------------------------------------------------------------------

def test_volatile_eq() -> None:
    """Volatile differences (whitespace, segment case, kwarg order) do NOT change the fingerprint."""
    base = _reference_fingerprint(**_BASE_KWARGS)

    # Extra surrounding whitespace on free-text fields.
    padded = _reference_fingerprint(
        **{
            **_BASE_KWARGS,
            "needs": "   " + _BASE_KWARGS["needs"] + "\n\t",
            "additional_context": "  " + _BASE_KWARGS["additional_context"] + "  ",
        }
    )
    assert base == padded, "whitespace on free-text fields must be volatile"

    # Mixed-case customer_segment.
    upper_segment = _reference_fingerprint(
        **{**_BASE_KWARGS, "customer_segment": "SME"}
    )
    assert base == upper_segment, "customer_segment case must be volatile"

    # Re-ordering kwargs at the call site cannot affect the hash because the
    # payload is serialized with sort_keys=True. We assert this by reconstructing
    # the kwargs in a different insertion order.
    reordered_kwargs = {
        "model_id": _BASE_KWARGS["model_id"],
        "advice_language": _BASE_KWARGS["advice_language"],
        "needs": _BASE_KWARGS["needs"],
        "model_provider": _BASE_KWARGS["model_provider"],
        "prompt_version": _BASE_KWARGS["prompt_version"],
        "additional_context": _BASE_KWARGS["additional_context"],
        "industry_code": _BASE_KWARGS["industry_code"],
        "province_code": _BASE_KWARGS["province_code"],
        "customer_segment": _BASE_KWARGS["customer_segment"],
    }
    reordered = _reference_fingerprint(**reordered_kwargs)
    assert base == reordered, "kwarg order must be volatile"


# ---------------------------------------------------------------------------
# Schema integrity — guards against accidental field drift in the contract.
# ---------------------------------------------------------------------------

def test_contract_fields_are_exhaustive() -> None:
    """Every kwarg the reference impl consumes must appear in the contract tuples."""
    contract = set(FINGERPRINT_INPUT_FIELDS) | set(FINGERPRINT_ENV_COMPONENTS)
    assert contract == set(_BASE_KWARGS.keys()), (
        "FINGERPRINT_INPUT_FIELDS + FINGERPRINT_ENV_COMPONENTS must match the "
        "fields hashed by the reference implementation."
    )
