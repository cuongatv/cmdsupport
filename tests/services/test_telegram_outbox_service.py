# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""Tests for ``app.services.telegram_outbox_service``.

The service must:

* Insert a single ``pending`` row per task event with a stable idempotency
  key, returning the existing row on duplicate calls.
* Skip enqueue (return ``None``, no row) when ``binding.is_active`` is False.
* Never persist anything that looks like a Telegram bot token in the
  ``payload`` JSONB blob.

The tests use the rollback-isolated ``db_session`` fixture plus the
``bound_telegram_group`` fixture from ``tests.fixtures.telegram`` so we get a
real Department/Project/Binding triple to attach Task rows to.
"""

from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import func, select

from app.database.models import Task, TaskState, TelegramOutbox
from app.schemas.tasks import TaskCreate
from app.services.task_service import create_task
from app.services.telegram_outbox_service import (
    MESSAGE_KIND_BIND_REPLY,
    MESSAGE_KIND_ERROR_REPLY,
    MESSAGE_KIND_LINK_REPLY,
    MESSAGE_KIND_STATUS_CHANGED,
    MESSAGE_KIND_TASK_CREATED,
    enqueue_command_reply,
    enqueue_task_created,
    enqueue_task_status_changed,
)
from tests.fixtures.telegram import BoundTelegramGroupFixture

pytestmark = pytest.mark.asyncio

# Telegram bot tokens look like "<digits>:<35+ url-safe chars>". We use the
# same shape for the leakage assertion.
_TOKEN_LOOKALIKE_RE = re.compile(r"\d+:[A-Za-z0-9_-]{30,}")


async def _make_task(
    db_session,
    bound: BoundTelegramGroupFixture,
    *,
    title: str = "Outbox Sample Task",
) -> Task:
    state_row = await db_session.execute(
        select(TaskState)
        .where(TaskState.task_project_id == bound.project.id)
        .order_by(TaskState.position.asc())
    )
    state = state_row.scalars().first()
    assert state is not None, "task_project fixture must have at least one state"
    return await create_task(
        db_session,
        bound.project.id,
        TaskCreate(title=title, state_id=state.id),
        bound.lead,
    )


async def _outbox_count(db_session, *, binding_id) -> int:
    result = await db_session.execute(
        select(func.count()).select_from(TelegramOutbox).where(
            TelegramOutbox.binding_id == binding_id
        )
    )
    return result.scalar_one()


async def test_enqueue_task_created_inserts_pending_row(
    db_session,
    bound_telegram_group: BoundTelegramGroupFixture,
):
    task = await _make_task(db_session, bound_telegram_group)

    row = await enqueue_task_created(
        db_session,
        binding=bound_telegram_group.binding,
        task=task,
        task_url="https://cmd.example/tasks/abc",
        assignee_username="telegram_lead",
    )

    assert row is not None
    assert row.status == "pending"
    assert row.retry_count == 0
    assert row.sent_at is None
    assert row.last_error is None
    assert row.message_kind == MESSAGE_KIND_TASK_CREATED
    assert row.binding_id == bound_telegram_group.binding.id
    assert row.task_id == task.id
    assert row.idempotency_key.startswith(f"task_created:{task.id}:")
    # Payload routing matches the binding.
    assert row.payload["chat_id"] == bound_telegram_group.binding.chat_id
    assert (
        row.payload["message_thread_id"]
        == bound_telegram_group.binding.message_thread_id
    )
    assert row.payload["parse_mode"] == "HTML"
    # The rendered text uses formatter output: HTML-safe and starts with the
    # task-created label.
    assert row.payload["text"].startswith("<b>Task created:</b>")
    # Exactly one row exists.
    assert await _outbox_count(db_session, binding_id=bound_telegram_group.binding.id) == 1


async def test_enqueue_task_created_returns_existing_on_duplicate_idempotency_key(
    db_session,
    bound_telegram_group: BoundTelegramGroupFixture,
):
    task = await _make_task(db_session, bound_telegram_group)

    first = await enqueue_task_created(
        db_session,
        binding=bound_telegram_group.binding,
        task=task,
        task_url="https://cmd.example/tasks/abc",
    )
    second = await enqueue_task_created(
        db_session,
        binding=bound_telegram_group.binding,
        task=task,
        task_url="https://cmd.example/tasks/abc",
    )

    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert await _outbox_count(db_session, binding_id=bound_telegram_group.binding.id) == 1


async def test_enqueue_when_binding_disabled_returns_none_and_no_row(
    db_session,
    bound_telegram_group: BoundTelegramGroupFixture,
):
    task = await _make_task(db_session, bound_telegram_group)
    bound_telegram_group.binding.is_active = False
    await db_session.flush()

    row = await enqueue_task_created(
        db_session,
        binding=bound_telegram_group.binding,
        task=task,
        task_url="https://cmd.example/tasks/abc",
    )

    assert row is None
    assert await _outbox_count(db_session, binding_id=bound_telegram_group.binding.id) == 0


async def test_enqueue_task_status_changed_uses_unique_key_per_transition(
    db_session,
    bound_telegram_group: BoundTelegramGroupFixture,
):
    task = await _make_task(db_session, bound_telegram_group)

    todo_to_doing = await enqueue_task_status_changed(
        db_session,
        binding=bound_telegram_group.binding,
        task=task,
        from_state="todo",
        to_state="doing",
        task_url="https://cmd.example/tasks/abc",
    )
    doing_to_done = await enqueue_task_status_changed(
        db_session,
        binding=bound_telegram_group.binding,
        task=task,
        from_state="doing",
        to_state="done",
        task_url="https://cmd.example/tasks/abc",
    )
    duplicate_todo_to_doing = await enqueue_task_status_changed(
        db_session,
        binding=bound_telegram_group.binding,
        task=task,
        from_state="todo",
        to_state="doing",
        task_url="https://cmd.example/tasks/abc",
    )

    assert todo_to_doing is not None
    assert doing_to_done is not None
    assert duplicate_todo_to_doing is not None
    assert todo_to_doing.id != doing_to_done.id
    assert todo_to_doing.id == duplicate_todo_to_doing.id
    assert todo_to_doing.idempotency_key.endswith(":todo->doing")
    assert doing_to_done.idempotency_key.endswith(":doing->done")
    assert todo_to_doing.message_kind == MESSAGE_KIND_STATUS_CHANGED
    assert (
        await _outbox_count(db_session, binding_id=bound_telegram_group.binding.id)
        == 2
    )


async def test_enqueue_command_reply_for_bind_link_error_kinds(
    db_session,
    bound_telegram_group: BoundTelegramGroupFixture,
):
    bind_row = await enqueue_command_reply(
        db_session,
        binding=bound_telegram_group.binding,
        text="Group bound to department X",
        kind=MESSAGE_KIND_BIND_REPLY,
        idempotency_key="bind_reply:update_id:9001",
    )
    link_row = await enqueue_command_reply(
        db_session,
        binding=bound_telegram_group.binding,
        text="Account linked",
        kind=MESSAGE_KIND_LINK_REPLY,
        idempotency_key="link_reply:update_id:9002",
    )
    error_row = await enqueue_command_reply(
        db_session,
        binding=bound_telegram_group.binding,
        text="Could not parse command",
        kind=MESSAGE_KIND_ERROR_REPLY,
        idempotency_key="error_reply:update_id:9003",
    )

    assert bind_row is not None
    assert link_row is not None
    assert error_row is not None
    assert {bind_row.message_kind, link_row.message_kind, error_row.message_kind} == {
        MESSAGE_KIND_BIND_REPLY,
        MESSAGE_KIND_LINK_REPLY,
        MESSAGE_KIND_ERROR_REPLY,
    }
    # Each command reply has no associated task.
    assert bind_row.task_id is None
    assert link_row.task_id is None
    assert error_row.task_id is None
    # All three are pending and use HTML parse mode.
    for row in (bind_row, link_row, error_row):
        assert row.status == "pending"
        assert row.payload["parse_mode"] == "HTML"
        assert row.payload["chat_id"] == bound_telegram_group.binding.chat_id
    # Unsupported kinds raise immediately, no rows touched.
    with pytest.raises(ValueError):
        await enqueue_command_reply(
            db_session,
            binding=bound_telegram_group.binding,
            text="oops",
            kind="task_created",
            idempotency_key="bogus",
        )
    assert (
        await _outbox_count(db_session, binding_id=bound_telegram_group.binding.id)
        == 3
    )


async def test_payload_does_not_contain_token_lookalike(
    db_session,
    bound_telegram_group: BoundTelegramGroupFixture,
):
    task = await _make_task(
        db_session,
        bound_telegram_group,
        title="Pretend token 1234567890:ABCDEFabcdef0123456789-_ZZZZZZZZ",
    )

    created = await enqueue_task_created(
        db_session,
        binding=bound_telegram_group.binding,
        task=task,
        task_url="https://cmd.example/tasks/abc",
        assignee_username="telegram_lead",
    )
    status = await enqueue_task_status_changed(
        db_session,
        binding=bound_telegram_group.binding,
        task=task,
        from_state="todo",
        to_state="doing",
        task_url="https://cmd.example/tasks/abc",
    )
    bind_reply = await enqueue_command_reply(
        db_session,
        binding=bound_telegram_group.binding,
        text="bind ok",
        kind=MESSAGE_KIND_BIND_REPLY,
        idempotency_key="bind_reply:test",
    )

    for row in (created, status, bind_reply):
        assert row is not None
        serialized = json.dumps(row.payload)
        assert _TOKEN_LOOKALIKE_RE.search(serialized) is None, (
            f"payload for {row.message_kind!r} contains a token-shaped substring: "
            f"{serialized!r}"
        )
