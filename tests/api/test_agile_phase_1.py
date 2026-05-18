from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Employee, TaskProject, TaskState
from app.schemas.tasks import TaskStateCreate, TaskStateOut, TaskStateUpdate


def test_legacy_task_state_payload_without_wip_fields() -> None:
    create = TaskStateCreate(name="Todo", group="todo")
    update = TaskStateUpdate(name="Đang thực hiện")
    state = TaskStateOut.model_validate(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "task_project_id": "00000000-0000-0000-0000-000000000002",
            "name": create.name,
            "group": create.group,
            "color": None,
            "position": 0.0,
            "is_default": False,
            "created_at": "2026-05-17T00:00:00Z",
            "updated_at": "2026-05-17T00:00:00Z",
        }
    )

    assert create.wip_limit is None
    assert create.wip_policy is None
    assert create.aging_warn_days is None
    assert update.wip_limit is None
    assert update.wip_policy is None
    assert update.aging_warn_days is None
    assert state.wip_limit is None
    assert state.wip_policy is None
    assert state.aging_warn_days is None


@pytest.mark.parametrize(
    ("module_path", "revision", "down_revision"),
    [
        ("alembic/versions/029_agile_phase_1.py", "029", "028"),
    ],
)
def test_agile_phase_1_migration_round_trip_marker(
    module_path: str,
    revision: str,
    down_revision: str,
) -> None:
    module_file = Path(__file__).resolve().parents[2] / module_path
    spec = importlib.util.spec_from_file_location("agile_phase_1_migration", module_file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == revision
    assert module.down_revision == down_revision
    assert hasattr(module, "upgrade")
    assert hasattr(module, "downgrade")


# ---------------------------------------------------------------------------
# API contract — Phase 1 WIP/aging gate on TaskState create + update endpoints
# ---------------------------------------------------------------------------
#
# Strategy mirrors tests/api/test_habits.py: in-process ASGI client with
# ``get_db`` and ``get_current_user`` overridden onto the rollback-isolated
# ``db_session`` fixture so endpoints exercise the real router AND service
# code paths against PostgreSQL — but no rows survive the test.
#
# ``settings.FEATURE_AGILE_PHASE_1`` is flipped per-test with monkeypatch so
# both halves of the feature gate (enabled ⇒ persist, disabled ⇒ 403
# FEATURE_DISABLED) can be asserted in a single run. Tests skip cleanly when
# Postgres is unreachable thanks to the upstream ``db_session`` fixture.


@pytest_asyncio.fixture
async def admin_employee(db_session: AsyncSession) -> Employee:
    """Insert a synthetic admin ``Employee`` on the rollback session.

    Admin role bypasses ``require_permission`` so we exercise the WIP-field
    gate in isolation rather than tangling it with RBAC.
    """
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {
            "id": department_id,
            "name": f"Agile Phase 1 Dept {department_id.hex[:8]}",
        },
    )
    employee_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, role, department_id, is_active)
            VALUES (:id, :name, :email, 'admin', :department_id, true)
            """
        ),
        {
            "id": employee_id,
            "name": "Phase 1 API Admin",
            "email": f"{employee_id.hex[:12]}@example.test",
            "department_id": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


@pytest_asyncio.fixture
async def task_project_with_state(
    db_session: AsyncSession, admin_employee: Employee
) -> tuple[TaskProject, TaskState]:
    """Materialise one department-scoped project with a single seed state."""
    project = TaskProject(
        name="Agile Phase 1 Project",
        description=None,
        identifier=f"AP{uuid.uuid4().hex[:5].upper()}",
        workspace_id=None,
        department_id=admin_employee.department_id,
        created_by_id=admin_employee.id,
        allow_any_employee=False,
    )
    db_session.add(project)
    await db_session.flush()

    state = TaskState(
        task_project_id=project.id,
        name="Backlog",
        group="backlog",
        position=0.0,
        is_default=True,
    )
    db_session.add(state)
    await db_session.flush()
    await db_session.refresh(state)
    return project, state


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession, admin_employee: Employee
) -> AsyncIterator[httpx.AsyncClient]:
    """In-process ASGI client bound to the rollback ``db_session`` + admin."""
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
    ) as client:
        try:
            yield client
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


async def test_update_task_state_wip_config_enabled(
    api_client: httpx.AsyncClient,
    task_project_with_state: tuple[TaskProject, TaskState],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With Phase 1 ON, PATCH persists WIP/aging fields and they round-trip via GET."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    project, state = task_project_with_state

    patch_resp = await api_client.patch(
        f"/api/tasks/projects/{project.id}/states/{state.id}",
        json={"wip_limit": 3, "wip_policy": "warn", "aging_warn_days": 5},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    patched = patch_resp.json()
    assert patched["wip_limit"] == 3
    assert patched["wip_policy"] == "warn"
    assert patched["aging_warn_days"] == 5

    get_resp = await api_client.get(f"/api/tasks/projects/{project.id}/states")
    assert get_resp.status_code == 200, get_resp.text
    fetched = next(row for row in get_resp.json() if row["id"] == str(state.id))
    assert fetched["wip_limit"] == 3
    assert fetched["wip_policy"] == "warn"
    assert fetched["aging_warn_days"] == 5


async def test_update_task_state_wip_config_disabled_returns_feature_disabled(
    api_client: httpx.AsyncClient,
    task_project_with_state: tuple[TaskProject, TaskState],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With Phase 1 OFF, PATCH carrying any WIP field fails with 403 FEATURE_DISABLED."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", False)
    project, state = task_project_with_state

    resp = await api_client.patch(
        f"/api/tasks/projects/{project.id}/states/{state.id}",
        json={"wip_limit": 5},
    )
    assert resp.status_code == 403, resp.text
    payload = resp.json()
    assert payload["detail"]["code"] == "FEATURE_DISABLED"

    # State row must remain unchanged — the gate runs before the service call.
    get_resp = await api_client.get(f"/api/tasks/projects/{project.id}/states")
    assert get_resp.status_code == 200, get_resp.text
    fetched = next(row for row in get_resp.json() if row["id"] == str(state.id))
    assert fetched["wip_limit"] is None


async def test_existing_clients_without_wip_fields_still_pass(
    api_client: httpx.AsyncClient,
    task_project_with_state: tuple[TaskProject, TaskState],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backward compat: payloads without WIP fields succeed regardless of flag.

    Runs both create and update (without the new fields) under flag OFF — the
    legacy path that pre-Phase-1 clients use must stay green so the rollout
    can't break existing callers.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", False)
    project, state = task_project_with_state

    create_resp = await api_client.post(
        f"/api/tasks/projects/{project.id}/states",
        json={"name": "Triage", "group": "todo"},
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["name"] == "Triage"
    assert created["wip_limit"] is None
    assert created["wip_policy"] == "off"
    assert created["aging_warn_days"] is None

    update_resp = await api_client.patch(
        f"/api/tasks/projects/{project.id}/states/{state.id}",
        json={"name": "Backlog renamed"},
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["name"] == "Backlog renamed"
