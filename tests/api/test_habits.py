"""
API tests for the ``/api/me/*`` personal workspace endpoints (T12).

Strategy
--------
These tests run in-process via ``httpx.AsyncClient(transport=ASGITransport(app))``
against the FastAPI app. ``get_db`` is overridden to yield the shared
``db_session`` rollback fixture so every endpoint actually exercises
``app.services.habit_service`` and ``task_dashboard_service`` against
PostgreSQL — but the outer transaction is rolled back on teardown, so the
database is left untouched between tests. ``get_current_user`` is overridden
to return a synthetic ``Employee`` row created on the same rollback session.

If PostgreSQL is unreachable the ``db_session`` fixture in
``tests/conftest.py`` calls ``pytest.skip(...)``, so the whole module skips
cleanly on a fresh checkout.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Employee, EmployeeDepartmentMembership

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures — synthetic actor + ASGI client wired to the rollback session
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_employee(db_session: AsyncSession) -> Employee:
    """Insert one ``Employee`` row on the rollback session and return it.

    Each test gets its own department + employee. The outer transaction in
    ``db_session`` rolls everything back on teardown so the row never
    persists.
    """
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": department_id, "name": f"Habit Test Dept {department_id.hex[:8]}"},
    )
    employee_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, username, role, department_id, is_active)
            VALUES (:id, :name, :email, :username, :role, :department_id, true)
            """
        ),
        {
            "id": employee_id,
            "name": "Habit Test Employee",
            "email": f"{employee_id.hex[:12]}@example.test",
            "username": f"habit_{employee_id.hex[:12]}",
            "role": "employee",
            "department_id": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    test_employee: Employee,
) -> AsyncIterator[httpx.AsyncClient]:
    """ASGI client with ``get_db`` and ``get_current_user`` overridden.

    The same ``db_session`` is yielded for every request so the test can
    assert against rows the endpoints just wrote. The overrides are popped on
    teardown so they do not leak into the next test.
    """
    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    async def _db_override():
        yield db_session

    async def _user_override():
        return test_employee

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = _user_override

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as ac:
        try:
            yield ac
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# POST /api/me/habits — create
# ---------------------------------------------------------------------------


async def test_create_habit_returns_201_with_owner_set(
    client: httpx.AsyncClient,
    test_employee: Employee,
):
    """``POST /api/me/habits`` should persist a habit owned by the caller."""
    body = {
        "title": "Morning Run",
        "priority": "medium",
        "preferred_time": "07:00:00",
        "duration_minutes": 30,
        "active_days": [0, 1, 2, 3, 4],
        "is_active": True,
    }
    resp = await client.post("/api/me/habits", json=body)

    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert payload["title"] == "Morning Run"
    assert payload["priority"] == "medium"
    assert payload["preferred_time"] == "07:00:00"
    assert payload["duration_minutes"] == 30
    assert payload["active_days"] == [0, 1, 2, 3, 4]
    assert payload["is_active"] is True
    assert payload["owner_employee_id"] == str(test_employee.id)
    assert "id" in payload
    assert "created_at" in payload


# ---------------------------------------------------------------------------
# GET /api/me/habits — list
# ---------------------------------------------------------------------------


async def test_list_habits_returns_only_owner_rows_and_excludes_inactive(
    client: httpx.AsyncClient,
    test_employee: Employee,
    personal_habit_factory,
):
    """``GET /api/me/habits`` returns only the caller's active habits by default."""
    await personal_habit_factory(test_employee.id, title="Habit Alpha")
    await personal_habit_factory(test_employee.id, title="Habit Beta")
    # Inactive habit must be hidden by the default filter.
    await personal_habit_factory(
        test_employee.id, title="Habit Gamma (inactive)", is_active=False
    )

    resp = await client.get("/api/me/habits")

    assert resp.status_code == 200, resp.text
    titles = {row["title"] for row in resp.json()}
    assert "Habit Alpha" in titles
    assert "Habit Beta" in titles
    assert "Habit Gamma (inactive)" not in titles


