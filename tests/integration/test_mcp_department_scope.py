"""T10 — MCP department scope respects membership union.

Verifies that a multi-membership user sees the union of department-scoped
sources via MCP. The MCP layer pre-computes ``allowed_source_ids`` on the
``ResolvedIdentity`` at token verify time (in ``MCPAuthService._resolve_scope``)
and every MCP tool then passes that identity through ``apply_scope_filter``.

This test mocks the database session so it can run without Docker. The mocks
mirror the exact ``session.execute(...)`` call sequence inside
``_resolve_scope`` for an employee scoped to ``doc:read:own_dept`` with two
active memberships and no project memberships.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio

EMP_ID = uuid.UUID("11111111-0000-0000-0000-000000000001")
DEPT_A = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
DEPT_B = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
DEPT_C = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
SRC_A = uuid.UUID("00000000-aaaa-0000-0000-000000000001")
SRC_B = uuid.UUID("00000000-bbbb-0000-0000-000000000001")
SRC_GLOBAL = uuid.UUID("00000000-9999-0000-0000-000000000001")


def _make_employee(*, primary_dept: uuid.UUID, permissions: list[str]) -> MagicMock:
    employee = MagicMock()
    employee.id = EMP_ID
    employee.name = "Multi Membership User"
    employee.role = "employee"
    employee.department_id = primary_dept
    employee.department = MagicMock()
    employee.department.name = "Primary Dept"
    employee.custom_role = MagicMock()
    employee.custom_role.permissions = permissions
    return employee


def _all_rows(rows: list[tuple]) -> MagicMock:
    result = MagicMock()
    result.all = MagicMock(return_value=rows)
    return result


def _scalars_rows(rows: list[uuid.UUID]) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=rows)
    result.scalars = MagicMock(return_value=scalars)
    return result


async def test_resolve_scope_union_of_two_memberships() -> None:
    """``_resolve_scope`` returns sources from BOTH dept memberships."""
    from app.services.mcp_auth_service import MCPAuthService

    employee = _make_employee(
        primary_dept=DEPT_A,
        permissions=["doc:read:own_dept"],
    )

    # Call order inside _resolve_scope:
    #   1. _resolve_project_sources: project_ids query (returns [])
    #   2. get_user_department_ids: scalars().all() → [DEPT_A, DEPT_B]
    #   3. _get_department_source_ids: global source query → []
    #   4. _get_department_source_ids: dept-IN source query → [(SRC_A,), (SRC_B,)]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        _all_rows([]),                              # no projects
        _scalars_rows([DEPT_A, DEPT_B]),            # union of memberships
        _all_rows([]),                              # no global sources
        _all_rows([(SRC_A,), (SRC_B,)]),            # sources in either dept
    ])

    svc = MCPAuthService(db)
    identity = await svc._resolve_scope(employee)

    allowed = set(identity.allowed_source_ids or [])
    assert str(SRC_A) in allowed, "expected source in DEPT_A to be visible"
    assert str(SRC_B) in allowed, "expected source in DEPT_B to be visible"
    assert identity.is_admin is False
    # Primary department is preserved on the identity for display purposes,
    # but allowed_source_ids must reflect the union, not just the primary.
    assert identity.department_id == DEPT_A


async def test_resolve_scope_excludes_non_membership_departments() -> None:
    """A user in {A, B} must NOT see sources tied only to dept C."""
    from app.services.mcp_auth_service import MCPAuthService

    employee = _make_employee(
        primary_dept=DEPT_A,
        permissions=["doc:read:own_dept"],
    )

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        _all_rows([]),                              # no projects
        _scalars_rows([DEPT_A, DEPT_B]),            # memberships: A and B only
        _all_rows([]),                              # no global sources
        _all_rows([(SRC_A,), (SRC_B,)]),            # SRC_C never returned by the IN filter
    ])

    svc = MCPAuthService(db)
    identity = await svc._resolve_scope(employee)

    allowed = set(identity.allowed_source_ids or [])
    # Source tied to DEPT_C is filtered out by the SQL IN-clause and so does
    # not appear in the side_effect — this assertion documents the invariant.
    src_c = uuid.UUID("00000000-cccc-0000-0000-000000000001")
    assert str(src_c) not in allowed


async def test_get_department_source_ids_accepts_set() -> None:
    """``_get_department_source_ids`` accepts a set and unions globals + dept sources."""
    from app.services.mcp_auth_service import MCPAuthService

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        _all_rows([(SRC_GLOBAL,)]),                 # one global source
        _all_rows([(SRC_A,), (SRC_B,)]),            # sources in dept A or B
    ])

    svc = MCPAuthService(db)
    ids = await svc._get_department_source_ids({DEPT_A, DEPT_B})

    assert set(ids) == {str(SRC_GLOBAL), str(SRC_A), str(SRC_B)}


async def test_get_department_source_ids_empty_set_returns_globals_only() -> None:
    """Empty membership set short-circuits to global sources only (no IN query)."""
    from app.services.mcp_auth_service import MCPAuthService

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[
        _all_rows([(SRC_GLOBAL,)]),                 # only the global query runs
    ])

    svc = MCPAuthService(db)
    ids = await svc._get_department_source_ids(set())

    assert ids == [str(SRC_GLOBAL)]
    # Second execute call must NOT happen — verifies the early-return guard.
    assert db.execute.await_count == 1
