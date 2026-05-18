"""API tests for the Phase 2 semantics surface (T8).

Mirrors ``tests/api/test_agile_sprint.py`` and ``tests/api/test_agile_phase_1.py``:
in-process ASGI client against the real router + service stack, ``db_session``
rollback fixture for isolation, ``settings.FEATURE_AGILE_PHASE_2`` flipped
per-test via ``monkeypatch``. Synthetic admin actor bypasses
``require_permission`` so the semantics contract is exercised in isolation
from RBAC plumbing.

Covered scenarios (T8 acceptance criteria):

* ``test_block_unblock_task_audit`` — block + unblock transitions stamp
  ``blocked_at`` / ``blocked_by_id`` correctly, emit the right activity
  verbs, and produce an audit log row.
* ``test_dependency_cycle_rejected`` — the recursive-CTE cycle check
  surfaces ``409 BLOCKED_CYCLE`` when a new edge would close a chain.
* ``test_dependency_duplicate_rejected`` — duplicate edges raise
  ``409 DUPLICATE_DEPENDENCY``.
* ``test_update_task_type_enabled`` — Phase 2 fields (``task_type``,
  ``estimate``, ``story_points``) round-trip through update.
* ``test_semantics_disabled_returns_feature_disabled`` — dependency writes
  and Phase 2 field updates fail closed with ``403 FEATURE_DISABLED`` when
  the flag is off; reads stay open.
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
    Task,
    TaskActivity,
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
            "name": f"Phase 2 Sem Dept {department_id.hex[:8]}",
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
            "name": "Phase 2 Sem API Admin",
            "email": f"{employee_id.hex[:12]}@example.test",
            "department_id": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


@pytest_asyncio.fixture
async def task_project_with_tasks(
    db_session: AsyncSession,
    admin_employee: Employee,
) -> tuple[TaskProject, list[Task]]:
    """Department-scoped project with one default state + three tasks.

    The three tasks let us build a dependency chain (A→B→C) so the cycle
    test can attempt to close it with (C→A).
    """
    project = TaskProject(
        name="Phase 2 Semantics Project",
        description=None,
        identifier=f"P2{uuid.uuid4().hex[:5].upper()}",
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

    tasks: list[Task] = []
    for index, title in enumerate(("Task A", "Task B", "Task C")):
        task = Task(
            task_project_id=project.id,
            state_id=backlog.id,
            title=title,
            priority="none",
            position=1000.0 * (index + 1),
        )
        db_session.add(task)
        tasks.append(task)
    await db_session.flush()
    for task in tasks:
        await db_session.refresh(task)
    return project, tasks


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


async def test_block_unblock_task_audit(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    task_project_with_tasks: tuple[TaskProject, list[Task]],
    admin_employee: Employee,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Block + unblock transitions stamp metadata, emit verbs, and audit."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    _, tasks = task_project_with_tasks
    task = tasks[0]
    # The test fixture and the endpoint share the same AsyncSession via the
    # dependency override, so ``task.version`` reflects the latest in-memory
    # value AFTER the PATCH lands. Snapshot the initial version up-front so
    # the post-conditions compare against the original.
    initial_version = task.version

    # --- Block ---
    block_resp = await api_client.patch(
        f"/api/tasks/{task.id}",
        json={
            "blocked_reason": "Đang chờ phê duyệt từ team RnD",
            "version": initial_version,
        },
    )
    assert block_resp.status_code == 200, block_resp.text
    blocked = block_resp.json()
    assert blocked["blocked_reason"] == "Đang chờ phê duyệt từ team RnD"
    assert blocked["blocked_at"] is not None
    assert blocked["blocked_by_id"] == str(admin_employee.id)
    assert blocked["version"] == initial_version + 1

    blocked_activity = (
        await db_session.execute(
            select(TaskActivity).where(
                TaskActivity.task_id == task.id,
                TaskActivity.verb == "task_blocked",
            )
        )
    ).scalar_one_or_none()
    assert blocked_activity is not None
    assert blocked_activity.field_name == "blocked_reason"

    audit_row = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.resource_type == "task",
                AuditLog.resource_id == str(task.id),
                AuditLog.action == "update",
            )
        )
    ).first()
    assert audit_row is not None

    # --- Unblock (explicit None) ---
    await db_session.refresh(task)
    unblock_version = task.version
    unblock_resp = await api_client.patch(
        f"/api/tasks/{task.id}",
        json={"blocked_reason": None, "version": unblock_version},
    )
    assert unblock_resp.status_code == 200, unblock_resp.text
    unblocked = unblock_resp.json()
    assert unblocked["blocked_reason"] is None
    assert unblocked["blocked_at"] is None
    assert unblocked["blocked_by_id"] is None

    unblocked_activity = (
        await db_session.execute(
            select(TaskActivity).where(
                TaskActivity.task_id == task.id,
                TaskActivity.verb == "task_unblocked",
            )
        )
    ).scalar_one_or_none()
    assert unblocked_activity is not None


async def test_dependency_cycle_rejected(
    api_client: httpx.AsyncClient,
    task_project_with_tasks: tuple[TaskProject, list[Task]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A→B + B→C succeeds; C→A closes the cycle and returns 409 BLOCKED_CYCLE."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    _, tasks = task_project_with_tasks
    a, b, c = tasks

    # A depends on B (A is blocked by B).
    r1 = await api_client.post(
        f"/api/tasks/{a.id}/dependencies",
        json={
            "from_task_id": str(a.id),
            "to_task_id": str(b.id),
            "dep_type": "blocks",
        },
    )
    assert r1.status_code == 201, r1.text

    # B depends on C.
    r2 = await api_client.post(
        f"/api/tasks/{b.id}/dependencies",
        json={
            "from_task_id": str(b.id),
            "to_task_id": str(c.id),
            "dep_type": "blocks",
        },
    )
    assert r2.status_code == 201, r2.text

    # C depends on A → would close A→B→C→A. Reject.
    r3 = await api_client.post(
        f"/api/tasks/{c.id}/dependencies",
        json={
            "from_task_id": str(c.id),
            "to_task_id": str(a.id),
            "dep_type": "blocks",
        },
    )
    assert r3.status_code == 409, r3.text
    assert r3.json()["detail"]["code"] == "BLOCKED_CYCLE"


async def test_dependency_duplicate_rejected(
    api_client: httpx.AsyncClient,
    task_project_with_tasks: tuple[TaskProject, list[Task]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding the same (from, to) pair twice returns 409 DUPLICATE_DEPENDENCY."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    _, tasks = task_project_with_tasks
    a, b, _ = tasks

    body = {
        "from_task_id": str(a.id),
        "to_task_id": str(b.id),
        "dep_type": "blocks",
    }
    r1 = await api_client.post(f"/api/tasks/{a.id}/dependencies", json=body)
    assert r1.status_code == 201, r1.text

    r2 = await api_client.post(f"/api/tasks/{a.id}/dependencies", json=body)
    assert r2.status_code == 409, r2.text
    assert r2.json()["detail"]["code"] == "DUPLICATE_DEPENDENCY"

    # The dep set must contain exactly one row — duplicate insert was a no-op.
    list_resp = await api_client.get(f"/api/tasks/{a.id}/dependencies")
    assert list_resp.status_code == 200, list_resp.text
    assert len(list_resp.json()) == 1


async def test_update_task_type_enabled(
    api_client: httpx.AsyncClient,
    task_project_with_tasks: tuple[TaskProject, list[Task]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With Phase 2 ON, semantics fields round-trip through update."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", True)
    _, tasks = task_project_with_tasks
    task = tasks[0]
    initial_version = task.version

    resp = await api_client.patch(
        f"/api/tasks/{task.id}",
        json={
            "task_type": "story",
            "estimate": "m",
            "story_points": 5,
            "acceptance_criteria": "Người dùng có thể đăng nhập bằng SSO",
            "version": initial_version,
        },
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["task_type"] == "story"
    assert updated["estimate"] == "m"
    assert updated["story_points"] == 5
    assert (
        updated["acceptance_criteria"]
        == "Người dùng có thể đăng nhập bằng SSO"
    )
    assert updated["version"] == initial_version + 1


async def test_semantics_disabled_returns_feature_disabled(
    api_client: httpx.AsyncClient,
    task_project_with_tasks: tuple[TaskProject, list[Task]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With Phase 2 OFF, semantics writes and dep writes fail with 403."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_2", False)
    _, tasks = task_project_with_tasks
    a, b, _ = tasks

    # PATCH carrying a Phase 2 field → 403 FEATURE_DISABLED.
    patch_resp = await api_client.patch(
        f"/api/tasks/{a.id}",
        json={"task_type": "story", "version": a.version},
    )
    assert patch_resp.status_code == 403, patch_resp.text
    assert patch_resp.json()["detail"]["code"] == "FEATURE_DISABLED"

    # POST dependency → 403 FEATURE_DISABLED.
    dep_resp = await api_client.post(
        f"/api/tasks/{a.id}/dependencies",
        json={
            "from_task_id": str(a.id),
            "to_task_id": str(b.id),
            "dep_type": "blocks",
        },
    )
    assert dep_resp.status_code == 403, dep_resp.text
    assert dep_resp.json()["detail"]["code"] == "FEATURE_DISABLED"

    # GET dependencies stays open under the OFF flag (read-only) — confirms
    # the gate is on writes only, matching the documented contract.
    list_resp = await api_client.get(f"/api/tasks/{a.id}/dependencies")
    assert list_resp.status_code == 200, list_resp.text
    assert list_resp.json() == []