# ---------------------------------------------------------------------------
# POST /api/me/habits/{id}/occurrences/{date} — upsert
# ---------------------------------------------------------------------------


async def test_habit_occurrence_upsert_inserts_then_updates(
    client: httpx.AsyncClient,
    test_employee: Employee,
    personal_habit_factory,
):
    """First call inserts, second call updates the same row."""
    habit = await personal_habit_factory(test_employee.id)
    occurrence_date = date(2026, 5, 14)
    path = f"/api/me/habits/{habit.id}/occurrences/{occurrence_date.isoformat()}"

    # First call: completed.
    first = await client.post(path, json={"state": "completed"})
    assert first.status_code == 200, first.text
    first_payload = first.json()
    assert first_payload["state"] == "completed"
    assert first_payload["habit_id"] == str(habit.id)
    row_id = first_payload["id"]

    # Second call: same (habit, date) — must update the existing row, not insert.
    second = await client.post(
        path,
        json={
            "state": "shifted",
            "actual_start": "08:30:00",
            "shift_reason": "early meeting",
        },
    )
    assert second.status_code == 200, second.text
    second_payload = second.json()
    assert second_payload["id"] == row_id  # same row, mutated
    assert second_payload["state"] == "shifted"
    assert second_payload["actual_start"] == "08:30:00"
    assert second_payload["shift_reason"] == "early meeting"


# ---------------------------------------------------------------------------
# Security — cross-user habit access must not leak resource existence
# ---------------------------------------------------------------------------


async def _insert_employee_for_security_test(
    db_session: AsyncSession,
    *,
    department_id: uuid.UUID | None = None,
    name: str = "Security Employee",
) -> Employee:
    if department_id is None:
        department_id = uuid.uuid4()
        await db_session.execute(
            text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
            {
                "id": department_id,
                "name": f"Security Dept {department_id.hex[:8]}",
            },
        )

    employee_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, username, role, department_id, is_active)
            VALUES (:id, :name, :email, :username, :role, :department_id, true)
            """
        ),
        {
            "id": employee_id,
            "name": f"{name} {employee_id.hex[:6]}",
            "email": f"{employee_id.hex[:12]}@example.test",
            "username": f"sec_{employee_id.hex[:12]}",
            "role": "employee",
            "department_id": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


async def test_cross_user_habit_get_patch_delete_return_404(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    personal_habit_factory,
):
    """User B cannot read, mutate, or archive user A's habit."""
    owner = await _insert_employee_for_security_test(db_session)
    habit = await personal_habit_factory(owner.id, title="Private habit")

    get_resp = await client.get(f"/api/me/habits/{habit.id}")
    patch_resp = await client.patch(
        f"/api/me/habits/{habit.id}",
        json={"title": "Stolen title"},
    )
    delete_resp = await client.delete(f"/api/me/habits/{habit.id}")

    assert get_resp.status_code == 404, get_resp.text
    assert patch_resp.status_code == 404, patch_resp.text
    assert delete_resp.status_code == 404, delete_resp.text
    await db_session.refresh(habit)
    assert habit.title == "Private habit"
    assert habit.is_active is True


async def test_cross_user_occurrence_upsert_returns_404(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    personal_habit_factory,
):
    """User B cannot write occurrence state for user A's habit."""
    owner = await _insert_employee_for_security_test(db_session)
    habit = await personal_habit_factory(owner.id, title="Private occurrence habit")
    occurrence_date = date(2026, 5, 14)

    resp = await client.post(
        f"/api/me/habits/{habit.id}/occurrences/{occurrence_date.isoformat()}",
        json={"state": "completed"},
    )

    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# GET /api/me/tasks — paginated assignee list
# ---------------------------------------------------------------------------


async def test_get_my_tasks_returns_paginated_shape_for_empty_assignment(
    client: httpx.AsyncClient,
):
    """An assignee with no tasks gets an empty page-1 envelope, not an error."""
    resp = await client.get("/api/me/tasks")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["items"] == []
    assert payload["total"] == 0
    assert payload["page"] == 1
    assert payload["page_size"] == 50
    assert payload["total_pages"] == 0


