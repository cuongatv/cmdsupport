"""API tests for the Phase 4 task-project DoR/DoD template surface (T16).

Mirrors ``tests/api/test_agile_phase_4_knowledge.py``: in-process ASGI client
against the real router + service stack, ``db_session`` rollback fixture for
isolation, ``settings.FEATURE_AGILE_PHASE_4`` flipped per-test via
``monkeypatch``. Synthetic admin actor bypasses ``require_permission`` so the
template contract is exercised in isolation from RBAC plumbing.

Covered scenarios (T16 acceptance criteria):

* ``test_get_template_returns_empty_on_new_project`` — GET materialises an
  empty template row on first read regardless of the Phase 4 flag state.
* ``test_update_template_enabled`` — PUT with the flag ON persists the
  DoR/DoD arrays and the round-trip GET reflects the change.
* ``test_update_template_disabled_returns_403`` — PUT with the flag OFF
  fails with ``403 FEATURE_DISABLED``; GET stays open.
* ``test_update_template_does_not_affect_existing_tasks`` — changing the
  template after a task already exists does NOT mutate the task's
  ``dor_checklist`` / ``dod_checklist`` snapshot.
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
    Employee,
    Task,
    TaskProject,
    TaskState,
)


@pytest_asyncio.fixture
async def admin_employee(db_session: AsyncSession) -> Employee:
    """Synthetic admin ``Employee`` for the rollback session."""
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {
            "id": department_id,
            "name": f"Phase 4 Template Dept {department_id.hex[:8]}",
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
            "name": "Phase 4 Template API Admin",
            "email": f"{employee_id.hex[:12]}@example.test",
            "department_id": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


@pytest_asyncio.fixture
async def task_project(
    db_session: AsyncSession,
    admin_employee: Employee,
) -> TaskProject:
    """Department-scoped project with a default state for task creation."""
    project = TaskProject(
        name="Phase 4 Template Project",
        description=None,
        identifier=f"P4T{uuid.uuid4().hex[:5].upper()}",
        workspace_id=None,
        department_id=admin_employee.department_id,
        created_by_id=admin_employee.id,
        allow_any_employee=False,
    )
    db_session.add(project)
    await db_session.flush()

    backlog = TaskState(
        task_project_id=project.id,
        name="Backlog",
        group="backlog",
        position=0.0,
        is_default=True,
    )
    db_session.add(backlog)
    await db_session.flush()
    await db_session.refresh(project)
    return project


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession, admin_employee: Employee
) -> AsyncIterator[httpx.AsyncClient]:
    """In-process ASGI client wired to the rollback session + admin actor."""
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


async def test_get_template_returns_empty_on_new_project(
    api_client: httpx.AsyncClient,
    task_project: TaskProject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET materialises an empty template row regardless of the Phase 4 flag.

    The read surface is intentionally open under the OFF flag so dashboards
    that pre-fetch the template during a partial rollout do not see 403s.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_4", False)

    resp = await api_client.get(f"/api/tasks/projects/{task_project.id}/template")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["task_project_id"] == str(task_project.id)
    assert body["dor_template"] == []
    assert body["dod_template"] == []

    # Second read returns the same row — get_or_create is idempotent.
    again = await api_client.get(f"/api/tasks/projects/{task_project.id}/template")
    assert again.status_code == 200, again.text
    assert again.json()["id"] == body["id"]


async def test_update_template_enabled(
    api_client: httpx.AsyncClient,
    task_project: TaskProject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PUT with the flag ON persists the DoR/DoD arrays."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_4", True)

    dor = [
        {"label": "Yêu cầu đã được xác nhận", "done": False},
        {"label": "Tiêu chí chấp nhận rõ ràng", "done": False},
    ]
    dod = [
        {"label": "Đã kiểm thử", "done": False},
        {"label": "Đã review code", "done": False},
    ]

    resp = await api_client.put(
        f"/api/tasks/projects/{task_project.id}/template",
        json={"dor_template": dor, "dod_template": dod},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["dor_template"] == dor
    assert body["dod_template"] == dod

    # Round-trip GET reflects the change.
    get_resp = await api_client.get(
        f"/api/tasks/projects/{task_project.id}/template"
    )
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["dor_template"] == dor
    assert get_resp.json()["dod_template"] == dod


async def test_update_template_disabled_returns_403(
    api_client: httpx.AsyncClient,
    task_project: TaskProject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PUT with the flag OFF fails with 403 FEATURE_DISABLED; GET stays open."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_4", False)

    put_resp = await api_client.put(
        f"/api/tasks/projects/{task_project.id}/template",
        json={
            "dor_template": [{"label": "Mục tiêu rõ ràng", "done": False}],
            "dod_template": [],
        },
    )
    assert put_resp.status_code == 403, put_resp.text
    assert put_resp.json()["detail"]["code"] == "FEATURE_DISABLED"

    # GET remains accessible under the OFF flag.
    get_resp = await api_client.get(
        f"/api/tasks/projects/{task_project.id}/template"
    )
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["dor_template"] == []
    assert body["dod_template"] == []


async def test_update_template_does_not_affect_existing_tasks(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    task_project: TaskProject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Updating the template after a task exists leaves the task's snapshot intact.

    DoR/DoD on the task row is a one-time snapshot taken at create time
    (T6). Template edits must NOT retroactively rewrite that snapshot.
    """
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_4", True)

    # Seed a task with an explicit dor_checklist snapshot. We bypass the
    # ``create_task`` service so the test stays focused on the template
    # contract — the snapshot semantics are already covered by T6 tests.
    default_state = await db_session.scalar(
        text(
            """
            SELECT id FROM task_states
            WHERE task_project_id = :project_id
            ORDER BY position
            LIMIT 1
            """
        ).bindparams(project_id=task_project.id)
    )
    assert default_state is not None
    pre_existing_dor = [{"label": "Bước cũ", "done": False}]
    pre_existing_dod = [{"label": "Hoàn thành cũ", "done": False}]
    task = Task(
        task_project_id=task_project.id,
        state_id=default_state,
        title="Existing task with snapshot",
        priority="none",
        position=1000.0,
        dor_checklist=pre_existing_dor,
        dod_checklist=pre_existing_dod,
    )
    db_session.add(task)
    await db_session.flush()
    task_id = task.id

    # Now update the project's template to something completely different.
    new_dor = [{"label": "Yêu cầu mới đã được xác nhận", "done": False}]
    new_dod = [{"label": "Đã được Product Owner xác nhận", "done": False}]
    put_resp = await api_client.put(
        f"/api/tasks/projects/{task_project.id}/template",
        json={"dor_template": new_dor, "dod_template": new_dod},
    )
    assert put_resp.status_code == 200, put_resp.text

    # The pre-existing task's snapshot is untouched — re-fetch from the DB.
    await db_session.refresh(task)
    assert task.dor_checklist == pre_existing_dor
    assert task.dod_checklist == pre_existing_dod

    # Sanity: the template itself does reflect the new arrays.
    get_resp = await api_client.get(
        f"/api/tasks/projects/{task_project.id}/template"
    )
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["dor_template"] == new_dor
    assert get_resp.json()["dod_template"] == new_dod
    # task_id is referenced to silence the unused-variable lint while keeping
    # the intent (we read the task back through the session, not the API).
    assert task_id == task.id
