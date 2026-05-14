"""
API-level tests for department membership endpoints (T9).

These tests run entirely in-process via httpx ASGITransport and never touch
PostgreSQL: ``get_db`` is replaced with a no-op, ``get_current_user`` returns
a synthetic admin, and ``app.services.membership_service`` calls are patched
with monkeypatched stubs. The intent is to lock the *HTTP contract* of the
new routes (status codes, error translation, schema rejection), not to
re-test the service-layer behavior that already lives in
``tests/services/test_membership_service.py``.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport

from app.database.models import MembershipRole
from app.services.membership_service import (
    DepartmentArchiveBlockedError,
    LastActiveMembershipError,
    MembershipRoleNotAllowedError,
    PrimaryMembershipRequiredError,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Synthetic admin & dependency overrides
# ---------------------------------------------------------------------------

_ADMIN_ID = uuid.uuid4()
_ADMIN = SimpleNamespace(
    id=_ADMIN_ID,
    name="Smoke Admin",
    email="admin@cmdsupport.local",
    role="admin",
    custom_role=None,
    department_id=uuid.uuid4(),
)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """In-process ASGI client with auth + DB dependencies overridden."""
    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    async def _noop_db():
        yield SimpleNamespace()

    async def _admin_user():
        return _ADMIN

    async def _audit_noop(*_args, **_kwargs):
        return None

    app.dependency_overrides[get_db] = _noop_db
    app.dependency_overrides[get_current_user] = _admin_user
    # Audit logging would otherwise try to talk to the noop session.
    import app.routers.departments as departments_module

    original_log_audit = departments_module.log_audit
    departments_module.log_audit = _audit_noop

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        try:
            yield ac
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)
            departments_module.log_audit = original_log_audit


def _make_membership(
    *,
    employee_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    role: MembershipRole = MembershipRole.MEMBER,
    is_primary: bool = False,
    is_active: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        employee_id=employee_id or uuid.uuid4(),
        department_id=department_id or uuid.uuid4(),
        role=role,
        capacity_percent=None,
        is_primary=is_primary,
        is_active=is_active,
    )


# Returned by the patched session for `db.refresh` / `db.commit` — no-op.
async def _async_noop(*_args, **_kwargs):  # pragma: no cover - trivial
    return None


def _patch_session_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the bits of routers/departments.py that touch the session.

    The noop ``get_db`` yields a bare ``SimpleNamespace``, so any
    ``await db.commit() / db.refresh()`` would explode without these stubs.
    """
    import app.routers.departments as departments_module

    async def _commit():
        return None

    async def _refresh(_obj, *_args, **_kwargs):
        return None

    async def _resolve_name(_db, _employee_id):
        return "Stub Employee"

    monkeypatch.setattr(
        departments_module,
        "_resolve_employee_name",
        _resolve_name,
    )

    # Patch SimpleNamespace to grow async commit/refresh methods.
    # SimpleNamespace doesn't support setattr in this way for instance methods,
    # so we patch via the dependency_overrides instead.
    from app.database import get_db
    from app.main import app

    class _StubSession:
        async def commit(self):  # noqa: D401 - stub
            return None

        async def refresh(self, _obj, *_args, **_kwargs):
            return None

        async def flush(self):
            return None

        async def get(self, _model, _ident):
            # Returning a truthy stub is enough for the existence checks
            # in update_department / list_members.
            return SimpleNamespace(
                id=_ident,
                name="Stub Department",
                description=None,
                unit_type=None,
                is_archived=False,
                archived_at=None,
            )

        async def execute(self, *_args, **_kwargs):
            # Return an object with .scalars().all() == []
            class _Scalars:
                def all(self):
                    return []

                def scalar(self):
                    return 0

            class _Result:
                def scalars(self):
                    return _Scalars()

                def scalar(self):
                    return 0

                def all(self):
                    return []

            return _Result()

    async def _stub_db():
        yield _StubSession()

    app.dependency_overrides[get_db] = _stub_db


# ---------------------------------------------------------------------------
# Department PATCH — unit_type immutability
# ---------------------------------------------------------------------------