# ---------------------------------------------------------------------------
# GET /api/me/dashboard — buckets + units
# ---------------------------------------------------------------------------


async def test_get_dashboard_returns_zero_buckets_for_new_user(
    client: httpx.AsyncClient,
):
    """``GET /api/me/dashboard`` returns the personal + units shape for a fresh user.

    Lazy-creates the canonical personal ``TaskProject`` on first call, so the
    response always carries a populated ``personal`` bucket (zeros for a new
    user) plus zero or more ``units`` aggregates. Validates the response
    *shape* and zero-state semantics — counts are exercised in the per-task
    dashboard tests.
    """
    resp = await client.get("/api/me/dashboard")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert set(payload.keys()) == {"personal", "units", "due_soon_days"}
    assert payload["due_soon_days"] == 7

    personal = payload["personal"]
    assert set(personal.keys()) == {"total", "not_due_yet", "due_soon", "overdue"}
    # New user → all bucket counts are zero.
    assert personal["total"] == 0
    assert personal["not_due_yet"] == 0
    assert personal["due_soon"] == 0
    assert personal["overdue"] == 0
    assert isinstance(payload["units"], list)


# ---------------------------------------------------------------------------
# GET /api/me/units — standalone unit switcher
# ---------------------------------------------------------------------------


async def test_list_my_units_includes_legacy_primary_department(
    client: httpx.AsyncClient,
    test_employee: Employee,
):
    """``GET /api/me/units`` includes the legacy primary department fallback.

    The synthetic ``Employee`` in ``test_employee`` has a ``department_id``
    column value but NO row in ``employee_department_memberships``. The /me
    department guards also honor that legacy pointer, so the unit switcher must
    surface the same department instead of making the frontend inconsistent with
    calendar access.
    """
    resp = await client.get("/api/me/units")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert len(payload) == 1
    assert payload[0]["unit_id"] == str(test_employee.department_id)


# ---------------------------------------------------------------------------
# GET /api/me/calendar — scope=department requires dept_id (T9 verification)
# ---------------------------------------------------------------------------


async def test_calendar_department_scope_requires_dept_id(
    client: httpx.AsyncClient,
):
    """``scope=department`` without ``dept_id`` must return 400, not 500."""
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()
    resp = await client.get(
        "/api/me/calendar",
        params={"week_start": week_start, "scope": "department"},
    )
    assert resp.status_code == 400, resp.text
    assert "dept_id" in resp.json()["detail"]


async def test_calendar_department_scope_requires_membership(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """A non-member cannot request another department's calendar."""
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {
            "id": department_id,
            "name": f"Calendar Security Dept {department_id.hex[:8]}",
        },
    )
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()

    resp = await client.get(
        "/api/me/calendar",
        params={
            "week_start": week_start,
            "scope": "department",
            "dept_id": str(department_id),
        },
    )

    assert resp.status_code == 403, resp.text


