"""Task notification service.

Creates in-app notification rows for task events. Notifications are polled by
the frontend (no websocket / no SSE — see ``task_constants`` for the polling
interval).

Notification kinds (stored in ``Notification.notification_type``):
- ``assigned``       — a task was assigned to an employee
- ``mentioned``      — an employee was mentioned in a comment / description
- ``commented``      — a comment was posted on a task the employee participates in
- ``state_changed``  — the task workflow state changed
- ``due_soon``       — a task is due within 1 day (emitted by the cron scan)

Inactive employees never receive notifications.

The functions in this module never call ``db.commit()`` — they only
``db.flush()``. The arq job (or router) that drives them owns the transaction
boundary.

Schema notes (verified against ``app/database/models.py``):
- The column is ``notification_type`` (NOT ``kind``).
- The task title snapshot is stored in ``Notification.title`` (there is no
  ``payload`` JSONB column). The snapshot lets a notification render correctly
  even after the task is soft-deleted.
- ``Task.due_date`` is the canonical "target date" column.
"""
from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Employee,
    Notification,
    Task,
    TaskAssignee,
    TaskState,
)

NOTIFICATION_TYPE_ASSIGNED: str = "assigned"
NOTIFICATION_TYPE_MENTIONED: str = "mentioned"
NOTIFICATION_TYPE_COMMENTED: str = "commented"
NOTIFICATION_TYPE_STATE_CHANGED: str = "state_changed"
NOTIFICATION_TYPE_DUE_SOON: str = "due_soon"

_TERMINAL_STATE_GROUPS: tuple[str, ...] = ("done", "cancelled")


async def create_notification(
    db: AsyncSession,
    *,
    recipient_id: uuid.UUID,
    notification_type: str,
    task_id: uuid.UUID,
    title: str,
    body: str | None = None,
    actor_id: uuid.UUID | None = None,
) -> Notification:
    """Insert a single Notification row and flush, without committing.

    ``title`` is a snapshot of the task title at notification time so the
    rendered notification survives a soft delete of the underlying task.
    """
    notification = Notification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        notification_type=notification_type,
        task_id=task_id,
        title=title,
        body=body,
        is_read=False,
        read_at=None,
    )
    db.add(notification)
    await db.flush()
    return notification


async def notify_assigned(
    db: AsyncSession,
    task: Task,
    assignee_ids: list[uuid.UUID],
    *,
    actor: Employee | None = None,
) -> list[Notification]:
    """Create one ``assigned`` notification per ACTIVE assignee."""
    active_ids = await _filter_active_employee_ids(db, assignee_ids)
    actor_id = actor.id if actor is not None else None
    notifications: list[Notification] = []
    for recipient_id in active_ids:
        notifications.append(
            await create_notification(
                db,
                recipient_id=recipient_id,
                notification_type=NOTIFICATION_TYPE_ASSIGNED,
                task_id=task.id,
                title=task.title,
                actor_id=actor_id,
            )
        )
    return notifications


async def notify_mentioned(
    db: AsyncSession,
    task: Task,
    mention_ids: list[uuid.UUID],
    *,
    actor: Employee | None = None,
) -> list[Notification]:
    """Create one ``mentioned`` notification per ACTIVE mentioned employee."""
    active_ids = await _filter_active_employee_ids(db, mention_ids)
    actor_id = actor.id if actor is not None else None
    notifications: list[Notification] = []
    for recipient_id in active_ids:
        notifications.append(
            await create_notification(
                db,
                recipient_id=recipient_id,
                notification_type=NOTIFICATION_TYPE_MENTIONED,
                task_id=task.id,
                title=task.title,
                actor_id=actor_id,
            )
        )
    return notifications


async def notify_commented(
    db: AsyncSession,
    task: Task,
    commenter: Employee,
    recipient_ids: list[uuid.UUID],
) -> list[Notification]:
    """Notify all ACTIVE recipients about a new comment, except the commenter."""
    filtered = [rid for rid in recipient_ids if rid != commenter.id]
    active_ids = await _filter_active_employee_ids(db, filtered)
    notifications: list[Notification] = []
    for recipient_id in active_ids:
        notifications.append(
            await create_notification(
                db,
                recipient_id=recipient_id,
                notification_type=NOTIFICATION_TYPE_COMMENTED,
                task_id=task.id,
                title=task.title,
                actor_id=commenter.id,
            )
        )
    return notifications


