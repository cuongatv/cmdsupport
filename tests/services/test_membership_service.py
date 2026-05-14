from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.database.models import MembershipRole, UnitType
from app.services.membership_service import (
    DepartmentArchiveBlockedError,
    DepartmentDeleteBlockedError,
    LastActiveMembershipError,
    MembershipRoleNotAllowedError,
    PrimaryMembershipRequiredError,
    _validate_role_for_unit_type,
    archive_department,
    create_membership,
    delete_department,
    delete_membership,
    get_user_department_ids,
    set_primary,
    update_membership,
)

pytestmark = pytest.mark.asyncio


def _scalar_result(value):
    result = Mock()
    result.scalar.return_value = value
    return result


def _scalar_one_or_none_result(value):
    result = Mock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_all_result(values):
    scalars = Mock()
    scalars.all.return_value = values
    result = Mock()
    result.scalars.return_value = scalars
    return result


def _session() -> AsyncMock:
    session = AsyncMock()
    session.add = Mock()
    return session


async def test_validate_role_for_unit_type_squad_only_in_squad_team_ok():
    _validate_role_for_unit_type(
        MembershipRole.PRODUCT_OWNER,
        UnitType.SQUAD_TEAM,
    )


async def test_validate_role_for_unit_type_squad_only_in_business_group_raises():
    with pytest.raises(MembershipRoleNotAllowedError, match="product_owner"):
        _validate_role_for_unit_type(
            MembershipRole.PRODUCT_OWNER,
            UnitType.BUSINESS_GROUP,
        )


async def test_validate_role_for_unit_type_common_role_in_business_group_ok():
    _validate_role_for_unit_type(MembershipRole.LEAD, UnitType.BUSINESS_GROUP)


async def test_get_user_department_ids_returns_active_depts():
    session = _session()
    department_ids = [uuid.uuid4(), uuid.uuid4()]
    session.execute.return_value = _scalars_all_result(department_ids)

    result = await get_user_department_ids(session, uuid.uuid4())

    assert result == set(department_ids)
    session.execute.assert_awaited_once()


async def test_create_membership_invalid_role_raises():
    session = _session()
    session.get.return_value = SimpleNamespace(unit_type=UnitType.BUSINESS_GROUP)

    with pytest.raises(MembershipRoleNotAllowedError, match="product_owner"):
        await create_membership(
            session,
            employee_id=uuid.uuid4(),
            department_id=uuid.uuid4(),
            role=MembershipRole.PRODUCT_OWNER,
        )

    session.execute.assert_not_called()
    session.add.assert_not_called()


async def test_create_membership_duplicate_raises():
    session = _session()
    session.get.return_value = SimpleNamespace(unit_type=UnitType.SQUAD_TEAM)
    session.execute.return_value = _scalar_one_or_none_result(SimpleNamespace())
    department_id = uuid.uuid4()

    with pytest.raises(ValueError, match=f"{department_id}"):
        await create_membership(
            session,
            employee_id=uuid.uuid4(),
            department_id=department_id,
            role=MembershipRole.DEVELOPER,
        )

    session.add.assert_not_called()


async def test_set_primary_inactive_raises():
    session = _session()
    membership = SimpleNamespace(
        id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        department_id=uuid.uuid4(),
        is_active=False,
    )
    session.get.return_value = membership

    with pytest.raises(ValueError, match="inactive membership"):
        await set_primary(session, membership.id)

    session.execute.assert_not_called()
    session.flush.assert_not_called()


async def test_update_membership_role_revalidates():
    session = _session()
    membership = SimpleNamespace(
        id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        department_id=uuid.uuid4(),
        role=MembershipRole.MEMBER,
        is_primary=False,
    )
    session.get.side_effect = [
        membership,
        SimpleNamespace(unit_type=UnitType.BUSINESS_GROUP),
    ]

    with pytest.raises(MembershipRoleNotAllowedError, match="product_owner"):
        await update_membership(
            session,
            membership.id,
            role=MembershipRole.PRODUCT_OWNER,
        )

    assert membership.role == MembershipRole.MEMBER
    session.flush.assert_not_called()


async def test_update_membership_deactivate_last_primary_raises():
    session = _session()
    membership = SimpleNamespace(
        id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        department_id=uuid.uuid4(),
        is_active=True,
        is_primary=True,
    )
    session.get.return_value = membership
    session.execute.return_value = _scalar_result(0)

    with pytest.raises(LastActiveMembershipError, match="only active primary"):
        await update_membership(session, membership.id, is_active=False)

    assert membership.is_active is True
    assert membership.is_primary is True
    session.flush.assert_not_called()


async def test_archive_department_with_open_projects_raises():
    session = _session()
    department_id = uuid.uuid4()
    session.execute.return_value = _scalar_result(1)

    with pytest.raises(DepartmentArchiveBlockedError) as exc_info:
        await archive_department(session, department_id)

    assert exc_info.value.open_project_count == 1
    session.get.assert_not_called()
    session.flush.assert_not_called()


async def test_delete_department_not_archived_raises():
    session = _session()
    department_id = uuid.uuid4()
    session.get.return_value = SimpleNamespace(id=department_id, is_archived=False)
    session.execute.side_effect = [_scalar_result(0), _scalar_result(0)]

    with pytest.raises(DepartmentDeleteBlockedError) as exc_info:
        await delete_department(session, department_id)

    assert "department must be archived first" in exc_info.value.reasons
    session.delete.assert_not_called()
    session.flush.assert_not_called()


async def test_delete_membership_only_primary_raises():
    session = _session()
    membership = SimpleNamespace(
        id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        is_primary=True,
    )
    session.get.return_value = membership
    session.execute.return_value = _scalar_result(0)

    with pytest.raises(PrimaryMembershipRequiredError, match="only membership"):
        await delete_membership(session, membership.id)

    session.delete.assert_not_called()
    session.flush.assert_not_called()