async def test_calendar_department_scope_allows_active_membership(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    test_employee: Employee,
):
    """Positive control: active membership is enough for department calendar."""
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {
            "id": department_id,
            "name": f"Calendar Member Dept {department_id.hex[:8]}",
        },
    )
    db_session.add(
        EmployeeDepartmentMembership(
            employee_id=test_employee.id,
            department_id=department_id,
            role="viewer",
            is_active=True,
        )
    )
    await db_session.flush()
    week_start = (date.today() - timedelta(days=date.today().weekday())).isoformat()

    resp = await client.get(
        "/api/me/calendar",
        params={
            "week_start": week_start,
            "scope": "department",
            "dept_id": str(department_id),
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["scope"] == "department"


# ---------------------------------------------------------------------------
# GET /api/me/calendar?scope=personal — assignee-based, not project-based
# ---------------------------------------------------------------------------


async def test_calendar_personal_scope_includes_squad_team_task_assigned_to_user(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    test_employee: Employee,
):
    """Regression: a task created in a Squad Team (department-scoped TaskProject)
    and assigned to the user must appear in their personal calendar.

    Earlier code filtered ``scope=personal`` to ``Task.task_project_id ==
    personal_project_id`` which hid every department / workspace task the user
    was assigned to. The personal calendar is supposed to be "every task I am
    on this week" regardless of which project owns it — matching the
    ``/api/me/tasks`` list endpoint's TaskAssignee join.
    """
    from datetime import datetime, time, timezone

    from app.database.models import (
        Task,
        TaskAssignee,
        TaskProject,
        TaskState,
    )

    # Squad Team = a department-scoped TaskProject.
    squad_dept_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": squad_dept_id, "name": f"Squad Team {squad_dept_id.hex[:8]}"},
    )
    squad_project = TaskProject(
        id=uuid.uuid4(),
        name="Squad Backlog",
        identifier="SQUAD",
        department_id=squad_dept_id,
    )
    db_session.add(squad_project)
    await db_session.flush()
    state = TaskState(
        id=uuid.uuid4(),
        task_project_id=squad_project.id,
        name="Todo",
        group="todo",
        position=1.0,
        is_default=True,
    )
    db_session.add(state)
    await db_session.flush()

    # Pick a due_date inside the current week (Mon..Sun) so the calendar
    # window surfaces it via the due_inside_window branch.
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    due_at = datetime.combine(week_start, time(9, 0), tzinfo=timezone.utc)
    task = Task(
        id=uuid.uuid4(),
        task_project_id=squad_project.id,
        state_id=state.id,
        title="Squad task assigned to user",
        priority="medium",
        position=1000.0,
        version=1,
        due_date=due_at,
    )
    db_session.add(task)
    await db_session.flush()
    db_session.add(TaskAssignee(task_id=task.id, employee_id=test_employee.id))
    await db_session.flush()

    resp = await client.get(
        "/api/me/calendar",
        params={"week_start": week_start.isoformat(), "scope": "personal"},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    task_ids = {
        ev["task_id"]
        for ev in payload["events"]
        if ev.get("event_type") == "task"
    }
    assert str(task.id) in task_ids, (
        "Squad Team task assigned to the user must appear in personal calendar"
    )


async def test_calendar_personal_scope_excludes_task_not_assigned_to_user(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    test_employee: Employee,
):
    """Negative control: a department task the user is NOT assigned to must
    stay out of their personal calendar — assignee filter is the only
    inclusion path for ``scope=personal``.
    """
    from datetime import datetime, time, timezone

    from app.database.models import Task, TaskProject, TaskState

    other_dept_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": other_dept_id, "name": f"Other Dept {other_dept_id.hex[:8]}"},
    )
    other_project = TaskProject(
        id=uuid.uuid4(),
        name="Other Backlog",
        identifier="OTHR",
        department_id=other_dept_id,
    )
    db_session.add(other_project)
    await db_session.flush()
    state = TaskState(
        id=uuid.uuid4(),
        task_project_id=other_project.id,
        name="Todo",
        group="todo",
        position=1.0,
        is_default=True,
    )
    db_session.add(state)
    await db_session.flush()

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    due_at = datetime.combine(week_start, time(10, 0), tzinfo=timezone.utc)
    other_task = Task(
        id=uuid.uuid4(),
        task_project_id=other_project.id,
        state_id=state.id,
        title="Task NOT assigned to user",
        priority="medium",
        position=1000.0,
        version=1,
        due_date=due_at,
    )
    db_session.add(other_task)
    await db_session.flush()

    resp = await client.get(
        "/api/me/calendar",
        params={"week_start": week_start.isoformat(), "scope": "personal"},
    )
    assert resp.status_code == 200, resp.text
    task_ids = {
        ev["task_id"]
        for ev in resp.json()["events"]
        if ev.get("event_type") == "task"
    }
    assert str(other_task.id) not in task_ids
