from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio

DEPT_A = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
DEPT_B = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
DEPT_C = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
USER_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000001")


def _make_user(
    *,
    department_id: uuid.UUID | None = None,
    permissions: list[str] | None = None,
) -> MagicMock:
    user = MagicMock()
    user.id = USER_ID
    user.role = "employee"
    user.department_id = department_id
    user.custom_role = MagicMock()
    user.custom_role.permissions = permissions or [
        "doc:read:own_dept",
        "skill:read:own_dept",
    ]
    return user


def _make_db(
    *,
    source_department_ids: set[uuid.UUID] | None = None,
    membership_department_ids: list[uuid.UUID] | None = None,
) -> MagicMock:
    db = MagicMock()

    source_result = MagicMock()
    source_result.all = MagicMock(
        return_value=[(dept_id,) for dept_id in (source_department_ids or set())]
    )

    membership_result = MagicMock()
    membership_result.scalars.return_value.all.return_value = membership_department_ids or []

    if source_department_ids is None:
        db.execute = AsyncMock(return_value=membership_result)
    else:
        db.execute = AsyncMock(side_effect=[source_result, membership_result])
    return db


def _make_source() -> MagicMock:
    source = MagicMock()
    source.id = uuid.uuid4()
    return source


def _make_skill(department_ids: list[uuid.UUID]) -> MagicMock:
    skill = MagicMock()
    skill.departments = [MagicMock(department_id=dept_id) for dept_id in department_ids]
    return skill


async def test_no_membership_denies_own_dept() -> None:
    """User with no memberships and no department_id cannot access own_dept resource."""
    from app.services import permission_engine

    user = _make_user(department_id=None)
    source = _make_source()
    db = _make_db(source_department_ids={DEPT_A}, membership_department_ids=[])

    assert await permission_engine.can_access_document(db, user, source, "read") is False

    skill = _make_skill([DEPT_A])
    skill_db = _make_db(membership_department_ids=[])
    assert await permission_engine.can_access_skill(skill_db, user, skill, "read") is False


async def test_union_two_memberships() -> None:
    """User with memberships in A and B can access resources tagged A or B."""
    from app.services import permission_engine

    user = _make_user(department_id=DEPT_C)

    source_a = _make_source()
    db_a = _make_db(
        source_department_ids={DEPT_A},
        membership_department_ids=[DEPT_A, DEPT_B],
    )
    assert await permission_engine.can_access_document(db_a, user, source_a, "read") is True

    source_b = _make_source()
    db_b = _make_db(
        source_department_ids={DEPT_B},
        membership_department_ids=[DEPT_A, DEPT_B],
    )
    assert await permission_engine.can_access_document(db_b, user, source_b, "read") is True

    skill_a = _make_skill([DEPT_A])
    skill_db_a = _make_db(membership_department_ids=[DEPT_A, DEPT_B])
    assert await permission_engine.can_access_skill(skill_db_a, user, skill_a, "read") is True

    skill_b = _make_skill([DEPT_B])
    skill_db_b = _make_db(membership_department_ids=[DEPT_A, DEPT_B])
    assert await permission_engine.can_access_skill(skill_db_b, user, skill_b, "read") is True


async def test_inactive_excluded() -> None:
    """User with inactive membership in B cannot access B-tagged resources."""
    from app.services import permission_engine

    user = _make_user(department_id=None)
    source = _make_source()
    db = _make_db(source_department_ids={DEPT_B}, membership_department_ids=[DEPT_A])

    assert await permission_engine.can_access_document(db, user, source, "read") is False

    skill = _make_skill([DEPT_B])
    skill_db = _make_db(membership_department_ids=[DEPT_A])
    assert await permission_engine.can_access_skill(skill_db, user, skill, "read") is False


async def test_one_membership_allows_own_dept() -> None:
    """User with one active membership can access matching own_dept resources."""
    from app.services import permission_engine

    user = _make_user(department_id=None)
    source = _make_source()
    db = _make_db(source_department_ids={DEPT_A}, membership_department_ids=[DEPT_A])

    assert await permission_engine.can_access_document(db, user, source, "read") is True

    skill = _make_skill([DEPT_A])
    skill_db = _make_db(membership_department_ids=[DEPT_A])
    assert await permission_engine.can_access_skill(skill_db, user, skill, "read") is True
