"""API tests for Agile Phase 5 flow metrics."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import Employee, Task, TaskProject, TaskState
from app.services.task_flow_service import capture_flow_snapshot

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def admin_employee(db_session: AsyncSession) -> Employee:
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {
            "id": department_id,
            "name": f"Phase 5 Metrics Dept {department_id.hex[:8]}",
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
            "name": "Phase 5 Metrics API Admin",
            "email": f"{employee_id.hex[:12]}@p5metrics.test",
            "department_id": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


@pytest_asyncio.fixture
async def project_with_tasks(
    db_session: AsyncSession,
    admin_employee: Employee,
) -> tuple[TaskProject, TaskState, TaskState, Task, Task]:
    project = TaskProject(
        name="Phase 5 Metrics Project",
        description=None,
        identifier=f"P5{uuid.uuid4().hex[:5].upper()}",
        department_id=admin_employee.department_id,
        created_by_id=admin_employee.id,
        allow_any_employee=False,
    )
    db_session.add(project)
    await db_session.flush()

    todo = TaskState(
        task_project_id=project.id,
        name="Todo",
        group="todo",
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
    db_session.add_all([todo, done])
    await db_session.flush()

    open_task = Task(
        task_project_id=project.id,
        state_id=todo.id,
        title="Open task",
        priority="none",
        position=1000.0,
        story_points=3,
        blocked_reason="Waiting for input",
    )
    done_task = Task(
        task_project_id=project.id,
        state_id=done.id,
        title="Done task",
        priority="none",
        position=1000.0,
        story_points=5,
    )
    db_session.add_all([open_task, done_task])
    await db_session.flush()
    return project, todo, done, open_task, done_task


@pytest_asyncio.fixture
async def api_client(
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
    ) as client:
        try:
            yield client
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


async def _force_task_updated_at(
    db_session: AsyncSession,
    task_id: uuid.UUID,
    when: datetime,
) -> None:
    await db_session.execute(
        text("UPDATE tasks SET updated_at = :updated_at WHERE id = :task_id"),
        {"updated_at": when, "task_id": task_id},
    )
    await db_session.flush()


async def test_capture_snapshot(
    db_session: AsyncSession,
    project_with_tasks: tuple[TaskProject, TaskState, TaskState, Task, Task],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)
    project, todo, done, _open_task, _done_task = project_with_tasks

    rows = await capture_flow_snapshot(
        db_session, project.id, snapshot_date=date(2026, 5, 17)
    )

    assert len(rows) == 2
    by_state = {row.state_id: row for row in rows}
    assert by_state[todo.id].task_count == 1
    assert by_state[todo.id].story_points_sum == 3
    assert by_state[todo.id].blocked_count == 1
    assert by_state[done.id].task_count == 1
    assert by_state[done.id].story_points_sum == 5
    assert by_state[done.id].blocked_count == 0

    # Idempotent: second capture for the same project/date returns existing rows.
    second = await capture_flow_snapshot(
        db_session, project.id, snapshot_date=date(2026, 5, 17)
    )
    assert len(second) == 2


async def test_get_flow_metrics_date_range(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project_with_tasks: tuple[TaskProject, TaskState, TaskState, Task, Task],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)
    project, _todo, _done, _open_task, _done_task = project_with_tasks
    await capture_flow_snapshot(db_session, project.id, snapshot_date=date(2026, 5, 16))
    await capture_flow_snapshot(db_session, project.id, snapshot_date=date(2026, 5, 17))

    resp = await api_client.get(
        f"/api/task-projects/{project.id}/flow-metrics",
        params={"start_date": "2026-05-17", "end_date": "2026-05-17"},
    )

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert len(payload) == 2
    assert {row["snapshot_date"] for row in payload} == {"2026-05-17"}
    assert payload[0]["snapshot_date"] <= payload[1]["snapshot_date"]


async def test_throughput_calculation(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    project_with_tasks: tuple[TaskProject, TaskState, TaskState, Task, Task],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)
    project, _todo, _done, open_task, done_task = project_with_tasks
    in_range = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
    out_of_range = in_range - timedelta(days=3)
    await _force_task_updated_at(db_session, done_task.id, in_range)
    await _force_task_updated_at(db_session, open_task.id, out_of_range)

    resp = await api_client.get(
        f"/api/task-projects/{project.id}/throughput",
        params={"start_date": "2026-05-17", "end_date": "2026-05-17"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"tasks_completed": 1, "story_points_completed": 5}


async def test_metrics_disabled_returns_403(
    api_client: httpx.AsyncClient,
    project_with_tasks: tuple[TaskProject, TaskState, TaskState, Task, Task],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", False)
    project, _todo, _done, _open_task, _done_task = project_with_tasks

    flow_resp = await api_client.get(
        f"/api/task-projects/{project.id}/flow-metrics",
        params={"start_date": "2026-05-17", "end_date": "2026-05-17"},
    )
    assert flow_resp.status_code == 403, flow_resp.text
    assert flow_resp.json()["detail"]["code"] == "FEATURE_DISABLED"

    throughput_resp = await api_client.get(
        f"/api/task-projects/{project.id}/throughput",
        params={"start_date": "2026-05-17", "end_date": "2026-05-17"},
    )
    assert throughput_resp.status_code == 403, throughput_resp.text
    assert throughput_resp.json()["detail"]["code"] == "FEATURE_DISABLED"

    snapshot_resp = await api_client.post(
        f"/api/task-projects/{project.id}/flow-metrics/snapshot"
    )
    assert snapshot_resp.status_code == 403, snapshot_resp.text
    assert snapshot_resp.json()["detail"]["code"] == "FEATURE_DISABLED"
