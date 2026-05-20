# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""API tests for ``GET /api/admin/telegram/diagnostics``.

Verifies that:
* Admins receive a 200 with diagnostics that NEVER include the raw bot token.
* Non-admins receive 403.
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
from app.services.config_service import ConfigService

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def admin_employee(db_session: AsyncSession) -> Employee:
    dept_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": dept_id, "name": f"Tg Diag Admin Dept {dept_id.hex[:8]}"},
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
            "name": "Telegram Diag Admin",
            "email": f"{emp_id.hex[:12]}@example.test",
            "username": f"tg_diag_admin_{emp_id.hex[:12]}",
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
        {"id": dept_id, "name": f"Tg Diag Regular Dept {dept_id.hex[:8]}"},
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
            "name": "Telegram Diag Regular",
            "email": f"{emp_id.hex[:12]}@example.test",
            "username": f"tg_diag_reg_{emp_id.hex[:12]}",
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


async def test_get_diagnostics_as_admin_returns_200_no_secrets(
    db_session: AsyncSession, admin_client: httpx.AsyncClient
):
    raw_token = "987654321:zyxwvutsrqponmlkjihgfedcba0123456789"
    raw_secret = "diag-webhook-secret-12345-abcdef"

    svc = ConfigService(db_session)
    await svc.set("telegram_bot_token", raw_token)
    await svc.set("telegram_webhook_secret", raw_secret)

    resp = await admin_client.get("/api/admin/telegram/diagnostics")
    assert resp.status_code == 200, resp.text

    # The raw token and secret MUST NOT leak into any response field.
    assert raw_token not in resp.text
    assert raw_secret not in resp.text

    body = resp.json()
    assert body["configured"] is True
    assert "configured" in body
    assert "enabled" in body
    assert "active_bindings" in body
    assert "disabled_bindings" in body
    assert "active_identities" in body
    assert "outbox_pending" in body
    assert "outbox_sending" in body
    assert "outbox_failed_last_24h" in body
    assert "outbox_sent_last_24h" in body
    assert "last_webhook_received_at" in body
    assert "last_outbox_error" in body
    assert "last_outbox_error_at" in body
    assert "webhook_last_set_at" in body
    assert "bot_username" in body
    # No secret-shaped field names should appear in the response payload.
    assert "bot_token" not in body
    assert "webhook_secret" not in body


async def test_get_diagnostics_non_admin_forbidden(
    regular_client: httpx.AsyncClient,
):
    resp = await regular_client.get("/api/admin/telegram/diagnostics")
    assert resp.status_code == 403, resp.text
