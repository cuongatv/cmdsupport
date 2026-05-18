"""API tests for the Phase 2 Sprint lifecycle endpoints.

Mirrors the ``tests/api/test_agile_phase_1.py`` strategy: in-process ASGI
client against the real router + service stack, ``db_session`` rollback
fixture for isolation, ``settings.FEATURE_AGILE_PHASE_2`` flipped per-test
via ``monkeypatch``. The synthetic admin actor bypasses
``require_permission`` so the sprint contract is exercised in isolation
from RBAC plumbing.

Covered scenarios (T7 acceptance criteria):

* ``test_create_and_activate_sprint`` — create + start happy path, status
  transitions persist, audit row exists.
* ``test_second_active_sprint_rejected`` — partial-unique invariant maps
  to ``409 ACTIVE_SPRINT_EXISTS``.
* ``test_sprint_close_unlinks_tasks`` — close clears ``sprint_id`` on
  still-open tasks but preserves the link on terminal tasks.
* ``test_sprint_disabled_returns_feature_disabled`` — write endpoints
  short-circuit with ``403 FEATURE_DISABLED`` when the flag is off.
* ``test_invalid_date_range_rejected`` — ``start_date > end_date`` maps
  to ``409 INVALID_DATE_RANGE``.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    AuditLog,
    Employee,
    Sprint,
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
            "name": f"Sprint Test Dept {department_id.hex[:8]}",
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
            "name": "Sprint API Admin",
            "email": f"{employee_id.hex[:12]}@example.test",
            "department_id": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


@pytest_asyncio.fixture
async def task_project(
    db_session: AsyncSession, admin_employee: Employee
) -> TaskProject:
    """A department-scoped project plus a backlog + done state.

    The two states cover the ``close_sprint`` semantics: a backlog-group
    task stays "open" and gets unlinked on close, while a done-group task
    stays linked to the closed sprint for historical clarity.
    """
    project = TaskProject(
        name="Sprint Test Project",
        description=None,
        identifier=f"SP{uuid.uuid4().hex[:5].upper()}",
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
    done = TaskState(
        task_project_id=project.id,
        name="Done",
        group="done",
        position=1000.0,
        is_default=False,
    )
    db_session.add_all([backlog, done])
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


async def _make_task(
    db: AsyncSession,
    project: TaskProject,
    *,
    state_group: str,
    sprint_id: uuid.UUID,
    title: str,
) -> Task:
    """Create a task in the requested state group, linked to ``sprint_id``."""
    state = (
        await db.execute(
            select(TaskState).where(
                TaskState.task_project_id == project.id,
                TaskState.group == state_group,
            )
        )
    ).scalar_one()
    task = Task(
        task_project_id=project.id,
        state_id=state.id,
        title=title,
        priority="none",
        sprint_id=sprint_id,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def test_create_and_activate_sprint(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    task_project: TaskProject,
    admin_employee: Employee,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create returns 201/planned, activate transitions to active, audit logged."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)

    create_resp = await api_client.post(
        f"/api/task-projects/{task_project.id}/sprints",
        json={"name": "Sprint Thử Nghiệm 1", "goal": "Đo đạc baseline"},
    )
    assert create_resp.status_code == 201, create_resp.text
    payload = create_resp.json()
    assert payload["name"] == "Sprint Thử Nghiệm 1"
    assert payload["status"] == "planned"
    sprint_id = payload["id"]

    start_resp = await api_client.post(f"/api/sprints/{sprint_id}/start")
    assert start_resp.status_code == 200, start_resp.text
    assert start_resp.json()["status"] == "active"

    audit_row = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.resource_type == "sprint",
                AuditLog.resource_id == sprint_id,
                AuditLog.action == "sprint_created",
            )
        )
    ).scalar_one_or_none()
    assert audit_row is not None
    assert audit_row.principal_id == admin_employee.id


async def test_second_active_sprint_rejected(
    api_client: httpx.AsyncClient,
    task_project: TaskProject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Activating a second sprint for the same project surfaces 409."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)

    first = await api_client.post(
        f"/api/task-projects/{task_project.id}/sprints",
        json={"name": "Sprint Thử Nghiệm 1"},
    )
    assert first.status_code == 201, first.text
    first_id = first.json()["id"]
    started = await api_client.post(f"/api/sprints/{first_id}/start")
    assert started.status_code == 200, started.text

    second = await api_client.post(
        f"/api/task-projects/{task_project.id}/sprints",
        json={"name": "Sprint Thử Nghiệm 2"},
    )
    assert second.status_code == 201, second.text
    second_id = second.json()["id"]

    conflict = await api_client.post(f"/api/sprints/{second_id}/start")
    assert conflict.status_code == 409, conflict.text
    detail = conflict.json()["detail"]
    assert detail["code"] == "ACTIVE_SPRINT_EXISTS"
    assert detail["task_project_id"] == str(task_project.id)


async def test_sprint_close_unlinks_tasks(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    task_project: TaskProject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closing a sprint clears sprint_id on open tasks, keeps it on done tasks."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)

    create_resp = await api_client.post(
        f"/api/task-projects/{task_project.id}/sprints",
        json={"name": "Sprint Đóng Test"},
    )
    assert create_resp.status_code == 201, create_resp.text
    sprint_id = uuid.UUID(create_resp.json()["id"])
    start_resp = await api_client.post(f"/api/sprints/{sprint_id}/start")
    assert start_resp.status_code == 200, start_resp.text

    open_task = await _make_task(
        db_session,
        task_project,
        state_group="backlog",
        sprint_id=sprint_id,
        title="Open work",
    )
    done_task = await _make_task(
        db_session,
        task_project,
        state_group="done",
        sprint_id=sprint_id,
        title="Done work",
    )

    close_resp = await api_client.post(f"/api/sprints/{sprint_id}/close")
    assert close_resp.status_code == 200, close_resp.text
    assert close_resp.json()["status"] == "completed"

    await db_session.refresh(open_task)
    await db_session.refresh(done_task)
    assert open_task.sprint_id is None
    assert done_task.sprint_id == sprint_id


async def test_sprint_disabled_returns_feature_disabled(
    api_client: httpx.AsyncClient,
    task_project: TaskProject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write endpoints return 403 FEATURE_DISABLED when Phase 2 flag is off."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", False)

    resp = await api_client.post(
        f"/api/task-projects/{task_project.id}/sprints",
        json={"name": "Sprint Off"},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "FEATURE_DISABLED"

    # Reads stay open even with the flag off — confirms the gate is only on
    # writes, matching the contract documented in ``sprint_router``.
    list_resp = await api_client.get(
        f"/api/task-projects/{task_project.id}/sprints"
    )
    assert list_resp.status_code == 200, list_resp.text
    assert list_resp.json() == []


async def test_invalid_date_range_rejected(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    task_project: TaskProject,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``start_date > end_date`` surfaces 409 INVALID_DATE_RANGE and persists nothing."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)

    resp = await api_client.post(
        f"/api/task-projects/{task_project.id}/sprints",
        json={
            "name": "Sprint Sai Ngày",
            "start_date": "2026-06-10T00:00:00",
            "end_date": "2026-06-01T00:00:00",
        },
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"]["code"] == "INVALID_DATE_RANGE"

    # Defence-in-depth: confirm the partial-unique-index pre-check did not
    # leak a row past the validation gate.
    row_count = (
        await db_session.execute(
            select(Sprint).where(Sprint.task_project_id == task_project.id)
        )
    ).all()
    assert row_count == []
