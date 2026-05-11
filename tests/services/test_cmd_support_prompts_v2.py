"""
Contract tests for the v2.0 CMD Support advisory prompt.

W1-T2 of the cmd-support-advisory-v2 plan: pin that PROMPT_VERSION is
bumped to "v2.0" and that every new v2 schema section name appears in
the system prompt string so the LLM is instructed to emit them.
"""

from __future__ import annotations

from app.ai import cmd_support_prompts
from app.ai.cmd_support_prompts import PROMPT_VERSION, SYSTEM_PROMPT_VI

# New JSON sections introduced by v2.0. Kept as a module-level tuple so the
# names are easy to audit alongside the plan notepad.
V2_NEW_SECTIONS: tuple[str, ...] = (
    "executive_thesis",
    "primary_products",
    "cross_sell_products",
    "upsell_products",
    "operations_products",
    "digital_channels",
    "policies_incentives",
    "bundle_advantages",
    "schema_version",
)

# Existing v1 fields that must survive the v2 bump (additive schema).
V1_RETAINED_SECTIONS: tuple[str, ...] = (
    "advice_language",
    "customer_context",
    "analysis",
    "recommendations",
    "red_flags",
    "offer_materials",
    "follow_up_questions",
    "coverage_gaps",
    "rm_disclaimer",
)


def test_prompt_version_is_v2() -> None:
    """PROMPT_VERSION must be bumped to v2.0 so fingerprints partition v1 vs v2."""
    assert PROMPT_VERSION == "v2.0"
    # Cross-check via attribute lookup as well, in case of accidental re-export.
    assert cmd_support_prompts.PROMPT_VERSION == "v2.0"


def test_v2_schema_sections_present() -> None:
    """All v2 schema section names must appear in SYSTEM_PROMPT_VI."""
    missing = [name for name in V2_NEW_SECTIONS if name not in SYSTEM_PROMPT_VI]
    assert not missing, f"Missing v2 schema sections in SYSTEM_PROMPT_VI: {missing}"


def test_v1_sections_still_present() -> None:
    """v2 is additive — every v1 field must still be present."""
    missing = [name for name in V1_RETAINED_SECTIONS if name not in SYSTEM_PROMPT_VI]
    assert not missing, f"v1 schema sections dropped from SYSTEM_PROMPT_VI: {missing}"


def test_schema_version_literal_in_prompt() -> None:
    """The literal value "v2.0" must appear so the LLM emits the right marker."""
    assert "v2.0" in SYSTEM_PROMPT_VI


def test_build_user_prompt_signature_unchanged() -> None:
    """W1-T2 must not change build_user_prompt's signature."""
    import inspect

    sig = inspect.signature(cmd_support_prompts.build_user_prompt)
    params = list(sig.parameters)
    assert params == [
        "customer_name",
        "province_name",
        "industry_name",
        "needs",
        "additional_context",
        "context_blocks",
        "segment_label",
        "advice_language",
    ]
