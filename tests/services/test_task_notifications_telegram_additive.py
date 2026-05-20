# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""Regression tests proving Telegram task hooks are additive."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Notification,
    TaskAssignee,
    TelegramOutbox,
    TelegramTaskLink,
)
from app.schemas.tasks import TaskCreate
from app.services.task_comment_service import create_comment
from app.services.task_notification_service import (
    notify_commented,
    notify_state_changed,
)
from app.services.task_service import create_task

pytestmark = pytest.mark.asyncio


async def test_comment_in_app_notifications_survive_telegram_hook(
    db_session: AsyncSession,
    bound_telegram_group,
):
    state = sorted(bound_telegram_group.project.states, key=lambda item: item.position)[0]
    task = await create_task(
        db_session,
        bound_telegram_group.project.id,
        TaskCreate(title="Additive Comment Task", state_id=state.id),
        bound_telegram_group.lead,
    )
    db_session.add(TaskAssignee(task_id=task.id, employee_id=bound_telegram_group.member.id))
    db_session.add(
        TelegramTaskLink(task_id=task.id, binding_id=bound_telegram_group.binding.id)
    )
    await db_session.flush()

    await create_comment(
        db_session,
        task.id,
        "Please review this task",
        bound_telegram_group.lead,
    )
    await notify_commented(
        db_session,
        task,
        bound_telegram_group.lead,
        [bound_telegram_group.member.id],
    )

    notification = await db_session.scalar(
        select(Notification).where(
            Notification.task_id == task.id,
            Notification.recipient_id == bound_telegram_group.member.id,
            Notification.notification_type == "commented",
        )
    )
    outbox = await db_session.scalar(
        select(TelegramOutbox).where(
            TelegramOutbox.task_id == task.id,
            TelegramOutbox.message_kind == "comment_added",
        )
    )
    assert notification is not None
    assert outbox is not None


async def test_state_change_in_app_notifications_survive_telegram_hook(
    db_session: AsyncSession,
    bound_telegram_group,
):
    states = sorted(bound_telegram_group.project.states, key=lambda item: item.position)
    task = await create_task(
        db_session,
        bound_telegram_group.project.id,
        TaskCreate(title="Additive State Task", state_id=states[0].id),
        bound_telegram_group.lead,
    )
    db_session.add(TaskAssignee(task_id=task.id, employee_id=bound_telegram_group.member.id))
    db_session.add(
        TelegramTaskLink(task_id=task.id, binding_id=bound_telegram_group.binding.id)
    )
    await db_session.flush()

    await notify_state_changed(
        db_session,
        task,
        states[0].name,
        bound_telegram_group.lead,
        states[1].name,
    )

    notification = await db_session.scalar(
        select(Notification).where(
            Notification.task_id == task.id,
            Notification.recipient_id == bound_telegram_group.member.id,
            Notification.notification_type == "state_changed",
        )
    )
    outbox = await db_session.scalar(
        select(TelegramOutbox).where(
            TelegramOutbox.task_id == task.id,
            TelegramOutbox.message_kind == "status_changed",
        )
    )
    assert notification is not None
    assert outbox is not None
