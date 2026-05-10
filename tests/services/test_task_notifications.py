"""Tests for the task notification service."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from app.database.models import Employee, Notification, Task, TaskAssignee
from app.schemas.tasks import TaskCreate, TaskProjectCreate
from app.services.task_notification_service import (
    notify_assigned,
    notify_commented,
    notify_mentioned,
    notify_state_changed,
    scan_due_soon,
)
from app.services.task_project_service import create_task_project
from app.services.task_service import create_task

pytestmark = pytest.mark.asyncio


async def _insert_department(db_session, name: str = "Notif Department") -> uuid.UUID:
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": department_id, "name": f"{name} {department_id.hex[:8]}"},
    )
    return department_id


async def _insert_workspace(db_session, name: str = "Notif Workspace") -> uuid.UUID:
    workspace_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
        {"id": workspace_id, "name": f"{name} {workspace_id.hex[:8]}"},
    )
    return workspace_id


async def _insert_employee(
    db_session,
    *,
    department_id: uuid.UUID | None = None,
    role: str = "employee",
    name: str = "Notif Tester",
    is_active: bool = True,
) -> Employee:
    if department_id is None:
        department_id = await _insert_department(db_session)
    employee_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, role, department_id, is_active)
            VALUES (:id, :name, :email, :role, :department_id, :is_active)
            """
        ),
        {
            "id": employee_id,
            "name": f"{name} {employee_id.hex[:6]}",
            "email": f"{employee_id.hex[:12]}@example.test",
            "role": role,
            "department_id": department_id,
            "is_active": is_active,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


async def _seed_task(
    db_session,
    *,
    due_date: datetime | None = None,
    title: str = "Notifiable Task",
) -> tuple[Task, Employee]:
    workspace_id = await _insert_workspace(db_session)
    actor = await _insert_employee(db_session)
    project = await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Notif Project",
            identifier=f"NT{workspace_id.hex[:4].upper()}",
            workspace_id=workspace_id,
        ),
        actor,
    )
    state = sorted(project.states, key=lambda item: item.position)[0]
    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title=title, state_id=state.id, due_date=due_date),
        actor,
    )
    return task, actor


async def _notifs_for_task(db_session, task_id: uuid.UUID) -> list[Notification]:
    result = await db_session.execute(
        select(Notification).where(Notification.task_id == task_id)
    )
    return list(result.scalars().all())


async def test_notify_assigned_creates_unread_notifications(db_session):
    task, _actor = await _seed_task(db_session, title="Snapshot Title")
    alice = await _insert_employee(db_session, name="Alice")
    bob = await _insert_employee(db_session, name="Bob")

    notifications = await notify_assigned(db_session, task, [alice.id, bob.id])

    assert {n.recipient_id for n in notifications} == {alice.id, bob.id}
    assert all(n.notification_type == "assigned" for n in notifications)
    assert all(n.is_read is False for n in notifications)
    assert all(n.read_at is None for n in notifications)
    assert all(n.task_id == task.id for n in notifications)
    # Title snapshot survives task deletion
    assert all(n.title == "Snapshot Title" for n in notifications)


async def test_notify_assigned_skips_inactive_assignee(db_session):
    task, _actor = await _seed_task(db_session)
    active = await _insert_employee(db_session, name="ActiveAssignee")
    inactive = await _insert_employee(
        db_session, name="InactiveAssignee", is_active=False
    )

    notifications = await notify_assigned(
        db_session, task, [active.id, inactive.id]
    )

    assert len(notifications) == 1
    assert notifications[0].recipient_id == active.id

    persisted = await _notifs_for_task(db_session, task.id)
    assert {n.recipient_id for n in persisted} == {active.id}


async def test_notify_mentioned_active_only(db_session):
    task, _actor = await _seed_task(db_session)
    active = await _insert_employee(db_session, name="ActiveMention")
    inactive = await _insert_employee(
        db_session, name="InactiveMention", is_active=False
    )

    notifications = await notify_mentioned(
        db_session, task, [active.id, inactive.id]
    )

    assert len(notifications) == 1
    assert notifications[0].recipient_id == active.id
    assert notifications[0].notification_type == "mentioned"


async def test_scan_due_soon_creates_one_notification_per_recipient(db_session):
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    task, _actor = await _seed_task(db_session, due_date=tomorrow)
    a1 = await _insert_employee(db_session, name="Due1")
    a2 = await _insert_employee(db_session, name="Due2")
    db_session.add(TaskAssignee(task_id=task.id, employee_id=a1.id))
    db_session.add(TaskAssignee(task_id=task.id, employee_id=a2.id))
    await db_session.flush()

    created = await scan_due_soon(db_session)

    relevant = [n for n in created if n.task_id == task.id]
    assert {n.recipient_id for n in relevant} == {a1.id, a2.id}
    assert all(n.notification_type == "due_soon" for n in relevant)
    assert all(n.is_read is False for n in relevant)


async def test_scan_due_soon_skips_inactive_assignee(db_session):
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    task, _actor = await _seed_task(db_session, due_date=tomorrow)
    active = await _insert_employee(db_session, name="DueActive")
    inactive = await _insert_employee(
        db_session, name="DueInactive", is_active=False
    )
    db_session.add(TaskAssignee(task_id=task.id, employee_id=active.id))
    db_session.add(TaskAssignee(task_id=task.id, employee_id=inactive.id))
    await db_session.flush()

    created = await scan_due_soon(db_session)
    relevant = [n for n in created if n.task_id == task.id]

    assert {n.recipient_id for n in relevant} == {active.id}


async def test_scan_due_soon_does_not_duplicate_per_day(db_session):
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    task, _actor = await _seed_task(db_session, due_date=tomorrow)
    assignee = await _insert_employee(db_session, name="DueAssignee")
    db_session.add(TaskAssignee(task_id=task.id, employee_id=assignee.id))
    await db_session.flush()

    first = await scan_due_soon(db_session)
    await db_session.flush()
    second = await scan_due_soon(db_session)

    relevant_first = [n for n in first if n.task_id == task.id]
    relevant_second = [n for n in second if n.task_id == task.id]

    assert len(relevant_first) == 1
    assert len(relevant_second) == 0

    persisted = await _notifs_for_task(db_session, task.id)
    due_soon = [n for n in persisted if n.notification_type == "due_soon"]
    assert len(due_soon) == 1