async def notify_state_changed(
    db: AsyncSession,
    task: Task,
    old_state_name: str,
    actor: Employee,
) -> list[Notification]:
    """Notify all ACTIVE assignees that the task state changed."""
    result = await db.execute(
        select(TaskAssignee.employee_id).where(TaskAssignee.task_id == task.id)
    )
    assignee_ids = list(result.scalars().all())
    active_ids = await _filter_active_employee_ids(db, assignee_ids)
    body = f"State changed from {old_state_name}"
    notifications: list[Notification] = []
    for recipient_id in active_ids:
        notifications.append(
            await create_notification(
                db,
                recipient_id=recipient_id,
                notification_type=NOTIFICATION_TYPE_STATE_CHANGED,
                task_id=task.id,
                title=task.title,
                body=body,
                actor_id=actor.id,
            )
        )
    return notifications


async def scan_due_soon(db: AsyncSession) -> list[Notification]:
    """Create ``due_soon`` notifications for tasks whose ``due_date`` is tomorrow.

    Skips tasks in ``done`` / ``cancelled`` state groups and soft-deleted tasks.
    Skips inactive assignees.

    Idempotent per (task, recipient, UTC calendar day): if a ``due_soon``
    notification already exists for the recipient/task with ``created_at`` on
    the current UTC day, no new notification is emitted.
    """
    now_utc = datetime.now(timezone.utc)
    today_utc = now_utc.date()
    target_date = today_utc + timedelta(days=1)

    target_start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
    target_end = target_start + timedelta(days=1)
    today_start = datetime.combine(today_utc, time.min, tzinfo=timezone.utc)
    today_end = today_start + timedelta(days=1)

    tasks_result = await db.execute(
        select(Task)
        .join(TaskState, TaskState.id == Task.state_id)
        .where(
            Task.due_date >= target_start,
            Task.due_date < target_end,
            Task.deleted_at.is_(None),
            TaskState.group.notin_(_TERMINAL_STATE_GROUPS),
        )
    )
    tasks = list(tasks_result.scalars().all())
    if not tasks:
        return []

    task_ids = [task.id for task in tasks]

    assignees_result = await db.execute(
        select(TaskAssignee.task_id, TaskAssignee.employee_id)
        .join(Employee, Employee.id == TaskAssignee.employee_id)
        .where(
            TaskAssignee.task_id.in_(task_ids),
            Employee.is_active.is_(True),
        )
    )
    pairs: list[tuple[uuid.UUID, uuid.UUID]] = [
        (row[0], row[1]) for row in assignees_result.all()
    ]
    if not pairs:
        return []

    existing_result = await db.execute(
        select(Notification.task_id, Notification.recipient_id).where(
            Notification.task_id.in_(task_ids),
            Notification.notification_type == NOTIFICATION_TYPE_DUE_SOON,
            Notification.created_at >= today_start,
            Notification.created_at < today_end,
        )
    )
    already_notified: set[tuple[uuid.UUID, uuid.UUID]] = {
        (row[0], row[1]) for row in existing_result.all()
    }

    task_by_id = {task.id: task for task in tasks}
    created: list[Notification] = []
    for task_id, recipient_id in pairs:
        if (task_id, recipient_id) in already_notified:
            continue
        task = task_by_id[task_id]
        notification = await create_notification(
            db,
            recipient_id=recipient_id,
            notification_type=NOTIFICATION_TYPE_DUE_SOON,
            task_id=task_id,
            title=task.title,
        )
        created.append(notification)
        already_notified.add((task_id, recipient_id))

    return created


async def _filter_active_employee_ids(
    db: AsyncSession,
    employee_ids: list[uuid.UUID],
) -> list[uuid.UUID]:
    """Return the input IDs deduplicated and restricted to ACTIVE employees, order preserved."""
    ordered_unique: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for employee_id in employee_ids:
        if employee_id in seen:
            continue
        seen.add(employee_id)
        ordered_unique.append(employee_id)

    if not ordered_unique:
        return []

    result = await db.execute(
        select(Employee.id).where(
            Employee.id.in_(ordered_unique),
            Employee.is_active.is_(True),
        )
    )
    valid_ids = set(result.scalars().all())
    return [eid for eid in ordered_unique if eid in valid_ids]
