"""Integration coverage for Agile Phase 1-5 feature flag boundaries."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Employee
from app.services.task_constants import FEATURE_DISABLED_ERROR_CODE
from app.services.task_flow_service import capture_flow_snapshot
from app.services.task_project_service import get_or_create_template

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def admin_employee(db_session: AsyncSession) -> Employee:
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name, unit_type) VALUES (:id, :name, 'squad_team')"),
        {
            "id": department_id,
            "name": f"Agile Flag Dept {department_id.hex[:8]}",
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
            "name": "Agile Flag Admin",
            "email": f"{employee_id.hex[:12]}@agile-flags.test",
            "department_id": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    admin_employee: Employee,
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
        transport=transport,
        base_url="http://testserver",
    ) as client:
        try:
            yield client
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def reset_agile_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    for phase in range(1, 6):
        monkeypatch.setattr(settings, f"FEATURE_AGILE_PHASE_{phase}", False)


async def _create_project(api_client: httpx.AsyncClient, admin: Employee) -> dict:
    suffix = uuid.uuid4().hex[:6].upper()
    resp = await api_client.post(
        "/api/tasks/projects",
        json={
            "name": f"Agile Flag Project {suffix}",
            "identifier": f"AF{suffix[:5]}",
            "department_id": str(admin.department_id),
            "allow_any_employee": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _states(api_client: httpx.AsyncClient, project_id: str) -> list[dict]:
    resp = await api_client.get(f"/api/tasks/projects/{project_id}/states")
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert states
    return states


async def _create_task(
    api_client: httpx.AsyncClient,
    project_id: str,
    state_id: str,
    *,
    title: str = "Agile flag task",
    extra: dict | None = None,
) -> dict:
    body = {
        "title": title,
        "state_id": state_id,
        "assignee_ids": [],
        "label_ids": [],
    }
    if extra:
        body.update(extra)
    resp = await api_client.post(
        "/api/tasks",
        params={"task_project_id": project_id},
        json=body,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _assert_feature_disabled(resp: httpx.Response) -> None:
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == FEATURE_DISABLED_ERROR_CODE


async def test_phase5_disabled_hides_flow_metrics(
    api_client: httpx.AsyncClient,
    admin_employee: Employee,
) -> None:
    project = await _create_project(api_client, admin_employee)

    for resp in [
        await api_client.get(
            f"/api/task-projects/{project['id']}/flow-metrics",
            params={"start_date": "2026-05-17", "end_date": "2026-05-17"},
        ),
        await api_client.get(
            f"/api/task-projects/{project['id']}/throughput",
            params={"start_date": "2026-05-17", "end_date": "2026-05-17"},
        ),
        await api_client.post(f"/api/task-projects/{project['id']}/flow-metrics/snapshot"),
    ]:
        _assert_feature_disabled(resp)


async def test_phase5_disabled_hides_governance_endpoints(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_employee: Employee,
) -> None:
    """Phase 5 advisory read surfaces are hidden while prior audit reads remain usable."""
    project = await _create_project(api_client, admin_employee)
    states = await _states(api_client, project["id"])
    task = await _create_task(api_client, project["id"], states[0]["id"])

    # A normal audit query still works; the Phase-5 governance advisory filter
    # must be explicitly hidden by the flag so operators do not see the Stage A
    # advisory stream before rollout.
    audit_resp = await api_client.get("/api/audit/log", params={"page_size": 1})
    assert audit_resp.status_code == 200, audit_resp.text

    advisory_resp = await api_client.get(
        "/api/audit/log",
        params={"action": "permission_denied_advisory", "page_size": 1},
    )
    _assert_feature_disabled(advisory_resp)

    # Governance-producing mutations are owned by their prior-phase flags and
    # remain available; with Phase 5 off they simply omit advisory metadata.
    await get_or_create_template(db_session, uuid.UUID(project["id"]))
    move_resp = await api_client.post(
        f"/api/tasks/{task['id']}/move",
        json={
            "state_id": states[-1]["id"],
            "position": 5000.0,
            "version": task["version"],
        },
    )
    assert move_resp.status_code == 200, move_resp.text
    assert "governance_advisories" not in move_resp.json()
    assert "advisory" not in move_resp.json()


async def test_phase1_2_3_4_still_work_when_phase5_disabled(
    api_client: httpx.AsyncClient,
    admin_employee: Employee,
) -> None:
    settings.FEATURE_AGILE_PHASE_1 = True
    settings.FEATURE_AGILE_PHASE_2 = True
    settings.FEATURE_AGILE_PHASE_3 = True
    settings.FEATURE_AGILE_PHASE_4 = True
    settings.FEATURE_AGILE_PHASE_5 = False

    project = await _create_project(api_client, admin_employee)
    states = await _states(api_client, project["id"])
    todo = states[0]

    phase1_resp = await api_client.patch(
        f"/api/tasks/projects/{project['id']}/states/{todo['id']}",
        json={"wip_limit": 3, "wip_policy": "warn", "aging_warn_days": 5},
    )
    assert phase1_resp.status_code == 200, phase1_resp.text
    assert phase1_resp.json()["wip_limit"] == 3

    sprint_resp = await api_client.post(
        f"/api/task-projects/{project['id']}/sprints",
        json={"name": "Sprint Phase 2"},
    )
    assert sprint_resp.status_code == 201, sprint_resp.text

    capacity_resp = await api_client.get(
        f"/api/departments/{admin_employee.department_id}/agile/capacity"
    )
    assert capacity_resp.status_code == 200, capacity_resp.text
    assert isinstance(capacity_resp.json(), list)

    template_resp = await api_client.put(
        f"/api/tasks/projects/{project['id']}/template",
        json={"dor_template": ["Rõ yêu cầu"], "dod_template": ["Đã kiểm thử"]},
    )
    assert template_resp.status_code == 200, template_resp.text
    assert template_resp.json()["dor_template"] == ["Rõ yêu cầu"]

    flow_resp = await api_client.get(
        f"/api/task-projects/{project['id']}/flow-metrics",
        params={"start_date": "2026-05-17", "end_date": "2026-05-17"},
    )
    _assert_feature_disabled(flow_resp)


async def test_each_phase_independently_controlled(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_employee: Employee,
) -> None:
    project = await _create_project(api_client, admin_employee)
    states = await _states(api_client, project["id"])

    # Phase 1 off: WIP settings reject, but Phase 2 sprint write still works.
    settings.FEATURE_AGILE_PHASE_1 = False
    settings.FEATURE_AGILE_PHASE_2 = True
    phase1_resp = await api_client.patch(
        f"/api/tasks/projects/{project['id']}/states/{states[0]['id']}",
        json={"wip_limit": 2},
    )
    _assert_feature_disabled(phase1_resp)
    phase2_resp = await api_client.post(
        f"/api/task-projects/{project['id']}/sprints",
        json={"name": "Independent Sprint"},
    )
    assert phase2_resp.status_code == 201, phase2_resp.text

    # Phase 2 off: sprint writes reject, but Phase 3 capacity stays available.
    settings.FEATURE_AGILE_PHASE_2 = False
    settings.FEATURE_AGILE_PHASE_3 = True
    phase2_off_resp = await api_client.post(
        f"/api/task-projects/{project['id']}/sprints",
        json={"name": "Blocked Sprint"},
    )
    _assert_feature_disabled(phase2_off_resp)
    phase3_resp = await api_client.get(
        f"/api/departments/{admin_employee.department_id}/agile/capacity"
    )
    assert phase3_resp.status_code == 200, phase3_resp.text

    # Phase 3 off: capacity rejects, while Phase 4 template writes still work.
    settings.FEATURE_AGILE_PHASE_3 = False
    settings.FEATURE_AGILE_PHASE_4 = True
    phase3_off_resp = await api_client.get(
        f"/api/departments/{admin_employee.department_id}/agile/capacity"
    )
    _assert_feature_disabled(phase3_off_resp)
    phase4_resp = await api_client.put(
        f"/api/tasks/projects/{project['id']}/template",
        json={"dor_template": ["Ready"], "dod_template": ["Done"]},
    )
    assert phase4_resp.status_code == 200, phase4_resp.text

    # Phase 4 off: template writes reject, while Phase 5 metrics stay available.
    settings.FEATURE_AGILE_PHASE_4 = False
    settings.FEATURE_AGILE_PHASE_5 = True
    phase4_off_resp = await api_client.put(
        f"/api/tasks/projects/{project['id']}/template",
        json={"dor_template": ["Blocked"], "dod_template": ["Blocked"]},
    )
    _assert_feature_disabled(phase4_off_resp)
    await _create_task(api_client, project["id"], states[0]["id"])
    await capture_flow_snapshot(db_session, uuid.UUID(project["id"]), snapshot_date=date(2026, 5, 17))
    phase5_resp = await api_client.get(
        f"/api/task-projects/{project['id']}/flow-metrics",
        params={"start_date": "2026-05-17", "end_date": "2026-05-17"},
    )
    assert phase5_resp.status_code == 200, phase5_resp.text
    assert phase5_resp.json()

    # Phase 5 off: metrics reject without breaking Phase 1 writes.
    settings.FEATURE_AGILE_PHASE_1 = True
    settings.FEATURE_AGILE_PHASE_5 = False
    phase5_off_resp = await api_client.get(
        f"/api/task-projects/{project['id']}/flow-metrics",
        params={"start_date": "2026-05-17", "end_date": "2026-05-17"},
    )
    _assert_feature_disabled(phase5_off_resp)
    phase1_again_resp = await api_client.patch(
        f"/api/tasks/projects/{project['id']}/states/{states[0]['id']}",
        json={"wip_limit": 4, "wip_policy": "warn"},
    )
    assert phase1_again_resp.status_code == 200, phase1_again_resp.text
