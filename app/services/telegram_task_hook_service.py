"""Telegram task mutation hook dispatcher.

This module is intentionally small and side-effect-light: it resolves the
Telegram destination for a task event and delegates message creation to
``telegram_outbox_service``. It never sends Telegram HTTP and never commits;
callers own the surrounding task transaction.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Task, TelegramGroupBinding, TelegramTaskLink
from app.services import telegram_outbox_service


async def notify_task_created(session: AsyncSession, task: Task) -> int:
    """Enqueue a Telegram outbox row for a task-created event when bound."""
    binding = await _resolve_binding(session, task)
    if binding is None:
        return 0

    row = await telegram_outbox_service.enqueue_task_created(
        session,
        binding=binding,
        task=task,
        task_url=_task_url(task),
    )
    return 1 if row is not None else 0


async def notify_task_updated(session: AsyncSession, task: Task, summary: str) -> int:
    """Enqueue a Telegram outbox row for a generic task update when bound."""
    binding = await _resolve_binding(session, task)
    if binding is None:
        return 0

    row = await telegram_outbox_service.enqueue_task_updated(
        session,
        binding=binding,
        task=task,
        summary=summary,
        idempotency_suffix=summary,
    )
    return 1 if row is not None else 0


async def notify_task_status_changed(
    session: AsyncSession,
    task: Task,
    from_state: str,
    to_state: str,
) -> int:
    """Enqueue a Telegram outbox row for a task state transition when bound."""
    binding = await _resolve_binding(session, task)
    if binding is None:
        return 0

    row = await telegram_outbox_service.enqueue_task_status_changed(
        session,
        binding=binding,
        task=task,
        from_state=from_state,
        to_state=to_state,
        task_url=_task_url(task),
    )
    return 1 if row is not None else 0


async def notify_task_comment_added(
    session: AsyncSession,
    task: Task,
    author_display: str,
    comment_excerpt: str,
) -> int:
    """Enqueue a Telegram outbox row for a new task comment when bound."""
    binding = await _resolve_binding(session, task)
    if binding is None:
        return 0

    row = await telegram_outbox_service.enqueue_comment_added(
        session,
        binding=binding,
        task=task,
        author_display=author_display,
        comment_excerpt=comment_excerpt,
        idempotency_suffix=comment_excerpt,
    )
    return 1 if row is not None else 0


async def _resolve_binding(
    session: AsyncSession,
    task: Task,
) -> TelegramGroupBinding | None:
    explicit = await session.execute(
        select(TelegramGroupBinding)
        .join(TelegramTaskLink, TelegramTaskLink.binding_id == TelegramGroupBinding.id)
        .where(
            TelegramTaskLink.task_id == task.id,
            TelegramGroupBinding.is_active.is_(True),
        )
        .order_by(TelegramTaskLink.created_at, TelegramTaskLink.id)
    )
    binding = explicit.scalars().first()
    if binding is not None:
        return binding

    default_bindings = await session.execute(
        select(TelegramGroupBinding).where(
            TelegramGroupBinding.default_task_project_id == task.task_project_id,
            TelegramGroupBinding.is_active.is_(True),
        )
    )
    bindings = list(default_bindings.scalars().all())
    if len(bindings) == 1:
        return bindings[0]
    if len(bindings) > 1:
        logger.info(
            "telegram_task_hook: skip default-project notification for task_id={} "
            "project_id={} because {} active bindings are ambiguous",
            task.id,
            task.task_project_id,
            len(bindings),
        )
    return None


def _task_url(task: Task) -> str:
    return f"/tasks/{task.id}"
