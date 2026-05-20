# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""
API tests for ``/api/telegram/bindings``.

Verifies the bind-code flow over the REST surface:
* Squad LEAD can POST to create a bind code (response includes ``CMD-...``).
* Regular member POST is rejected 403.
* GET lists active+pending bindings for the lead.
* DELETE deactivates the binding for the lead.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    MembershipRole,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def department(db_session: AsyncSession) -> Department:
    dept = Department(name=f"Tg Bind Dept {uuid.uuid4().hex[:8]}")
    db_session.add(dept)
    await db_session.flush()
    await db_session.refresh(dept)
    return dept


async def _make_employee(
    db_session: AsyncSession,
    *,
    department_id: uuid.UUID,
    role: str = "employee",
    name: str = "Tg Person",
) -> Employee:
    emp_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, username, role, department_id, is_active)
            VALUES (:id, :name, :email, :username, :role, :dept_id, true)
            """
        ),
        {
            "id": emp_id,
            "name": name,
            "email": f"{emp_id.hex[:12]}@example.test",
            "username": f"tg_{emp_id.hex[:12]}",
            "role": role,
            "dept_id": department_id,
        },
    )
    employee = await db_session.get(Employee, emp_id)
    assert employee is not None
    return employee


async def _make_membership(
    db_session: AsyncSession,
    *,
    employee_id: uuid.UUID,
    department_id: uuid.UUID,
    role: MembershipRole,
    is_primary: bool = True,
) -> EmployeeDepartmentMembership:
    membership = EmployeeDepartmentMembership(
        employee_id=employee_id,
        department_id=department_id,
        role=role,
        is_active=True,
        is_primary=is_primary,
    )
    db_session.add(membership)
    await db_session.flush()
    return membership


@pytest_asyncio.fixture
async def lead_employee(
    db_session: AsyncSession, department: Department
) -> Employee:
    employee = await _make_employee(
        db_session, department_id=department.id, name="Squad Lead"
    )
    await _make_membership(
        db_session,
        employee_id=employee.id,
        department_id=department.id,
        role=MembershipRole.LEAD,
    )
    return employee


@pytest_asyncio.fixture
async def regular_member(
    db_session: AsyncSession, department: Department
) -> Employee:
    employee = await _make_employee(
        db_session, department_id=department.id, name="Regular Member"
    )
    await _make_membership(
        db_session,
        employee_id=employee.id,
        department_id=department.id,
        role=MembershipRole.MEMBER,
    )
    return employee


@pytest_asyncio.fixture
async def lead_client(
    db_session: AsyncSession, lead_employee: Employee
) -> AsyncIterator[httpx.AsyncClient]:
    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    async def _db_override():
        yield db_session

    async def _user_override():
        return lead_employee

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = _user_override

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        try:
            yield ac
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def member_client(
    db_session: AsyncSession, regular_member: Employee
) -> AsyncIterator[httpx.AsyncClient]:
    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    async def _db_override():
        yield db_session

    async def _user_override():
        return regular_member

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = _user_override

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        try:
            yield ac
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


async def test_lead_can_create_bind_code(
    lead_client: httpx.AsyncClient, department: Department
):
    resp = await lead_client.post(
        "/api/telegram/bindings",
        json={"department_id": str(department.id)},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["department_id"] == str(department.id)
    assert body["is_active"] is False
    assert body["bind_code"] is not None
    assert body["bind_code"].startswith("CMD-")
    assert body["bind_code_expires_at"] is not None


async def test_regular_member_cannot_create_bind_code(
    member_client: httpx.AsyncClient, department: Department
):
    resp = await member_client.post(
        "/api/telegram/bindings",
        json={"department_id": str(department.id)},
    )
    assert resp.status_code == 403, resp.text


async def test_lead_lists_bindings_for_department(
    lead_client: httpx.AsyncClient, department: Department
):
    create = await lead_client.post(
        "/api/telegram/bindings",
        json={"department_id": str(department.id)},
    )
    assert create.status_code == 201, create.text
    created_id = create.json()["id"]

    listing = await lead_client.get(
        "/api/telegram/bindings",
        params={"department_id": str(department.id)},
    )
    assert listing.status_code == 200, listing.text
    rows = listing.json()
    assert any(row["id"] == created_id for row in rows)


async def test_lead_can_disable_binding(
    lead_client: httpx.AsyncClient, department: Department
):
    create = await lead_client.post(
        "/api/telegram/bindings",
        json={"department_id": str(department.id)},
    )
    assert create.status_code == 201, create.text
    binding_id = create.json()["id"]

    delete = await lead_client.delete(f"/api/telegram/bindings/{binding_id}")
    assert delete.status_code == 200, delete.text
    body = delete.json()
    assert body["id"] == binding_id
    assert body["is_active"] is False
    assert body["disabled_at"] is not None


async def test_regular_member_cannot_list_other_departments(
    member_client: httpx.AsyncClient, department: Department
):
    resp = await member_client.get(
        "/api/telegram/bindings",
        params={"department_id": str(department.id)},
    )
    assert resp.status_code == 403, resp.text
