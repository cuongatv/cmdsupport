"""API-facing assignment contract tests for the multi-unit membership upgrade.

These tests exercise the service-level contracts that the
``/api/tasks/{id}/assignees`` endpoint and the task-create flow rely on, using
AsyncMock so they run without Postgres. The router translates the raised
ValueError ("out of scope") into HTTP 400 via ``_call_service`` — that
translation is asserted by the existing test_tasks_api integration suite when
Docker is available; here we verify the precise error message + type contract
the router depends on.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.task_access_service import validate_assignee
from app.services.task_project_service import (
    TaskProjectAccessDenied,
    _authorize_default_dept_project_create,
)

pytestmark = pytest.mark.asyncio


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


def _actor(
    *,
    employee_id: uuid.UUID | None = None,
    role: str = "employee",
    department_id: uuid.UUID | None = None,
    custom_role_id: uuid.UUID | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=employee_id or uuid.uuid4(),
        role=role,
        department_id=department_id,
        custom_role_id=custom_role_id,
        is_active=True,
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


async def test_non_member_assignee_surfaces_eligible_value_error():
    """Endpoint contract: validate_assignee must raise ValueError("out of scope").

    ``_call_service`` in app/routers/tasks.py converts this exact ValueError
    into HTTP 400. Asserting the message string keeps the API surface stable.
    """
    session = _session()
    department_id = uuid.uuid4()
    project = _dept_project(department_id=department_id)
    employee = SimpleNamespace(
        id=uuid.uuid4(),
        is_active=True,
        department_id=uuid.uuid4(),  # different dept, no membership row
    )

    # get_user_department_ids → no memberships, no legacy match
    session.execute.return_value = _scalars_all_result([])

    with pytest.raises(ValueError) as excinfo:
        await validate_assignee(session, project, employee)

    assert "out of scope" in str(excinfo.value)


async def test_active_member_assignee_passes_validate():
    """Active member of the project's dept (via membership row) is accepted."""
    session = _session()
    department_id = uuid.uuid4()
    project = _dept_project(department_id=department_id)
    employee = SimpleNamespace(
        id=uuid.uuid4(),
        is_active=True,
        department_id=None,
    )

    session.execute.return_value = _scalars_all_result([department_id])

    await validate_assignee(session, project, employee)


async def test_resolve_default_authorizes_before_create():
    """Non-member cannot pass the authorization gate for lazy-creation.

    Directly invoke the gate so this test is independent of ORM relationship
    machinery in the rest of resolve_default_task_project. The router-level
    contract is: the gate raises TaskProjectAccessDenied BEFORE the caller
    reaches any db.add(TaskProject(...)) — guaranteed by the call order in
    resolve_default_task_project.
    """
    session = _session()
    department_id = uuid.uuid4()
    actor = _actor(department_id=uuid.uuid4())  # legacy points elsewhere

    # _resolve_actor_permissions has actor.custom_role_id=None so it uses
    # EMPLOYEE_DEFAULT_PERMISSIONS (which does NOT include task:create:all
    # nor task_project:manage:all). Only the membership lookup runs against
    # session.execute.
    session.execute.return_value = _scalars_all_result([])

    with pytest.raises(TaskProjectAccessDenied) as excinfo:
        await _authorize_default_dept_project_create(session, actor, department_id)

    assert str(department_id) in str(excinfo.value)
    # CRITICAL: no project rows were added before the gate raised.
    session.add.assert_not_called()


async def test_resolve_default_allows_dept_member():
    """Active dept member passes the lazy-create authorization gate."""
    session = _session()
    department_id = uuid.uuid4()
    actor = _actor()

    session.execute.return_value = _scalars_all_result([department_id])

    # No exception — the gate accepts the member.
    await _authorize_default_dept_project_create(session, actor, department_id)


async def test_resolve_default_admin_bypasses_membership_gate():
    """Admins skip the membership check entirely; no DB roundtrip needed."""
    session = _session()
    department_id = uuid.uuid4()
    actor = _actor(role="admin", department_id=None)

    await _authorize_default_dept_project_create(session, actor, department_id)

    # Admin short-circuit: no membership query was issued.
    session.execute.assert_not_called()


async def test_resolve_default_broad_create_permission_bypasses_gate():
    """Holders of task:create:all bypass the membership gate."""
    session = _session()
    department_id = uuid.uuid4()
    actor = _actor(custom_role_id=uuid.uuid4())

    # Role lookup returns a role with the broad-scope permission.
    role = SimpleNamespace(permissions=["task:create:all"])
    session.get = AsyncMock(return_value=role)

    await _authorize_default_dept_project_create(session, actor, department_id)

    # Gate accepted via permission; membership lookup never ran.
    session.execute.assert_not_called()
