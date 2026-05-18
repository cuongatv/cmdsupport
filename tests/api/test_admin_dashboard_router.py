"""API coverage for the admin Agile dashboard flow summary."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
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
from app.main import app
from app.services.auth_service import create_access_token

pytestmark = pytest.mark.asyncio

QUERY_DAY = date(2026, 5, 18)
QUERY_NOW = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async def _db_override():
        yield db_session

    app.dependency_overrides[get_db] = _db_override

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        try:
            yield client
        finally:
            app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def dashboard_seed(db_session: AsyncSession) -> SimpleNamespace:
    async def _department(name: str) -> Department:
        dept = Department(name=f"{name} {uuid.uuid4().hex[:8]}")
        db_session.add(dept)
        await db_session.flush()
        return dept

    async def _role(name: str, permissions: list[str]) -> Role:
        role = Role(
            name=f"{name}-{uuid.uuid4().hex[:8]}",
            permissions=permissions,
            is_system=False,
        )
        db_session.add(role)
        await db_session.flush()
        return role

    async def _employee(
        *,
        name: str,
        department: Department,
        role: str,
        custom_role: Role | None = None,
    ) -> Employee:
        employee = Employee(
            name=name,
            email=f"{uuid.uuid4().hex[:12]}@dashboard.test",
            role=role,
            department_id=department.id,
            custom_role_id=custom_role.id if custom_role else None,
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
        return employee

    async def _project_with_states(
        *,
        workspace_name: str,
        member: Employee,
    ) -> tuple[TaskProject, TaskState, TaskState, TaskState]:
        workspace = Project(name=f"{workspace_name} {uuid.uuid4().hex[:8]}")
        db_session.add(workspace)
        await db_session.flush()
        db_session.add(ProjectMember(project_id=workspace.id, employee_id=member.id))
        await db_session.flush()

        project = TaskProject(
            name=f"{workspace_name} Tasks",
            identifier=f"{uuid.uuid4().hex[:8].upper()}",
            workspace_id=workspace.id,
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
            aging_warn_days=5,
        )
        doing = TaskState(
            task_project_id=project.id,
            name="Doing",
            group="in_progress",
            position=1000.0,
            aging_warn_days=2,
        )
        done = TaskState(
            task_project_id=project.id,
            name="Done",
            group="done",
            position=2000.0,
            is_default=False,
        )
        db_session.add_all([todo, doing, done])
        await db_session.flush()
        return project, todo, doing, done

    async def _set_task_times(
        task_id: uuid.UUID,
        *,
        created_at: datetime,
        updated_at: datetime,
    ) -> None:
        await db_session.execute(
            text(
                """
                UPDATE tasks
                SET created_at = :created_at,
                    updated_at = :updated_at
                WHERE id = :task_id
                """
            ),
            {
                "task_id": task_id,
                "created_at": created_at,
                "updated_at": updated_at,
            },
        )
        await db_session.flush()

    admin_department = await _department("Admin Dept")
    scoped_department = await _department("Scoped Dept")
    idle_department = await _department("Idle Dept")

    admin_user = await _employee(
        name="Admin User",
        department=admin_department,
        role="admin",
    )
    own_dept_role = await _role("Task Reader", ["task:read:own_dept"])
    scoped_user = await _employee(
        name="Scoped User",
        department=scoped_department,
        role="employee",
        custom_role=own_dept_role,
    )
    no_access_user = await _employee(
        name="No Access User",
        department=idle_department,
        role="employee",
        custom_role=own_dept_role,
    )

    admin_project, admin_todo, admin_doing, admin_done = await _project_with_states(
        workspace_name="Admin Workspace",
        member=admin_user,
    )
    scoped_project, scoped_todo, scoped_doing, scoped_done = await _project_with_states(
        workspace_name="Scoped Workspace",
        member=scoped_user,
    )

    completed_at = QUERY_NOW

    seeded_tasks: list[Task] = []
    for project, todo_state, doing_state, done_state in [
        (admin_project, admin_todo, admin_doing, admin_done),
        (scoped_project, scoped_todo, scoped_doing, scoped_done),
    ]:
        active_task = Task(
            task_project_id=project.id,
            state_id=todo_state.id,
            title=f"{project.name} Todo",
            priority="medium",
        )
        blocked_task = Task(
            task_project_id=project.id,
            state_id=doing_state.id,
            title=f"{project.name} Blocked",
            priority="high",
            blocked_reason="Waiting on dependency",
        )
        completed_task = Task(
            task_project_id=project.id,
            state_id=done_state.id,
            title=f"{project.name} Done",
            priority="low",
        )
        db_session.add_all([active_task, blocked_task, completed_task])
        await db_session.flush()
        seeded_tasks.extend([active_task, blocked_task, completed_task])

        await _set_task_times(
            active_task.id,
            created_at=QUERY_NOW - timedelta(days=1),
            updated_at=QUERY_NOW - timedelta(hours=1),
        )
        await _set_task_times(
            blocked_task.id,
            created_at=QUERY_NOW - timedelta(days=6),
            updated_at=QUERY_NOW - timedelta(days=4),
        )
        await _set_task_times(
            completed_task.id,
            created_at=completed_at - timedelta(days=3),
            updated_at=completed_at,
        )

    await db_session.flush()
    return SimpleNamespace(
        admin=admin_user,
        scoped=scoped_user,
        no_access=no_access_user,
        admin_project=admin_project,
        scoped_project=scoped_project,
        tasks=seeded_tasks,
    )


@pytest.fixture
def auth_headers_factory():
    def _make(employee: Employee) -> dict[str, str]:
        token = create_access_token(
            employee_id=str(employee.id),
            role=employee.role,
            name=employee.name,
        )
        return {"Authorization": f"Bearer {token}"}

    return _make


async def _flow_summary(
    client: httpx.AsyncClient,
    headers: dict[str, str],
    **params: str,
) -> httpx.Response:
    query = {
        "start_date": QUERY_DAY.isoformat(),
        "end_date": QUERY_DAY.isoformat(),
        **params,
    }
    return await client.get(
        "/api/admin/dashboard/flow-summary",
        headers=headers,
        params=query,
    )


async def test_flow_summary_happy_path(
    api_client: httpx.AsyncClient,
    dashboard_seed: SimpleNamespace,
    auth_headers_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)

    response = await _flow_summary(
        api_client,
        auth_headers_factory(dashboard_seed.admin),
        project_id=str(dashboard_seed.admin_project.id),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["feature_enabled"] is True
    assert payload["scoped_project_count"] == 1
    assert payload["wip_count"] == 2
    assert payload["blocked_count"] == 1
    assert payload["aging_count"] == 1
    assert payload["throughput_count"] == 1
    assert payload["cycle_time_p50"] > 0
    assert payload["lead_time_p50"] > 0
    assert payload["approximation_used"] in {True, False}
    assert {
        "feature_enabled",
        "as_of",
        "approximation_used",
        "scoped_project_count",
        "wip_count",
        "blocked_count",
        "aging_count",
        "throughput_count",
        "cycle_time_p50",
        "lead_time_p50",
        "chart_series",
        "risk_items",
        "capacity_items",
    } <= payload.keys()


async def test_flow_summary_feature_flag_off_returns_disabled_payload(
    api_client: httpx.AsyncClient,
    dashboard_seed: SimpleNamespace,
    auth_headers_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", False)

    response = await _flow_summary(api_client, auth_headers_factory(dashboard_seed.admin))

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["feature_enabled"] is False
    assert payload["scoped_project_count"] == 0
    assert payload["wip_count"] == 0
    assert payload["blocked_count"] == 0
    assert payload["aging_count"] == 0
    assert payload["throughput_count"] == 0
    assert payload["cycle_time_p50"] == 0.0
    assert payload["lead_time_p50"] == 0.0
    assert payload["approximation_used"] is False


async def test_flow_summary_rbac_scoping(
    api_client: httpx.AsyncClient,
    dashboard_seed: SimpleNamespace,
    auth_headers_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)

    admin_response = await _flow_summary(
        api_client,
        auth_headers_factory(dashboard_seed.admin),
    )
    scoped_response = await _flow_summary(
        api_client,
        auth_headers_factory(dashboard_seed.scoped),
    )

    assert admin_response.status_code == 200, admin_response.text
    assert scoped_response.status_code == 200, scoped_response.text

    admin_payload = admin_response.json()
    scoped_payload = scoped_response.json()

    assert admin_payload["feature_enabled"] is True
    assert scoped_payload["feature_enabled"] is True
    assert scoped_payload["scoped_project_count"] == 1
    assert admin_payload["scoped_project_count"] > scoped_payload["scoped_project_count"]
    assert admin_payload["scoped_project_count"] != scoped_payload["scoped_project_count"]
    assert admin_payload["wip_count"] >= scoped_payload["wip_count"]
    assert admin_payload["blocked_count"] >= scoped_payload["blocked_count"]
    assert admin_payload["throughput_count"] >= scoped_payload["throughput_count"]


async def test_flow_summary_no_access_returns_empty_but_200(
    api_client: httpx.AsyncClient,
    dashboard_seed: SimpleNamespace,
    auth_headers_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_5", True)

    response = await _flow_summary(
        api_client,
        auth_headers_factory(dashboard_seed.no_access),
        project_id=str(dashboard_seed.admin_project.id),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["feature_enabled"] is True
    assert payload["scoped_project_count"] == 0
    assert payload["wip_count"] == 0
    assert payload["blocked_count"] == 0
    assert payload["aging_count"] == 0
    assert payload["throughput_count"] == 0
    assert payload["cycle_time_p50"] == 0.0
    assert payload["lead_time_p50"] == 0.0
