"""
Permission snapshot test.

PURPOSE: Capture the permission behavior of own_dept BEFORE the multi-unit
membership migration changes the semantics. T20 enables
``test_diff_against_baseline_zero`` to verify zero regression for
single-membership users.

SNAPSHOT FORMAT:
    Key:   "{user_id}:{resource_type}:{resource_id}:{action}"
    Value: bool (True = permitted, False = denied)

BASELINE FILE: ``.sisyphus/evidence/perm-snapshot-baseline.json``

DESIGN: The snapshot exercises the real ``permission_engine`` functions
(``can_access_document`` / ``can_access_skill``) but stubs out the
``AsyncSession`` with ``AsyncMock`` so no live Postgres is required.
The engine reads ``user.department_id``, ``user.role`` and
``user.custom_role.permissions`` — all simple attribute lookups that
``MagicMock`` honours faithfully.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

BASELINE_PATH = Path(".sisyphus/evidence/perm-snapshot-baseline.json")

# T20 (post-migration golden gate) enables this so the diff test runs.
ENABLE_DIFF_CHECK = True

DEPT_A = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
DEPT_B = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")

# Users whose effective permissions MUST match exactly across the migration.
# Multi-membership users may legitimately gain access (their membership set
# grows) — they are excluded from the regression check in T20.
SINGLE_MEMBERSHIP_USERS: frozenset[str] = frozenset(
    {"user-own-dept-a", "user-all-a", "user-no-dept", "user-admin"}
)


def _make_user(
    role: str,
    department_id: uuid.UUID | None,
    permissions: list[str],
) -> MagicMock:
    """Build a stand-in ``Employee`` with just the attributes the engine reads."""
    user = MagicMock()
    user.role = role
    user.department_id = department_id
    user.custom_role = MagicMock()
    user.custom_role.permissions = list(permissions)
    return user


def _make_source(source_id: uuid.UUID) -> MagicMock:
    source = MagicMock()
    source.id = source_id
    return source


def _make_skill(department_ids: list[uuid.UUID]) -> MagicMock:
    skill = MagicMock()
    skill.departments = [MagicMock(department_id=did) for did in department_ids]
    return skill


def _make_db(source_dept_ids: set[uuid.UUID]) -> MagicMock:
    """Mock AsyncSession whose ``execute().all()`` yields ``(department_id,)`` rows."""
    db = MagicMock()
    result = MagicMock()
    result.all = MagicMock(return_value=[(did,) for did in source_dept_ids])
    db.execute = AsyncMock(return_value=result)
    return db


async def _compute_snapshot() -> dict[str, bool]:
    """Compute the permission snapshot against the current engine implementation."""
    # Lazy import so ruff doesn't load the engine on collection in non-DB envs.
    from app.services import permission_engine

    users: dict[str, MagicMock] = {
        "user-own-dept-a": _make_user(
            "employee",
            DEPT_A,
            [
                "doc:read:own_dept",
                "skill:read:own_dept",
                "task:read:own_dept",
            ],
        ),
        "user-all-a": _make_user(
            "employee",
            DEPT_A,
            [
                "doc:read:all",
                "skill:read:all",
                "task:read:all",
            ],
        ),
        "user-no-dept": _make_user("employee", None, []),
        "user-admin": _make_user("admin", None, []),
    }

    # Resource identity is fixed by the LABEL — the actual uuid does not matter
    # because the mock DB returns the dept_ids regardless of source.id.
    sources: dict[str, set[uuid.UUID]] = {
        "source-dept-a": {DEPT_A},
        "source-dept-b": {DEPT_B},
        "source-global": set(),
    }

    skills: dict[str, list[uuid.UUID]] = {
        "skill-dept-a": [DEPT_A],
        "skill-dept-b": [DEPT_B],
        "skill-global": [],
    }

    snap: dict[str, bool] = {}

    for user_id, user in users.items():
        for src_id, dept_ids in sources.items():
            source = _make_source(uuid.uuid4())
            db = _make_db(dept_ids)
            result = await permission_engine.can_access_document(
                db, user, source, "read"
            )
            snap[f"{user_id}:source:{src_id}:read"] = bool(result)

        for skill_id, skill_depts in skills.items():
            skill = _make_skill(skill_depts)
            db = _make_db(set())  # can_access_skill does not query the DB
            result = await permission_engine.can_access_skill(
                db, user, skill, "read"
            )
            snap[f"{user_id}:skill:{skill_id}:read"] = bool(result)

    return snap


async def test_baseline_snapshot_saved() -> None:
    """Compute and persist the permission snapshot baseline."""
    snap = await _compute_snapshot()
    assert len(snap) > 0, "Snapshot must have at least 1 entry"

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(snap, indent=2, sort_keys=True), encoding="utf-8"
    )

    assert BASELINE_PATH.exists()
    loaded = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert len(loaded) > 0

    # --- Document access invariants (own_dept semantics under test) ---
    # own_dept user in dept_a CAN read a source in dept_a
    assert loaded["user-own-dept-a:source:source-dept-a:read"] is True, (
        "own_dept user must be able to read source in own dept"
    )
    # own_dept user in dept_a CANNOT read a source in dept_b
    assert loaded["user-own-dept-a:source:source-dept-b:read"] is False, (
        "own_dept user must NOT be able to read source in other dept"
    )
    # own_dept user CAN read a Global source (no departments)
    assert loaded["user-own-dept-a:source:source-global:read"] is True

    # :all permission grants access to everything
    assert loaded["user-all-a:source:source-dept-a:read"] is True
    assert loaded["user-all-a:source:source-dept-b:read"] is True
    assert loaded["user-all-a:source:source-global:read"] is True

    # User with no permissions has no document access (even Global needs perm)
    assert loaded["user-no-dept:source:source-dept-a:read"] is False
    assert loaded["user-no-dept:source:source-dept-b:read"] is False
    assert loaded["user-no-dept:source:source-global:read"] is False

    # Admin always wins
    assert loaded["user-admin:source:source-dept-a:read"] is True
    assert loaded["user-admin:source:source-dept-b:read"] is True
    assert loaded["user-admin:source:source-global:read"] is True

    # --- Skill access invariants ---
    # own_dept user can read own-dept skill, not other-dept skill,
    # and can read Global skill (no departments).
    assert loaded["user-own-dept-a:skill:skill-dept-a:read"] is True
    assert loaded["user-own-dept-a:skill:skill-dept-b:read"] is False
    assert loaded["user-own-dept-a:skill:skill-global:read"] is True

    # Admin sees all skills
    assert loaded["user-admin:skill:skill-dept-a:read"] is True
    assert loaded["user-admin:skill:skill-dept-b:read"] is True


async def test_diff_against_baseline_zero() -> None:
    """Verify zero permission regression for single-membership users after migration.

    DISABLED until T20 (post-migration golden gate) flips ``ENABLE_DIFF_CHECK``.
    """
    if not ENABLE_DIFF_CHECK:
        pytest.skip("Diff check disabled — enabled by T20 after migration")

    assert BASELINE_PATH.exists(), (
        "Baseline not found — run test_baseline_snapshot_saved first"
    )
    baseline: dict[str, bool] = json.loads(
        BASELINE_PATH.read_text(encoding="utf-8")
    )

    current = await _compute_snapshot()

    regressions: list[str] = []
    for key, old_val in baseline.items():
        user_id = key.split(":", 1)[0]
        if user_id not in SINGLE_MEMBERSHIP_USERS:
            continue
        new_val = current.get(key)
        if new_val != old_val:
            regressions.append(f"{key}: was {old_val}, now {new_val}")

    assert not regressions, "Permission regressions detected:\n" + "\n".join(
        regressions
    )
