# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""
API tests for ``/api/telegram/identities``.

Verifies the user-facing link-code flow:
* POST /link-codes returns a fresh ``LINK-...`` code.
* GET /me returns 404 before any code is consumed.
* DELETE /me revokes the active identity after consume.
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

from app.database.models import Employee

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def user_employee(db_session: AsyncSession) -> Employee:
    dept_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": dept_id, "name": f"Tg Ident Dept {dept_id.hex[:8]}"},
    )
    emp_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, username, role, department_id, is_active)
            VALUES (:id, :name, :email, :username, 'employee', :dept_id, true)
            """
        ),
        {
            "id": emp_id,
            "name": "Tg Identity User",
            "email": f"{emp_id.hex[:12]}@example.test",
            "username": f"tg_id_{emp_id.hex[:12]}",
            "dept_id": dept_id,
        },
    )
    employee = await db_session.get(Employee, emp_id)
    assert employee is not None
    return employee


@pytest_asyncio.fixture
async def user_client(
    db_session: AsyncSession, user_employee: Employee
) -> AsyncIterator[httpx.AsyncClient]:
    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    async def _db_override():
        yield db_session

    async def _user_override():
        return user_employee

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


async def test_get_me_returns_404_before_link(user_client: httpx.AsyncClient):
    resp = await user_client.get("/api/telegram/identities/me")
    assert resp.status_code == 404, resp.text


async def test_post_link_codes_returns_prefixed_code(
    user_client: httpx.AsyncClient,
):
    resp = await user_client.post("/api/telegram/identities/link-codes")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["link_code"].startswith("LINK-")
    assert body["expires_at"] is not None


async def test_delete_me_after_consume_revokes_identity(
    user_client: httpx.AsyncClient,
    user_employee: Employee,
    db_session: AsyncSession,
):
    # 1. Mint a link code over the API.
    code_resp = await user_client.post("/api/telegram/identities/link-codes")
    assert code_resp.status_code == 201, code_resp.text
    link_code = code_resp.json()["link_code"]

    # 2. Consume the code at the service layer (simulating /link in Telegram).
    from app.services import telegram_identity_service

    await telegram_identity_service.consume_link_code(
        db_session,
        code=link_code,
        telegram_user_id=900_000_000 + (user_employee.id.int % 1_000_000),
        telegram_username="tg_test_user",
        display_name="Tg Test User",
    )
    await db_session.flush()

    # 3. GET /me should now return the active identity.
    me_resp = await user_client.get("/api/telegram/identities/me")
    assert me_resp.status_code == 200, me_resp.text
    me_body = me_resp.json()
    assert me_body["is_active"] is True
    assert me_body["telegram_username"] == "tg_test_user"
    # The numeric telegram_user_id MUST NOT be exposed via the API.
    assert "telegram_user_id" not in me_body

    # 4. DELETE /me revokes it.
    delete_resp = await user_client.delete("/api/telegram/identities/me")
    assert delete_resp.status_code == 200, delete_resp.text
    delete_body = delete_resp.json()
    assert delete_body["is_active"] is False
    assert delete_body["revoked_at"] is not None

    # 5. GET /me is back to 404.
    me_again = await user_client.get("/api/telegram/identities/me")
    assert me_again.status_code == 404, me_again.text
