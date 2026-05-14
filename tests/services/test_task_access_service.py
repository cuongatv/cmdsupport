"""Unit tests for membership-based assignee eligibility in task_access_service.

These tests intentionally use AsyncMock + SimpleNamespace stubs so they don't
require Postgres or the full ORM. They exercise the real
``is_eligible_assignee`` implementation against the membership-union path
introduced in T8 (multi-unit upgrade).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.task_access_service import is_eligible_assignee, validate_assignee

pytestmark = pytest.mark.asyncio


def _scalars_all_result(values):
    scalars = Mock()
    scalars.all.return_value = values
    result = Mock()
    result.scalars.return_value = scalars
    return result


def _scalar_one_or_none_result(value):
    result = Mock()
    result.scalar_one_or_none.return_value = value
    return result


def _session() -> AsyncMock:
    session = AsyncMock()
    session.add = Mock()
    return session


def _employee(
    *,
    employee_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    is_active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=employee_id or uuid.uuid4(),
        department_id=department_id,
        is_active=is_active,
    )


def _dept_project(
    *,
    department_id: uuid.UUID,
    allow_any_employee: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        department_id=department_id,
        workspace_id=None,
        allow_any_employee=allow_any_employee,
        is_archived=False,
    )


def _workspace_project(
    *,
    workspace_id: uuid.UUID,
    allow_any_employee: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        department_id=None,
        workspace_id=workspace_id,
        allow_any_employee=allow_any_employee,
        is_archived=False,
    )


async def test_assignee_must_be_unit_member_no_membership_no_legacy():
    """Employee with neither active membership nor legacy department_id is rejected."""
    session = _session()
    department_id = uuid.uuid4()
    project = _dept_project(department_id=department_id)
    employee = _employee(department_id=None)

    # get_user_department_ids returns no rows; no legacy department_id → empty set.
    session.execute.return_value = _scalars_all_result([])

    result = await is_eligible_assignee(session, employee, project)

    assert result is False


async def test_assignee_must_be_unit_member_different_legacy_dept():
    """Employee whose legacy department_id is a different department is rejected."""
    session = _session()
    department_id = uuid.uuid4()
    other_department_id = uuid.uuid4()
    project = _dept_project(department_id=department_id)
    employee = _employee(department_id=other_department_id)

    # No membership rows; fallback yields {other_department_id}, which excludes
    # the project's department.
    session.execute.return_value = _scalars_all_result([])

    result = await is_eligible_assignee(session, employee, project)

    assert result is False


async def test_active_member_can_be_assignee():
    """Employee with an active membership row in the project's dept is eligible."""
    session = _session()
    department_id = uuid.uuid4()
    project = _dept_project(department_id=department_id)
    employee = _employee(department_id=None)

    session.execute.return_value = _scalars_all_result([department_id])

    result = await is_eligible_assignee(session, employee, project)

    assert result is True


async def test_legacy_department_id_member_can_be_assignee():
    """Employee with legacy department_id matching the project is eligible (fallback)."""
    session = _session()
    department_id = uuid.uuid4()
    project = _dept_project(department_id=department_id)
    employee = _employee(department_id=department_id)

    # No explicit membership rows; permission_engine.get_user_department_ids
    # falls back to {department_id}.
    session.execute.return_value = _scalars_all_result([])

    result = await is_eligible_assignee(session, employee, project)

    assert result is True


async def test_multi_unit_member_can_be_assigned_to_either_unit():
    """An employee with active memberships in two units is eligible in both."""
    session = _session()
    dept_a = uuid.uuid4()
    dept_b = uuid.uuid4()
    employee = _employee(department_id=dept_a)
    project_b = _dept_project(department_id=dept_b)

    session.execute.return_value = _scalars_all_result([dept_a, dept_b])

    result = await is_eligible_assignee(session, employee, project_b)

    assert result is True


async def test_inactive_employee_is_not_eligible():
    """Inactive employees can never be newly assigned."""
    session = _session()
    project = _dept_project(department_id=uuid.uuid4())
    employee = _employee(is_active=False, department_id=project.department_id)

    result = await is_eligible_assignee(session, employee, project)

    assert result is False
    session.execute.assert_not_called()


async def test_allow_any_employee_bypasses_scope():
    """`allow_any_employee` makes any active employee eligible regardless of dept."""
    session = _session()
    project = _dept_project(department_id=uuid.uuid4(), allow_any_employee=True)
    employee = _employee(department_id=uuid.uuid4())

    result = await is_eligible_assignee(session, employee, project)

    assert result is True
    session.execute.assert_not_called()


async def test_workspace_project_open_to_active_employees_for_create():
    """Workspace projects keep the open create-time eligibility (legacy CRUD)."""
    session = _session()
    project = _workspace_project(workspace_id=uuid.uuid4())
    employee = _employee(department_id=uuid.uuid4())

    result = await is_eligible_assignee(session, employee, project)

    assert result is True
    session.execute.assert_not_called()


async def test_validate_assignee_raises_for_non_member_dept_project():
    """validate_assignee surfaces the membership gate as a ValueError."""
    session = _session()
    department_id = uuid.uuid4()
    project = _dept_project(department_id=department_id)
    employee = _employee(department_id=uuid.uuid4())

    session.execute.return_value = _scalars_all_result([])

    with pytest.raises(ValueError, match="out of scope"):
        await validate_assignee(session, project, employee)


async def test_validate_assignee_workspace_requires_membership():
    """Assignment endpoint must keep enforcing workspace membership."""
    session = _session()
    workspace_id = uuid.uuid4()
    project = _workspace_project(workspace_id=workspace_id)
    employee = _employee(department_id=uuid.uuid4())

    # _is_workspace_member uses scalar_one_or_none(); return None → not a member.
    session.execute.return_value = _scalar_one_or_none_result(None)

    with pytest.raises(ValueError, match="out of scope"):
        await validate_assignee(session, project, employee)


async def test_validate_assignee_workspace_member_passes():
    """Workspace member is accepted by validate_assignee."""
    session = _session()
    workspace_id = uuid.uuid4()
    project = _workspace_project(workspace_id=workspace_id)
    employee = _employee(department_id=uuid.uuid4())

    session.execute.return_value = _scalar_one_or_none_result(employee.id)

    await validate_assignee(session, project, employee)


async def test_validate_assignee_inactive_employee_raises():
    """Inactive employees fail with the explicit inactive message."""
    session = _session()
    project = _dept_project(department_id=uuid.uuid4())
    employee = _employee(is_active=False, department_id=project.department_id)

    with pytest.raises(ValueError, match="inactive employee"):
        await validate_assignee(session, project, employee)

    session.execute.assert_not_called()
