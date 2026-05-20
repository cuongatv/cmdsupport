# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""
API tests for ``/api/admin/telegram/settings``.

Verifies that:
* GET returns ``bot_token_configured=False`` on a fresh DB.
* PUT with a bot token succeeds, subsequent GET reports it as configured,
  and the raw token never appears in any response body.
* Non-admin callers receive 403.
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
async def admin_employee(db_session: AsyncSession) -> Employee:
    dept_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": dept_id, "name": f"Tg Admin Dept {dept_id.hex[:8]}"},
    )
    emp_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, username, role, department_id, is_active)
            VALUES (:id, :name, :email, :username, 'admin', :dept_id, true)
            """
        ),
        {
            "id": emp_id,
            "name": "Telegram Admin",
            "email": f"{emp_id.hex[:12]}@example.test",
            "username": f"tg_admin_{emp_id.hex[:12]}",
            "dept_id": dept_id,
        },
    )
    employee = await db_session.get(Employee, emp_id)
    assert employee is not None
    return employee


@pytest_asyncio.fixture
async def regular_employee(db_session: AsyncSession) -> Employee:
    dept_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": dept_id, "name": f"Tg Regular Dept {dept_id.hex[:8]}"},
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
            "name": "Telegram Regular",
            "email": f"{emp_id.hex[:12]}@example.test",
            "username": f"tg_reg_{emp_id.hex[:12]}",
            "dept_id": dept_id,
        },
    )
    employee = await db_session.get(Employee, emp_id)
    assert employee is not None
    return employee


@pytest_asyncio.fixture
async def admin_client(
    db_session: AsyncSession, admin_employee: Employee
) -> AsyncIterator[httpx.AsyncClient]:
    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    async def _db_override():
        yield db_session

    async def _user_override():
        return admin_employee

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
async def regular_client(
    db_session: AsyncSession, regular_employee: Employee
) -> AsyncIterator[httpx.AsyncClient]:
    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    async def _db_override():
        yield db_session

    async def _user_override():
        return regular_employee

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


async def test_admin_can_read_initial_status_with_no_token_configured(
    admin_client: httpx.AsyncClient,
):
    resp = await admin_client.get("/api/admin/telegram/settings")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bot_token_configured"] is False
    assert body["webhook_secret_configured"] is False
    assert body["is_enabled"] is False


async def test_admin_put_sets_bot_token_and_get_reflects_configured(
    admin_client: httpx.AsyncClient,
):
    raw_token = "123:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789"

    put_resp = await admin_client.put(
        "/api/admin/telegram/settings",
        json={"bot_token": raw_token, "is_enabled": True},
    )
    assert put_resp.status_code == 200, put_resp.text
    put_body = put_resp.json()
    # The raw token MUST NOT leak through any response field.
    assert raw_token not in put_resp.text
    assert put_body["bot_token_configured"] is True
    assert put_body["is_enabled"] is True

    # Subsequent GET confirms persistence + still hides the token.
    get_resp = await admin_client.get("/api/admin/telegram/settings")
    assert get_resp.status_code == 200, get_resp.text
    get_body = get_resp.json()
    assert get_body["bot_token_configured"] is True
    assert get_body["is_enabled"] is True
    assert raw_token not in get_resp.text


async def test_admin_put_webhook_secret_is_masked_in_response(
    admin_client: httpx.AsyncClient,
):
    raw_secret = "my-webhook-secret-xyz-9999"
    resp = await admin_client.put(
        "/api/admin/telegram/settings",
        json={"webhook_secret": raw_secret, "webhook_url": "https://x.test/hook"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert raw_secret not in resp.text
    assert body["webhook_secret_configured"] is True
    assert body["webhook_url"] == "https://x.test/hook"
    assert body["webhook_last_set_at"] is not None


async def test_regular_employee_cannot_read_settings(
    regular_client: httpx.AsyncClient,
):
    resp = await regular_client.get("/api/admin/telegram/settings")
    assert resp.status_code == 403, resp.text


async def test_regular_employee_cannot_update_settings(
    regular_client: httpx.AsyncClient,
):
    resp = await regular_client.put(
        "/api/admin/telegram/settings",
        json={"bot_token": "123:should-not-be-stored"},
    )
    assert resp.status_code == 403, resp.text
