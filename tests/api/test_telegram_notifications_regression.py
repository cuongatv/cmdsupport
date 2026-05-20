# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""Regression: in-app ``Notification`` rows survive the Telegram hook (Task 15).

These tests prove the additive contract — the Telegram task hook does NOT
suppress or alter the existing in-app notification fan-out for plain task
mutations. They exercise the public REST endpoints (NOT the Telegram webhook)
and assert the same ``Notification`` rows that would have been written before
Task 15 still exist after it.

Pattern mirrors :mod:`tests.services.test_task_notifications` but at the
HTTP layer using the in-process ``test_client`` fixture.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Department,
    Employee,
    Notification,
    Task,
    TaskAssignee,
    TaskState,
)
from app.schemas.tasks import TaskProjectCreate
from app.services.task_project_service import create_task_project

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def setup_actors(db_session: AsyncSession):
    """Seed a department + actor (admin) + recipient employee + a TaskProject."""
    department = Department(
        name=f"Regression Notif Dept {uuid.uuid4().hex[:8]}"
    )
    db_session.add(department)
    await db_session.flush()

    def _make(name: str, system_role: str) -> Employee:
        emp = Employee(
            name=name,
            email=f"{uuid.uuid4().hex[:10]}@example.test",
            username=f"reg_{uuid.uuid4().hex[:8]}",
            role=system_role,
            department_id=department.id,
            is_active=True,
        )
        db_session.add(emp)
        return emp

    actor = _make("Regression Actor", "admin")
    recipient = _make("Regression Recipient", "employee")
    await db_session.flush()

    project = await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Regression Notif Project",
            identifier=f"RN{uuid.uuid4().hex[:3].upper()}",
            department_id=department.id,
            allow_any_employee=True,
        ),
        actor,
    )
    await db_session.flush()
    return {
        "department": department,
        "actor": actor,
        "recipient": recipient,
        "project": project,
    }


@pytest_asyncio.fixture
async def actor_client(
    db_session: AsyncSession, setup_actors: dict[str, Any]
) -> AsyncIterator[httpx.AsyncClient]:
    """An in-process HTTP client whose dependencies bind to ``db_session`` and
    return the admin actor for every authenticated request."""
    from httpx import ASGITransport

    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    actor = setup_actors["actor"]

    async def _db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _user_override() -> Employee:
        return actor

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


async def _project_states(
    db_session: AsyncSession, project_id: uuid.UUID
) -> list[TaskState]:
    result = await db_session.execute(
        select(TaskState)
        .where(TaskState.task_project_id == project_id)
        .order_by(TaskState.position)
    )
    return list(result.scalars().all())


async def _state_by_group(
    db_session: AsyncSession, project_id: uuid.UUID, group: str
) -> TaskState:
    states = await _project_states(db_session, project_id)
    matches = [s for s in states if s.group == group]
    assert matches, f"project missing state for group={group!r}"
    return matches[0]