async def test_patch_department_rejects_unit_type_change_with_400(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_session_helpers(monkeypatch)
    dept_id = uuid.uuid4()
    resp = await client.patch(
        f"/api/departments/{dept_id}",
        json={"unit_type": "squad_team"},
    )
    assert resp.status_code == 400, resp.text
    assert "unit_type" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /departments/{id}/members
# ---------------------------------------------------------------------------

async def test_add_member_invalid_role_returns_400(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_session_helpers(monkeypatch)
    import app.routers.departments as departments_module

    async def _raise_role(*_args, **_kwargs):
        raise MembershipRoleNotAllowedError(
            "role 'product_owner' not allowed for unit_type 'business_group'"
        )

    monkeypatch.setattr(
        departments_module.membership_service,
        "create_membership",
        _raise_role,
    )

    dept_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    resp = await client.post(
        f"/api/departments/{dept_id}/members",
        json={"employee_id": str(employee_id), "role": "product_owner"},
    )
    assert resp.status_code == 400, resp.text
    assert "product_owner" in resp.json()["detail"]


async def test_add_member_valid_returns_201(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_session_helpers(monkeypatch)
    import app.routers.departments as departments_module

    dept_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    membership = _make_membership(
        employee_id=employee_id,
        department_id=dept_id,
        role=MembershipRole.MEMBER,
    )

    async def _ok(*_args, **_kwargs):
        return membership

    monkeypatch.setattr(
        departments_module.membership_service,
        "create_membership",
        _ok,
    )

    resp = await client.post(
        f"/api/departments/{dept_id}/members",
        json={"employee_id": str(employee_id), "role": "member"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == str(membership.id)
    assert body["role"] == "member"
    assert body["employee_id"] == str(employee_id)


# ---------------------------------------------------------------------------
# PATCH /memberships/{id}
# ---------------------------------------------------------------------------

async def test_update_membership_role_invalid_returns_400(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_session_helpers(monkeypatch)
    import app.routers.departments as departments_module

    async def _raise_role(*_args, **_kwargs):
        raise MembershipRoleNotAllowedError(
            "role 'scrum_master' not allowed for unit_type 'business_group'"
        )

    monkeypatch.setattr(
        departments_module.membership_service,
        "update_membership",
        _raise_role,
    )

    membership_id = uuid.uuid4()
    resp = await client.patch(
        f"/api/memberships/{membership_id}",
        json={"role": "scrum_master"},
    )
    assert resp.status_code == 400, resp.text
    assert "scrum_master" in resp.json()["detail"]


async def test_update_membership_deactivate_last_active_returns_409(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_session_helpers(monkeypatch)
    import app.routers.departments as departments_module

    async def _raise_last(*_args, **_kwargs):
        raise LastActiveMembershipError(
            "Cannot deactivate the only active primary membership"
        )

    monkeypatch.setattr(
        departments_module.membership_service,
        "update_membership",
        _raise_last,
    )

    membership_id = uuid.uuid4()
    resp = await client.patch(
        f"/api/memberships/{membership_id}",
        json={"is_active": False},
    )
    assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# PATCH /memberships/{id}/primary
# ---------------------------------------------------------------------------

async def test_set_primary_returns_200(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_session_helpers(monkeypatch)
    import app.routers.departments as departments_module

    membership = _make_membership(is_primary=True)

    async def _ok(*_args, **_kwargs):
        return membership

    monkeypatch.setattr(
        departments_module.membership_service,
        "set_primary",
        _ok,
    )

    resp = await client.patch(f"/api/memberships/{membership.id}/primary")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_primary"] is True


# ---------------------------------------------------------------------------
# POST /departments/{id}/archive — open task projects
# ---------------------------------------------------------------------------

async def test_archive_with_open_projects_returns_409(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_session_helpers(monkeypatch)
    import app.routers.departments as departments_module

    async def _blocked(*_args, **_kwargs):
        raise DepartmentArchiveBlockedError(open_project_count=2)

    monkeypatch.setattr(
        departments_module.membership_service,
        "archive_department",
        _blocked,
    )

    dept_id = uuid.uuid4()
    resp = await client.post(f"/api/departments/{dept_id}/archive")
    assert resp.status_code == 409, resp.text
    assert "open task project" in resp.json()["detail"]


async def test_archive_no_open_projects_returns_200(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_session_helpers(monkeypatch)
    import app.routers.departments as departments_module

    dept_id = uuid.uuid4()

    async def _ok(*_args, **_kwargs):
        return {"archived": True, "department_id": str(dept_id)}

    monkeypatch.setattr(
        departments_module.membership_service,
        "archive_department",
        _ok,
    )

    resp = await client.post(f"/api/departments/{dept_id}/archive")
    assert resp.status_code == 200, resp.text
    assert resp.json()["archived"] is True


# ---------------------------------------------------------------------------
# POST /departments/{id}/unarchive
# ---------------------------------------------------------------------------

async def test_unarchive_returns_200(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_session_helpers(monkeypatch)
    import app.routers.departments as departments_module

    dept_id = uuid.uuid4()

    async def _ok(*_args, **_kwargs):
        return {"archived": False, "department_id": str(dept_id)}

    monkeypatch.setattr(
        departments_module.membership_service,
        "unarchive_department",
        _ok,
    )

    resp = await client.post(f"/api/departments/{dept_id}/unarchive")
    assert resp.status_code == 200, resp.text
    assert resp.json()["archived"] is False


# ---------------------------------------------------------------------------
# DELETE /api/departments/{id} — guarded by membership_service.delete_department
# ---------------------------------------------------------------------------

async def test_delete_blocked_not_archived_returns_409(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_session_helpers(monkeypatch)
    import app.routers.rbac as rbac_module
    from app.services.membership_service import DepartmentDeleteBlockedError

    async def _blocked(*_args, **_kwargs):
        raise DepartmentDeleteBlockedError(
            ["department must be archived first", "3 membership row(s) still exist"]
        )

    monkeypatch.setattr(
        rbac_module.membership_service,
        "delete_department",
        _blocked,
    )

    # Also patch the audit hook in rbac since the test session is a stub.
    async def _audit_noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(rbac_module, "log_audit", _audit_noop)

    dept_id = uuid.uuid4()
    resp = await client.delete(f"/api/departments/{dept_id}")
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert "archived" in detail
    assert "membership" in detail


# ---------------------------------------------------------------------------
# DELETE /memberships/{id}
# ---------------------------------------------------------------------------

async def test_delete_membership_primary_blocked_returns_409(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    _patch_session_helpers(monkeypatch)
    import app.routers.departments as departments_module

    async def _blocked(*_args, **_kwargs):
        raise PrimaryMembershipRequiredError(
            "Cannot delete the only membership"
        )

    monkeypatch.setattr(
        departments_module.membership_service,
        "delete_membership",
        _blocked,
    )

    membership_id = uuid.uuid4()
    resp = await client.delete(f"/api/memberships/{membership_id}")
    assert resp.status_code == 409, resp.text
