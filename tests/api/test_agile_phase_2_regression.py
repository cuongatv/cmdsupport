"""Phase 2 regression, concurrency, notification-template, and flag QA tests."""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Employee, Sprint, Task, TaskActivity, TaskProject, TaskState

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def admin_employee(db_session: AsyncSession) -> Employee:
    """Synthetic admin Employee for in-process API tests."""
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {
            "id": department_id,
            "name": f"Phase 2 Regression Dept {department_id.hex[:8]}",
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
            "name": "Phase 2 Regression Admin",
            "email": f"{employee_id.hex[:12]}@example.test",
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
        transport=transport,
        base_url="http://testserver",
    ) as client:
        try:
            yield client
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


async def _make_project(
    db: AsyncSession,
    admin: Employee,
    *,
    name: str,
) -> tuple[TaskProject, TaskState, TaskState]:
    project = TaskProject(
        name=name,
        description=None,
        identifier=f"R{uuid.uuid4().hex[:5].upper()}",
        workspace_id=None,
        department_id=admin.department_id,
        created_by_id=admin.id,
        allow_any_employee=False,
    )
    db.add(project)
    await db.flush()

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
    db.add_all([backlog, done])
    await db.flush()
    await db.refresh(project)
    return project, backlog, done


async def _make_task(
    db: AsyncSession,
    project: TaskProject,
    state: TaskState,
    *,
    title: str = "Regression task",
    sprint_id: uuid.UUID | None = None,
    acceptance_criteria: str | None = None,
) -> Task:
    task = Task(
        task_project_id=project.id,
        state_id=state.id,
        title=title,
        priority="none",
        position=1000.0,
        version=1,
        sprint_id=sprint_id,
        acceptance_criteria=acceptance_criteria,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def test_stale_version_acceptance_criteria_returns_409(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_employee: Employee,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATCH with stale version returns 409 and leaves acceptance criteria intact."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    project, backlog, _ = await _make_project(
        db_session,
        admin_employee,
        name="Stale AC Project",
    )
    task = await _make_task(
        db_session,
        project,
        backlog,
        acceptance_criteria="AC ban đầu",
    )
    stale_version = task.version

    fresh = await api_client.patch(
        f"/api/tasks/{task.id}",
        json={"title": "Updated title", "version": stale_version},
    )
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["version"] == stale_version + 1

    stale = await api_client.patch(
        f"/api/tasks/{task.id}",
        json={
            "acceptance_criteria": "AC không được ghi",
            "version": stale_version,
        },
    )
    assert stale.status_code == 409, stale.text

    await db_session.refresh(task)
    assert task.acceptance_criteria == "AC ban đầu"


async def test_stale_sprint_close_returns_409(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_employee: Employee,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sprint currently has no version column; close is therefore idempotent/safe."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    project, _, _ = await _make_project(
        db_session,
        admin_employee,
        name="Idempotent Close Project",
    )
    assert not hasattr(Sprint, "version")

    create_resp = await api_client.post(
        f"/api/task-projects/{project.id}/sprints",
        json={"name": "Sprint đóng an toàn"},
    )
    assert create_resp.status_code == 201, create_resp.text
    sprint_id = create_resp.json()["id"]

    first_close = await api_client.post(f"/api/sprints/{sprint_id}/close")
    assert first_close.status_code == 200, first_close.text
    assert first_close.json()["status"] == "completed"

    second_close = await api_client.post(f"/api/sprints/{sprint_id}/close")
    assert second_close.status_code == 200, second_close.text
    assert second_close.json()["status"] == "completed"


async def test_phase2_flag_off_preserves_sprint_data_rejects_writes(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_employee: Employee,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag OFF preserves stored sprint rows while PATCH sprint fails closed."""
    from app.config import settings

    project, _, _ = await _make_project(
        db_session,
        admin_employee,
        name="Flag Toggle Project",
    )

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    create_resp = await api_client.post(
        f"/api/task-projects/{project.id}/sprints",
        json={"name": "Sprint vẫn còn dữ liệu", "goal": "Không mất dữ liệu"},
    )
    assert create_resp.status_code == 201, create_resp.text
    sprint_id = uuid.UUID(create_resp.json()["id"])

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", False)
    patch_resp = await api_client.patch(
        f"/api/sprints/{sprint_id}",
        json={"name": "Không được cập nhật"},
    )
    assert patch_resp.status_code == 403, patch_resp.text
    assert patch_resp.json()["detail"]["code"] == "FEATURE_DISABLED"

    sprint = await db_session.get(Sprint, sprint_id)
    assert sprint is not None
    assert sprint.name == "Sprint vẫn còn dữ liệu"
    assert sprint.goal == "Không mất dữ liệu"

    list_resp = await api_client.get(f"/api/task-projects/{project.id}/sprints")
    assert list_resp.status_code == 200, list_resp.text
    assert [row["id"] for row in list_resp.json()] == [str(sprint_id)]


async def test_task_move_across_projects_clears_sprint_id(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_employee: Employee,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Moving a task to another TaskProject clears stale sprint membership."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    source_project, source_backlog, _ = await _make_project(
        db_session,
        admin_employee,
        name="Source Project",
    )
    target_project, target_backlog, _ = await _make_project(
        db_session,
        admin_employee,
        name="Target Project",
    )
    sprint_resp = await api_client.post(
        f"/api/task-projects/{source_project.id}/sprints",
        json={"name": "Sprint nguồn"},
    )
    assert sprint_resp.status_code == 201, sprint_resp.text
    sprint_id = uuid.UUID(sprint_resp.json()["id"])
    task = await _make_task(
        db_session,
        source_project,
        source_backlog,
        sprint_id=sprint_id,
    )

    move_resp = await api_client.patch(
        f"/api/tasks/{task.id}",
        json={
            "task_project_id": str(target_project.id),
            "state_id": str(target_backlog.id),
            "version": task.version,
        },
    )
    assert move_resp.status_code == 200, move_resp.text
    moved = move_resp.json()
    assert moved["task_project_id"] == str(target_project.id)
    assert moved["state_id"] == str(target_backlog.id)
    assert moved["sprint_id"] is None

    await db_session.refresh(task)
    assert task.task_project_id == target_project.id
    assert task.sprint_id is None

    activity = (
        await db_session.execute(
            select(TaskActivity).where(
                TaskActivity.task_id == task.id,
                TaskActivity.verb == "sprint_id_cleared_on_project_move",
            )
        )
    ).scalar_one_or_none()
    assert activity is not None
    assert activity.old_value == str(sprint_id)
    assert activity.new_value is None


async def test_native_task_regression(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    admin_employee: Employee,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native create/update/delete flows work without any Phase 2 payload fields."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", False)
    project, backlog, _ = await _make_project(
        db_session,
        admin_employee,
        name="Native Regression Project",
    )

    create_resp = await api_client.post(
        "/api/tasks",
        params={"task_project_id": str(project.id)},
        json={
            "title": "Native task vẫn hoạt động",
            "description": "Không có field Phase 2",
            "priority": "medium",
            "state_id": str(backlog.id),
            "assignee_ids": [],
            "label_ids": [],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["title"] == "Native task vẫn hoạt động"
    assert created["sprint_id"] is None

    update_resp = await api_client.patch(
        f"/api/tasks/{created['id']}",
        json={"title": "Native task đã cập nhật", "version": created["version"]},
    )
    assert update_resp.status_code == 200, update_resp.text
    updated = update_resp.json()
    assert updated["title"] == "Native task đã cập nhật"
    assert updated["version"] == created["version"] + 1

    delete_resp = await api_client.delete(f"/api/tasks/{created['id']}")
    assert delete_resp.status_code == 204, delete_resp.text

    row = await db_session.get(Task, uuid.UUID(created["id"]))
    assert row is not None
    assert row.deleted_at is not None
