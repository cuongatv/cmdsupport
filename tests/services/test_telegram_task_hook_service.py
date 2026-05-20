# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""Tests for Telegram task hook dispatch."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Task,
    TelegramGroupBinding,
    TelegramOutbox,
    TelegramTaskLink,
)
from app.schemas.tasks import TaskCreate
from app.services.task_service import create_task
from app.services.telegram_task_hook_service import (
    notify_task_created,
    notify_task_status_changed,
    notify_task_updated,
)

pytestmark = pytest.mark.asyncio


async def _create_task(
    db_session: AsyncSession,
    bound_telegram_group,
    *,
    title: str = "Telegram Hook Task",
) -> Task:
    state = sorted(bound_telegram_group.project.states, key=lambda item: item.position)[0]
    return await create_task(
        db_session,
        bound_telegram_group.project.id,
        TaskCreate(title=title, state_id=state.id),
        bound_telegram_group.lead,
    )


async def _outbox_rows(db_session: AsyncSession, task_id: uuid.UUID) -> list[TelegramOutbox]:
    result = await db_session.execute(
        select(TelegramOutbox).where(TelegramOutbox.task_id == task_id)
    )
    return list(result.scalars().all())


async def test_notify_task_created_with_telegram_link_enqueues_outbox(
    db_session: AsyncSession,
    bound_telegram_group,
):
    task = await _create_task(db_session, bound_telegram_group)
    db_session.add(
        TelegramTaskLink(task_id=task.id, binding_id=bound_telegram_group.binding.id)
    )
    await db_session.flush()

    count = await notify_task_created(db_session, task)

    assert count == 1
    rows = await _outbox_rows(db_session, task.id)
    assert len(rows) == 1
    assert rows[0].message_kind == "task_created"
    assert rows[0].binding_id == bound_telegram_group.binding.id


async def test_notify_task_updated_without_link_returns_zero(
    db_session: AsyncSession,
    task_project_factory,
    employee_factory,
):
    actor = await employee_factory(name="No Link Actor")
    project = await task_project_factory(
        department_id=actor.department_id,
        creator=actor,
        identifier=f"NL{uuid.uuid4().hex[:6].upper()}",
    )
    state = sorted(project.states, key=lambda item: item.position)[0]
    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="No Link Task", state_id=state.id),
        actor,
    )

    count = await notify_task_updated(db_session, task, "title changed")

    assert count == 0
    assert await _outbox_rows(db_session, task.id) == []


async def test_status_change_enqueues_with_from_to_states(
    db_session: AsyncSession,
    bound_telegram_group,
):
    task = await _create_task(db_session, bound_telegram_group)
    db_session.add(
        TelegramTaskLink(task_id=task.id, binding_id=bound_telegram_group.binding.id)
    )
    await db_session.flush()

    count = await notify_task_status_changed(db_session, task, "Todo", "Done")

    assert count == 1
    rows = await _outbox_rows(db_session, task.id)
    assert len(rows) == 1
    assert rows[0].message_kind == "status_changed"
    assert rows[0].idempotency_key == f"task_status_changed:{task.id}:Todo->Done"
    assert "Todo" in rows[0].payload["text"]
    assert "Done" in rows[0].payload["text"]


async def test_multi_binding_for_same_project_is_ambiguous_and_skipped(
    db_session: AsyncSession,
    bound_telegram_group,
):
    task = await _create_task(db_session, bound_telegram_group)
    db_session.add(
        TelegramGroupBinding(
            department_id=bound_telegram_group.department.id,
            default_task_project_id=bound_telegram_group.project.id,
            chat_id=-100_000_000_000_2,
            message_thread_id=202,
            chat_title="Second Binding",
            chat_type="supergroup",
            is_active=True,
            bound_by_id=bound_telegram_group.lead.id,
        )
    )
    await db_session.flush()

    count = await notify_task_updated(db_session, task, "priority changed")

    assert count == 0
    assert await _outbox_rows(db_session, task.id) == []


async def test_inactive_binding_returns_zero(
    db_session: AsyncSession,
    bound_telegram_group,
):
    task = await _create_task(db_session, bound_telegram_group)
    bound_telegram_group.binding.is_active = False
    db_session.add(
        TelegramTaskLink(task_id=task.id, binding_id=bound_telegram_group.binding.id)
    )
    await db_session.flush()

    count = await notify_task_created(db_session, task)

    assert count == 0
    assert await _outbox_rows(db_session, task.id) == []
