"""API coverage for the admin Agile dashboard flow summary."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    Project,
    ProjectMember,
    Role,
    Task,
    TaskProject,
    TaskState,
)

pytestmark = pytest.mark.asyncio


async def _employee(
    db_session: AsyncSession,
    *,
    department: Department,
    role_name: str,
    permissions: list[str],
) -> Employee:
    role = Role(
        name=f"{role_name}-{uuid.uuid4().hex[:8]}",
        permissions=permissions,
        is_system=False,
    )
    db_session.add(role)
    await db_session.flush()

    employee = Employee(
        name=role_name,
        email=f"{uuid.uuid4().hex[:12]}@dashboard.test",
        role="employee",
        department_id=department.id,
        custom_role_id=role.id,
        is_active=True,
    )
    db_session.add(employee)
    await db_session.flush()
    db_session.add(
        EmployeeDepartmentMembership(
            employee_id=employee.id,
            department_id=department.id,
            role="member",
            is_active=True,
        )
    )
    await db_session.flush()
    await db_session.refresh(employee, ["custom_role"])
    return employee


async def _department(db_session: AsyncSession, name: str) -> Department:
    department = Department(name=f"{name} {uuid.uuid4().hex[:8]}")
    db_session.add(department)
    await db_session.flush()
    return department


async def _project_with_states(
    db_session: AsyncSession,
    *,
    department_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> tuple[TaskProject, TaskState, TaskState, TaskState]:
    project = TaskProject(
        name=f"Dashboard Project {uuid.uuid4().hex[:6]}",
        identifier=f"AD{uuid.uuid4().hex[:6].upper()}",
        department_id=department_id,
        workspace_id=workspace_id,
        allow_any_employee=True,
    )
    db_session.add(project)
    await db_session.flush()

    todo = TaskState(
        task_project_id=project.id,
        name="Todo",
        group="todo",
        position=0,
        is_default=True,
        aging_warn_days=3,
    )
    doing = TaskState(
        task_project_id=project.id,
        name="Doing",
        group="in_progress",
        position=1000,
        is_default=False,
        aging_warn_days=2,
    )
    done = TaskState(
        task_project_id=project.id,
        name="Done",
        group="done",
        position=2000,
        is_default=False,
    )
    db_session.add_all([todo, doing, done])
    await db_session.flush()
    return project, todo, doing, done


async def _set_timestamps(
    db_session: AsyncSession,
    task_id: uuid.UUID,
    *,
    created_at: datetime,
    updated_at: datetime,
) -> None:
    await db_session.execute(
        text(
            """
            UPDATE tasks
            SET created_at = :created_at, updated_at = :updated_at
            WHERE id = :task_id
            """
        ),
        {"task_id": task_id, "created_at": created_at, "updated_at": updated_at},
    )
    await db_session.flush()


@pytest_asyncio.fixture
async def dashboard_seed(
    db_session: AsyncSession,
) -> tuple[Employee, TaskProject, TaskProject, TaskProject]:
    visible_department = await _department(db_session, "Visible Dept")
    hidden_department = await _department(db_session, "Hidden Dept")
    user = await _employee(
        db_session,
        department=visible_department,
        role_name="Dashboard User",
        permissions=["task:read:own_dept"],
    )

    visible_project, _todo, doing, done = await _project_with_states(
        db_session,
        department_id=visible_department.id,
    )
    hidden_project, _hidden_todo, hidden_doing, hidden_done = await _project_with_states(
        db_session,
        department_id=hidden_department.id,
    )

    workspace = Project(name=f"Dashboard Workspace {uuid.uuid4().hex[:6]}")
    db_session.add(workspace)
    await db_session.flush()
    db_session.add(ProjectMember(project_id=workspace.id, employee_id=user.id))
    workspace_project, _workspace_todo, workspace_doing, _workspace_done = (
        await _project_with_states(db_session, workspace_id=workspace.id)
    )

    now = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    visible_blocked = Task(
        task_project_id=visible_project.id,
        state_id=doing.id,
        title="Visible blocked aged",
        priority="high",
        blocked_reason="Waiting for approval",
    )
    visible_done = Task(
        task_project_id=visible_project.id,
        state_id=done.id,
        title="Visible done",
        priority="none",
    )
    hidden_open = Task(
        task_project_id=hidden_project.id,
        state_id=hidden_doing.id,
        title="Hidden open",
        priority="none",
        blocked_reason="Hidden blocker",
    )
    hidden_done_task = Task(
        task_project_id=hidden_project.id,
        state_id=hidden_done.id,
        title="Hidden done",
        priority="none",
    )
    workspace_open = Task(
        task_project_id=workspace_project.id,
        state_id=workspace_doing.id,
        title="Workspace open",
        priority="none",
    )
    db_session.add_all(
        [visible_blocked, visible_done, hidden_open, hidden_done_task, workspace_open]
    )
    await db_session.flush()

    await _set_timestamps(
        db_session,
        visible_blocked.id,
        created_at=now - timedelta(days=7),
        updated_at=now - timedelta(days=4),
    )
    await _set_timestamps(
        db_session,
        visible_done.id,
        created_at=now - timedelta(days=4),
        updated_at=now,
    )
    await _set_timestamps(
        db_session,
        hidden_open.id,
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=5),
    )
    await _set_timestamps(
        db_session,
        hidden_done_task.id,
        created_at=now - timedelta(days=2),
        updated_at=now,
    )
    await _set_timestamps(
        db_session,
        workspace_open.id,
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    return user, visible_project, hidden_project, workspace_project


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession,
    dashboard_seed: tuple[Employee, TaskProject, TaskProject, TaskProject],
) -> AsyncIterator[httpx.AsyncClient]:
    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    user, _visible_project, _hidden_project, _workspace_project = dashboard_seed

    async def _db_override():
        yield db_session

    async def _user_override():
        return user

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


async def test_flow_summary_scopes_to_readable_projects(
    api_client: httpx.AsyncClient,
    dashboard_seed: tuple[Employee, TaskProject, TaskProject, TaskProject],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)
    _user, visible_project, hidden_project, workspace_project = dashboard_seed

    response = await api_client.get(
        "/api/admin/dashboard/flow-summary",
        params={"start_date": "2026-05-18", "end_date": "2026-05-18"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["feature_enabled"] is True
    assert payload["scoped_project_count"] == 2
    assert payload["wip_count"] == 2
    assert payload["blocked_count"] == 1
    assert payload["aging_count"] == 1
    assert payload["throughput_count"] == 1
    assert payload["lead_time_p50"] == 4.0
    assert payload["cycle_time_p50"] == 4.0
    assert payload["approximation_used"] is True

    hidden_response = await api_client.get(
        "/api/admin/dashboard/flow-summary",
        params={
            "start_date": "2026-05-18",
            "end_date": "2026-05-18",
            "project_id": str(hidden_project.id),
        },
    )
    assert hidden_response.status_code == 200, hidden_response.text
    assert hidden_response.json()["scoped_project_count"] == 0
    assert hidden_response.json()["wip_count"] == 0

    visible_response = await api_client.get(
        "/api/admin/dashboard/flow-summary",
        params={
            "start_date": "2026-05-18",
            "end_date": "2026-05-18",
            "project_id": str(visible_project.id),
        },
    )
    assert visible_response.status_code == 200, visible_response.text
    assert visible_response.json()["scoped_project_count"] == 1
    assert visible_response.json()["wip_count"] == 1

    workspace_response = await api_client.get(
        "/api/admin/dashboard/flow-summary",
        params={
            "start_date": "2026-05-18",
            "end_date": "2026-05-18",
            "project_id": str(workspace_project.id),
        },
    )
    assert workspace_response.status_code == 200, workspace_response.text
    assert workspace_response.json()["scoped_project_count"] == 1
    assert workspace_response.json()["wip_count"] == 1


async def test_flow_summary_feature_flag_off_skips_database_work(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", False)
    query_count = 0
    bind = db_session.get_bind()

    def _count_query(*_args, **_kwargs) -> None:
        nonlocal query_count
        query_count += 1

    event.listen(bind, "before_cursor_execute", _count_query)
    try:
        response = await api_client.get(
            "/api/admin/dashboard/flow-summary",
            params={"start_date": "2026-05-18", "end_date": "2026-05-18"},
        )
    finally:
        event.remove(bind, "before_cursor_execute", _count_query)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["feature_enabled"] is False
    assert payload["scoped_project_count"] == 0
    assert query_count == 0


async def test_flow_summary_query_count_is_bounded(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)
    statements: list[str] = []
    bind = db_session.get_bind()

    def _count_query(_conn, _cursor, statement, *_args, **_kwargs) -> None:
        statements.append(statement)

    event.listen(bind, "before_cursor_execute", _count_query)
    try:
        response = await api_client.get(
            "/api/admin/dashboard/flow-summary",
            params={"start_date": "2026-05-18", "end_date": "2026-05-18"},
        )
    finally:
        event.remove(bind, "before_cursor_execute", _count_query)

    assert response.status_code == 200, response.text
    assert len(statements) <= 6
