"""
CMD Advisory Fingerprint — canonical contract for deduplication + cache reuse.

This module defines the *contract* by which two advisory requests are
considered equivalent (and therefore reusable) versus materially different
(and therefore requiring a fresh LLM call).

The fingerprint is the primary key for advisory cache lookup. A separate
``source_snapshot_hash`` captures the state of the retrieval corpus at the
time the advisory was generated, allowing us to detect when the underlying
knowledge base has changed even if the user input has not.

Full implementation lives in W2-T6; this module currently exposes:

- ``FINGERPRINT_INPUT_FIELDS``     — canonical list of input fields
- ``FINGERPRINT_ENV_COMPONENTS``   — canonical list of environment components
- ``REFRESH_SEMANTICS``            — refresh-logic contract (docstring)
- ``compute_advisory_fingerprint`` — stub signature for W2-T6
- ``compute_source_snapshot_hash`` — stub signature for W2-T6

CONTRACT
========

A "material" change MUST produce a different fingerprint:

- ``customer_segment``       (lowercased; e.g. "sme" / "midcom" / "public_admin")
- ``province_code``          (string code; None is materially distinct from "")
- ``industry_code``          (string code; None is materially distinct from "")
- ``needs``                  (whitespace-stripped; case-preserving — content matters)
- ``additional_context``     (whitespace-stripped; case-preserving)
- ``advice_language``        ("vi" | "en")
- ``prompt_version``         (PROMPT_VERSION from app.ai.cmd_support_prompts)
- ``model_provider``         (provider enum value, e.g. "google")
- ``model_id``               (model identifier string, e.g. "gemini-2.0-flash")

A "volatile" change MUST NOT produce a different fingerprint:

- whitespace at the start/end of free-text fields (``needs`` / ``additional_context``)
- capitalization of ``customer_segment`` (it is always lowercased before hashing)
- capitalization of ``customer_name`` (the customer's *name* is NOT part of the
  fingerprint — it is presentational only; the same need from "ACME CORP" and
  "Acme Corp" reuses the same cached advisory)
- key order of any dict serialized into the fingerprint (sort_keys=True)

REFRESH SEMANTICS
=================

The ``reuse_status`` field on a stored advisory has three values:

- ``"new"``       — first time this fingerprint has been seen; LLM was called.
- ``"reused"``    — a prior session with the same fingerprint AND the same
                    ``source_snapshot_hash`` exists; the prior ``result_json``
                    is returned verbatim.
- ``"refreshed"`` — a prior session with the same fingerprint exists, but the
                    ``source_snapshot_hash`` has changed (new/updated wiki
                    pages were retrieved); the LLM is re-called and the new
                    result supersedes the prior one.

ALGORITHM
=========

1. Build a dict containing every field in ``FINGERPRINT_INPUT_FIELDS`` and
   every field in ``FINGERPRINT_ENV_COMPONENTS``, after normalization:
   - lower-case ``customer_segment``
   - strip whitespace from ``needs`` and ``additional_context``
   - leave ``None`` as JSON ``null`` (distinct from empty string)
2. Serialize with ``json.dumps(payload, sort_keys=True,
   ensure_ascii=False, separators=(",", ":"))``.
3. Hash with SHA-256, return ``hexdigest()``.

The ``source_snapshot_hash`` follows the same algorithm over the *sorted* list
of retrieved wiki page UUIDs (rendered as strings via ``str(uuid)``).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from datetime import datetime

# ---------------------------------------------------------------------------
# Canonical contract — these tuples ARE the contract. Adding a field here is a
# breaking change for cache lookup (every prior advisory's fingerprint becomes
# stale). Removing a field is also breaking. Reordering is fine because
# serialization uses sort_keys=True.
# ---------------------------------------------------------------------------

FINGERPRINT_INPUT_FIELDS: tuple[str, ...] = (
    "customer_segment",
    "province_code",
    "industry_code",
    "needs",
    "additional_context",
    "advice_language",
)
"""User-facing inputs that materially change the advisory output."""

FINGERPRINT_ENV_COMPONENTS: tuple[str, ...] = (
    "prompt_version",
    "model_provider",
    "model_id",
)
"""Backend/environment components that materially change the advisory output."""

REFRESH_SEMANTICS: str = """\
reuse_status values:
  - "new":       no prior session with this fingerprint exists.
  - "reused":    prior session exists AND source_snapshot_hash matches.
  - "refreshed": prior session exists BUT source_snapshot_hash differs;
                 the retrieval corpus has changed, so the LLM is re-called.
"""


# ---------------------------------------------------------------------------
# Implementation (W2-T6).
# ---------------------------------------------------------------------------

def compute_advisory_fingerprint(
    *,
    customer_segment: str | None,
    province_code: str | None,
    industry_code: str | None,
    needs: str,
    additional_context: str | None,
    advice_language: str,
    prompt_version: str,
    model_provider: str | None,
    model_id: str | None,
) -> str:
    """Compute the canonical advisory fingerprint (SHA-256 hex).

    The returned string is a deterministic SHA-256 hex digest over a stable
    JSON serialization of the normalized inputs declared in
    ``FINGERPRINT_INPUT_FIELDS`` + ``FINGERPRINT_ENV_COMPONENTS``.

    Two calls with identical material inputs (modulo volatile differences
    documented in this module's docstring) MUST return the same string.
    Two calls with any different material input MUST return different
    strings.

    Normalization rules (kept in lockstep with the contract test reference):
    - ``customer_segment`` is lowercased; ``None`` or "" collapse to ``None``.
    - ``needs`` and ``additional_context`` have surrounding whitespace stripped;
      for ``additional_context`` an empty result collapses to ``None``.
    - ``province_code``, ``industry_code``, ``model_provider``, ``model_id``
      are passed through; ``None`` stays JSON ``null`` (materially distinct
      from the empty string).
    """
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
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_source_snapshot_hash(
    retrieved_pages: Iterable[tuple[uuid.UUID, int, datetime | None]],
) -> str:
    """Compute the canonical source-snapshot hash (SHA-256 hex).

    The returned string is a deterministic SHA-256 hex digest over the
    *sorted* list of retrieved wiki page identity tuples
    ``(page_id, version, updated_at)``. Order of the input iterable is
    irrelevant — equal sets yield equal hashes.

    Including ``version`` (and ``updated_at`` as a tiebreaker for legacy rows
    where the version counter may not advance on every edit) ensures that an
    edit to a wiki page's content invalidates the cached advisory even when
    the set of retrieved page UUIDs is unchanged. Without this, the
    ``"reused"`` path would serve stale advice indefinitely after editors
    update product policies.

    Used together with ``compute_advisory_fingerprint`` to decide between
    ``"reused"`` and ``"refreshed"`` reuse statuses (see ``REFRESH_SEMANTICS``).
    """
    sorted_tuples = sorted(
        (str(pid), int(ver), updated.isoformat() if updated is not None else None)
        for (pid, ver, updated) in retrieved_pages
    )
    serialized = json.dumps(
        sorted_tuples,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
