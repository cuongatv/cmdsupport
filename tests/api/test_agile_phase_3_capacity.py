"""API tests for the Phase 3 squad capacity endpoint.

Covers the three required scenarios:

* ``test_capacity_api_returns_data_when_enabled``  — flag ON, populated squad,
  rows shape matches ``SquadMemberCapacityOut``.
* ``test_capacity_api_returns_403_when_disabled``  — flag OFF, 403
  FEATURE_DISABLED short-circuits before the DB is touched.
* ``test_capacity_api_requires_auth``              — no bearer token →
  401 (handled by the global ``HTTPBearer`` dependency).

Strategy mirrors ``tests/api/test_agile_phase_1.py``: in-process ASGI client
with ``get_db`` and ``get_current_user`` overridden onto the rollback-isolated
``db_session`` fixture so the real router + service code paths exercise
PostgreSQL but no rows survive the test.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator, Optional

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import (
    Employee,
    EmployeeDepartmentMembership,
    MembershipRole,
    Task,
    TaskAssignee,
    TaskProject,
    TaskState,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures / helpers — kept self-contained so the API suite does not depend
# on the service-suite test module (which lives under tests/services/).
# ---------------------------------------------------------------------------


async def _insert_squad_department(db_session: AsyncSession) -> uuid.UUID:
    """Insert a ``squad_team`` department.

    The DB trigger from migration 026 requires ``unit_type='squad_team'``
    before squad-flavoured membership roles (``product_owner``,
    ``scrum_master``, ``developer``) are accepted. Phase 3 capacity rows
    model squad members specifically, so the fixture mirrors production.
    """
    department_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO departments (id, name, unit_type) "
            "VALUES (:id, :name, 'squad_team')"
        ),
        {
            "id": department_id,
            "name": f"P3 API Dept {department_id.hex[:6]}",
        },
    )
    return department_id


async def _insert_employee(
    db_session: AsyncSession,
    department_id: uuid.UUID,
    *,
    name: str = "Member",
    role: str = "employee",
) -> Employee:
    employee_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, role, department_id, is_active)
            VALUES (:id, :name, :email, :role, :dept, true)
            """
        ),
        {
            "id": employee_id,
            "name": f"{name}-{employee_id.hex[:6]}",
            "email": f"{employee_id.hex[:12]}@p3api.test",
            "role": role,
            "dept": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


async def _add_membership(
    db_session: AsyncSession,
    employee: Employee,
    department_id: uuid.UUID,
    *,
    capacity_percent: Optional[int] = 100,
    role: MembershipRole = MembershipRole.DEVELOPER,
) -> EmployeeDepartmentMembership:
    membership = EmployeeDepartmentMembership(
        employee_id=employee.id,
        department_id=department_id,
        role=role,
        capacity_percent=capacity_percent,
        is_active=True,
        is_primary=False,
    )
    db_session.add(membership)
    await db_session.flush()
    return membership


async def _seed_open_task(
    db_session: AsyncSession,
    department_id: uuid.UUID,
    assignee: Employee,
    creator: Employee,
    *,
    identifier: str,
    story_points: Optional[int] = None,
) -> Task:
    """Create a department-scoped TaskProject + Backlog state + one open task
    assigned to ``assignee``. Returns the task so callers can inspect it."""
    project = TaskProject(
        id=uuid.uuid4(),
        name=f"P3 API Project {identifier}",
        identifier=identifier,
        department_id=department_id,
        allow_any_employee=True,
        created_by_id=creator.id,
    )
    db_session.add(project)
    await db_session.flush()

    backlog = TaskState(
        id=uuid.uuid4(),
        task_project_id=project.id,
        name="Backlog",
        group="backlog",
        position=0.0,
        is_default=True,
    )
    db_session.add(backlog)
    await db_session.flush()

    task = Task(
        id=uuid.uuid4(),
        task_project_id=project.id,
        state_id=backlog.id,
        title="API capacity seed task",
        story_points=story_points,
        created_by_id=creator.id,
    )
    db_session.add(task)
    await db_session.flush()

    db_session.add(TaskAssignee(task_id=task.id, employee_id=assignee.id))
    await db_session.flush()
    return task


@pytest_asyncio.fixture
async def squad_with_member(
    db_session: AsyncSession,
) -> tuple[uuid.UUID, Employee, Employee]:
    """Insert one squad + an admin caller + one squad member with one task."""
    department_id = await _insert_squad_department(db_session)
    admin = await _insert_employee(
        db_session, department_id, name="p3-api-admin", role="admin"
    )
    member = await _insert_employee(db_session, department_id, name="p3-api-member")
    await _add_membership(db_session, member, department_id, capacity_percent=80)
    await _seed_open_task(
        db_session,
        department_id,
        assignee=member,
        creator=admin,
        identifier=f"PA{uuid.uuid4().hex[:4].upper()}",
        story_points=5,
    )
    return department_id, admin, member


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    squad_with_member: tuple[uuid.UUID, Employee, Employee],
) -> AsyncIterator[httpx.AsyncClient]:
    """In-process ASGI client bound to the rollback ``db_session`` + admin."""
    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    _department_id, admin, _member = squad_with_member

    async def _db_override():
        yield db_session

    async def _user_override():
        return admin

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = _user_override

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        try:
            yield client
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Required scenarios
# ---------------------------------------------------------------------------


async def test_capacity_api_returns_data_when_enabled(
    api_client: httpx.AsyncClient,
    squad_with_member: tuple[uuid.UUID, Employee, Employee],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag ON: endpoint returns one row per active membership, shape matches
    ``SquadMemberCapacityOut``, member's seeded task surfaces in ``open_task_count``."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_3", True)
    department_id, _admin, member = squad_with_member

    resp = await api_client.get(f"/api/departments/{department_id}/agile/capacity")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert isinstance(payload, list)
    assert len(payload) == 1

    row = payload[0]
    assert row["employee_id"] == str(member.id)
    assert row["department_id"] == str(department_id)
    assert row["capacity_percent"] == 80
    assert row["open_task_count"] == 1
    assert row["story_points_sum"] == 5
    assert row["is_overloaded"] is False
    # Shape contract: every documented field present + Vietnamese-safe name.
    assert "squad_name" in row
    assert "employee_name" in row


async def test_capacity_api_returns_403_when_disabled(
    api_client: httpx.AsyncClient,
    squad_with_member: tuple[uuid.UUID, Employee, Employee],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag OFF: 403 with ``{"code": "FEATURE_DISABLED"}`` mirrors Phase 1/2."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_3", False)
    department_id, _admin, _member = squad_with_member

    resp = await api_client.get(f"/api/departments/{department_id}/agile/capacity")

    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "FEATURE_DISABLED"


async def test_capacity_api_requires_auth(
    test_client: httpx.AsyncClient,
    override_db_noop: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Authorization header → 401. The auth check runs BEFORE the feature
    gate so an unauthenticated caller cannot probe the flag state.

    ``override_db_noop`` swaps in a no-op ``get_db`` so the test passes even
    when Postgres is unreachable — the auth dependency short-circuits first.
    """
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_3", True)
    department_id = uuid.uuid4()

    resp = await test_client.get(f"/api/departments/{department_id}/agile/capacity")

    assert resp.status_code == 401, resp.text