async def test_move_task_via_api_still_creates_state_changed_notification(
    actor_client: httpx.AsyncClient,
    db_session: AsyncSession,
    setup_actors: dict[str, Any],
) -> None:
    """``POST /api/tasks/{id}/move`` must keep producing the in-app
    ``state_changed`` notification per active assignee, exactly as before
    the Telegram hook was added."""
    project = setup_actors["project"]
    recipient: Employee = setup_actors["recipient"]
    todo = await _state_by_group(db_session, project.id, "todo")
    in_progress = await _state_by_group(db_session, project.id, "in_progress")

    create_resp = await actor_client.post(
        "/api/tasks",
        params={"task_project_id": str(project.id)},
        json={
            "title": "Regression move task",
            "priority": "medium",
            "state_id": str(todo.id),
            "assignee_ids": [str(recipient.id)],
            "label_ids": [],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    task_body = create_resp.json()
    task_id = uuid.UUID(task_body["id"])

    # Sanity: the assignment row landed.
    assignee_row = await db_session.scalar(
        select(TaskAssignee).where(
            TaskAssignee.task_id == task_id,
            TaskAssignee.employee_id == recipient.id,
        )
    )
    assert assignee_row is not None

    # Move the task -> triggers synchronous notify_state_changed.
    move_resp = await actor_client.post(
        f"/api/tasks/{task_id}/move",
        json={
            "state_id": str(in_progress.id),
            "position": 1.0,
            "version": task_body["version"],
        },
    )
    assert move_resp.status_code == 200, move_resp.text

    # The recipient must have exactly one state_changed notification for this task.
    notifications = list(
        (
            await db_session.execute(
                select(Notification).where(
                    Notification.task_id == task_id,
                    Notification.recipient_id == recipient.id,
                    Notification.notification_type == "state_changed",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(notifications) == 1
    notification = notifications[0]
    assert notification.is_read is False
    assert notification.read_at is None
    assert notification.title  # title is NOT NULL


async def test_comment_via_api_still_creates_commented_notifications(
    actor_client: httpx.AsyncClient,
    db_session: AsyncSession,
    setup_actors: dict[str, Any],
) -> None:
    """``POST /api/tasks/{id}/comments`` must keep producing the in-app
    ``commented`` notification per active assignee (excluding the comment author)."""
    project = setup_actors["project"]
    recipient: Employee = setup_actors["recipient"]
    todo = await _state_by_group(db_session, project.id, "todo")

    create_resp = await actor_client.post(
        "/api/tasks",
        params={"task_project_id": str(project.id)},
        json={
            "title": "Regression comment task",
            "priority": "medium",
            "state_id": str(todo.id),
            "assignee_ids": [str(recipient.id)],
            "label_ids": [],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    task_id = uuid.UUID(create_resp.json()["id"])

    comment_resp = await actor_client.post(
        f"/api/tasks/{task_id}/comments",
        json={"body": "Regression test: please review"},
    )
    assert comment_resp.status_code == 201, comment_resp.text

    commented_notifications = list(
        (
            await db_session.execute(
                select(Notification).where(
                    Notification.task_id == task_id,
                    Notification.recipient_id == recipient.id,
                    Notification.notification_type == "commented",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(commented_notifications) == 1
    assert commented_notifications[0].is_read is False


async def test_task_lifecycle_via_api_does_not_overproduce_notifications(
    actor_client: httpx.AsyncClient,
    db_session: AsyncSession,
    setup_actors: dict[str, Any],
) -> None:
    """A normal create -> move -> comment sequence must produce ONLY the
    expected in-app notifications for the recipient (no extra side effects
    from the Telegram hook)."""
    project = setup_actors["project"]
    recipient: Employee = setup_actors["recipient"]
    todo = await _state_by_group(db_session, project.id, "todo")
    in_progress = await _state_by_group(db_session, project.id, "in_progress")

    # 1. Create the task.
    create_resp = await actor_client.post(
        "/api/tasks",
        params={"task_project_id": str(project.id)},
        json={
            "title": "Regression lifecycle task",
            "priority": "medium",
            "state_id": str(todo.id),
            "assignee_ids": [str(recipient.id)],
            "label_ids": [],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    task_id = uuid.UUID(create_resp.json()["id"])
    task_version = create_resp.json()["version"]

    # 2. Move it.
    move_resp = await actor_client.post(
        f"/api/tasks/{task_id}/move",
        json={
            "state_id": str(in_progress.id),
            "position": 1.0,
            "version": task_version,
        },
    )
    assert move_resp.status_code == 200, move_resp.text

    # 3. Comment on it.
    comment_resp = await actor_client.post(
        f"/api/tasks/{task_id}/comments",
        json={"body": "Lifecycle comment"},
    )
    assert comment_resp.status_code == 201, comment_resp.text

    # The recipient should see exactly one ``state_changed`` and exactly one
    # ``commented`` notification. Assignment notifications go through arq and
    # are not exercised in-process here. Anything else would mean the Telegram
    # hook was double-firing or rewriting the in-app stream.
    rows_by_type: dict[str, list[Notification]] = {}
    result = await db_session.execute(
        select(Notification).where(
            Notification.task_id == task_id,
            Notification.recipient_id == recipient.id,
        )
    )
    for row in result.scalars().all():
        rows_by_type.setdefault(row.notification_type, []).append(row)

    assert len(rows_by_type.get("state_changed", [])) == 1
    assert len(rows_by_type.get("commented", [])) == 1
    # The Task itself stayed put — Telegram hook never wrote anything to
    # ``Task`` (this would be visible as a stray title rewrite).
    task = await db_session.get(Task, task_id)
    assert task is not None
    assert task.title == "Regression lifecycle task"
