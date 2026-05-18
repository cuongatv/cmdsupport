"""arq jobs for native task notifications.

These jobs run inside ``cmd_worker`` (default queue) — they own their
transaction boundary and call ``session.commit()`` themselves. The underlying
service functions (``app.services.task_notification_service``) only flush.

UUIDs are passed across the wire as strings because arq's default pickle
serializer is fine with UUID, but the surrounding ingestion jobs (and most
job-call sites in the codebase) already convert UUIDs to ``str`` to keep the
queue payloads JSON-friendly.
"""
from __future__ import annotations

import uuid

from loguru import logger


async def task_assignment_notification(
    ctx: dict,
    task_id: str,
    assignee_ids: list[str],
) -> dict:
    """Fan out ``assigned`` notifications for the given task and assignees."""
    from app.database import async_session_factory
    from app.database.models import Task
    from app.services.task_notification_service import notify_assigned

    tid = uuid.UUID(task_id)
    aids = [uuid.UUID(value) for value in assignee_ids]

    async with async_session_factory() as session:
        task = await session.get(Task, tid)
        if task is None:
            logger.warning(f"task_assignment_notification: task {task_id} not found")
            return {"created": 0}

        notifications = await notify_assigned(session, task, aids)
        await session.commit()
        logger.info(
            f"task_assignment_notification: task={task_id} "
            f"requested={len(aids)} created={len(notifications)}"
        )
        return {"created": len(notifications)}


async def task_due_soon_scan(ctx: dict) -> dict:
    """Cron entry point: scan tasks due in ~1 day and create due_soon notifications."""
    from app.database import async_session_factory
    from app.services.task_notification_service import scan_due_soon

    async with async_session_factory() as session:
        notifications = await scan_due_soon(session)
        await session.commit()
        logger.info(
            f"task_due_soon_scan: created={len(notifications)} due_soon notifications"
        )
        return {"created": len(notifications)}


async def scan_aging_tasks(ctx: dict) -> dict:
    """Cron entry point: scan tasks idle past their state's ``aging_warn_days``.

    No-op when ``FEATURE_AGILE_PHASE_1`` is disabled (the service function
    short-circuits). Idempotent across runs via a 24-hour dedupe window keyed
    on ``(task_id, notification_type='task_aging_alert')``.
    """
    from app.database import async_session_factory
    from app.services.task_notification_service import (
        scan_aging_tasks as scan_aging_tasks_service,
    )

    async with async_session_factory() as session:
        notifications = await scan_aging_tasks_service(session)
        await session.commit()
        logger.info(
            f"scan_aging_tasks: created={len(notifications)} task_aging_alert notifications"
        )
        return {"created": len(notifications)}


async def capture_flow_snapshots_job(ctx: dict) -> dict:
    """Cron entry point: capture Phase 5 flow snapshots for active projects."""
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.database.models import TaskProject
    from app.services.task_flow_service import capture_flow_snapshot

    async with async_session_factory() as session:
        result = await session.execute(
            select(TaskProject)
            .where(TaskProject.is_archived.is_(False))
            .order_by(TaskProject.created_at, TaskProject.id)
        )
        projects = list(result.scalars().all())

        captured = 0
        for project in projects:
            snapshots = await capture_flow_snapshot(session, project.id)
            captured += len(snapshots)

        await session.commit()
        logger.info(
            f"capture_flow_snapshots_job: projects={len(projects)} snapshots={captured}"
        )
        return {"projects": len(projects), "snapshots": captured}
