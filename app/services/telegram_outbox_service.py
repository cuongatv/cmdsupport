"""Telegram outbox enqueue service.

Turns task lifecycle events and Telegram command replies into ``pending`` rows
in ``telegram_outbox``. The outbound HTTP call is *not* performed here — the
arq worker (Task 12) polls the outbox by ``(status, next_attempt_at)`` and is
the only place that talks to the Telegram Bot API.

Design rules (mirrors ``task_notification_service.py``):

* Functions are async and take ``session: AsyncSession`` as the first argument.
* Functions ``flush`` but never ``commit`` — the caller owns the transaction.
* Inactive bindings short-circuit: the function logs at INFO and returns
  ``None`` so callers can fan-out optimistically without checking the flag.
* Idempotency: every public helper builds a stable ``idempotency_key`` and
  delegates to ``_insert_or_return_existing`` which first selects by key, and
  on miss inserts. Inserts are wrapped in a SAVEPOINT so an IntegrityError
  from a parallel writer can be swallowed and the existing row returned.
* Payloads are plain ``dict`` instances stored in the ``payload`` JSONB column.
  They contain *only* the rendered HTML text plus chat routing info; raw
  secrets (bot tokens, webhook secrets, user PII) never reach the outbox.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Task, TelegramGroupBinding, TelegramOutbox
from app.integrations.telegram.formatting import (
    format_command_reply,
    format_task_created,
    format_task_status_changed,
)

MESSAGE_KIND_TASK_CREATED: str = "task_created"
MESSAGE_KIND_TASK_UPDATED: str = "task_updated"
MESSAGE_KIND_COMMENT_ADDED: str = "comment_added"
MESSAGE_KIND_STATUS_CHANGED: str = "status_changed"
MESSAGE_KIND_BIND_REPLY: str = "bind_reply"
MESSAGE_KIND_LINK_REPLY: str = "link_reply"
MESSAGE_KIND_ERROR_REPLY: str = "error_reply"

_COMMAND_REPLY_KINDS: frozenset[str] = frozenset(
    {
        MESSAGE_KIND_BIND_REPLY,
        MESSAGE_KIND_LINK_REPLY,
        MESSAGE_KIND_ERROR_REPLY,
    }
)


class OutboxIdempotencyConflict(Exception):
    """Raised when a parallel writer wins the unique-key race AND the
    pre-existing row cannot be re-read (should not happen in practice)."""


async def enqueue_task_created(
    session: AsyncSession,
    *,
    binding: TelegramGroupBinding,
    task: Task,
    task_url: str,
    assignee_username: str | None = None,
    idempotency_suffix: str | None = None,
) -> TelegramOutbox | None:
    """Enqueue a ``task_created`` Telegram notification.

    Returns the inserted row, the pre-existing row on idempotency match, or
    ``None`` when the binding is disabled.
    """
    if not _binding_is_active(binding):
        return None

    text = format_task_created(
        task_title=task.title,
        task_url=task_url,
        assignee_username=assignee_username,
    )
    idempotency_key = f"task_created:{task.id}:{idempotency_suffix or ''}"
    payload = _build_payload(binding=binding, text=text)
    return await _insert_or_return_existing(
        session,
        idempotency_key=idempotency_key,
        binding_id=binding.id,
        task_id=task.id,
        message_kind=MESSAGE_KIND_TASK_CREATED,
        payload=payload,
    )


async def enqueue_task_status_changed(
    session: AsyncSession,
    *,
    binding: TelegramGroupBinding,
    task: Task,
    from_state: str,
    to_state: str,
    task_url: str,
) -> TelegramOutbox | None:
    """Enqueue a ``status_changed`` Telegram notification.

    Idempotency key includes the full transition so re-opening a task does
    not collide with the original close.
    """
    if not _binding_is_active(binding):
        return None

    text = format_task_status_changed(
        task_title=task.title,
        from_state=from_state,
        to_state=to_state,
        task_url=task_url,
    )
    idempotency_key = f"task_status_changed:{task.id}:{from_state}->{to_state}"
    payload = _build_payload(binding=binding, text=text)
    return await _insert_or_return_existing(
        session,
        idempotency_key=idempotency_key,
        binding_id=binding.id,
        task_id=task.id,
        message_kind=MESSAGE_KIND_STATUS_CHANGED,
        payload=payload,
    )


async def enqueue_task_updated(
    session: AsyncSession,
    *,
    binding: TelegramGroupBinding,
    task: Task,
    summary: str,
    idempotency_suffix: str | None = None,
) -> TelegramOutbox | None:
    """Enqueue a generic ``task_updated`` Telegram notification.

    ``summary`` is a short, already-trusted phrase (e.g. ``"due date moved
    to 2026-06-01"``); it is HTML-escaped here.
    """
    if not _binding_is_active(binding):
        return None

    text = format_command_reply(f"Task updated: {task.title} — {summary}")
    idempotency_key = f"task_updated:{task.id}:{idempotency_suffix or ''}"
    payload = _build_payload(binding=binding, text=text)
    return await _insert_or_return_existing(
        session,
        idempotency_key=idempotency_key,
        binding_id=binding.id,
        task_id=task.id,
        message_kind=MESSAGE_KIND_TASK_UPDATED,
        payload=payload,
    )


async def enqueue_comment_added(
    session: AsyncSession,
    *,
    binding: TelegramGroupBinding,
    task: Task,
    author_display: str,
    comment_excerpt: str,
    idempotency_suffix: str | None = None,
) -> TelegramOutbox | None:
    """Enqueue a ``comment_added`` Telegram notification."""
    if not _binding_is_active(binding):
        return None

    text = format_command_reply(
        f"New comment on {task.title} by {author_display}: {comment_excerpt}"
    )
    idempotency_key = f"comment_added:{task.id}:{idempotency_suffix or ''}"
    payload = _build_payload(binding=binding, text=text)
    return await _insert_or_return_existing(
        session,
        idempotency_key=idempotency_key,
        binding_id=binding.id,
        task_id=task.id,
        message_kind=MESSAGE_KIND_COMMENT_ADDED,
        payload=payload,
    )


async def enqueue_command_reply(
    session: AsyncSession,
    *,
    binding: TelegramGroupBinding,
    text: str,
    kind: str,
    idempotency_key: str,
    task: Task | None = None,
    pre_escaped: bool = False,
) -> TelegramOutbox | None:
    """Enqueue a Telegram reply to a ``/bind``, ``/link``, or error command.

    ``kind`` must be one of ``bind_reply | link_reply | error_reply``.
    Caller supplies a stable ``idempotency_key`` (typically derived from the
    incoming ``update_id`` or command id). ``text`` is wrapped through
    ``format_command_reply`` unless ``pre_escaped`` is True.
    """
    if kind not in _COMMAND_REPLY_KINDS:
        raise ValueError(
            f"enqueue_command_reply: unsupported kind {kind!r}; "
            f"expected one of {sorted(_COMMAND_REPLY_KINDS)}"
        )

    if not _binding_is_active(binding):
        return None

    rendered = text if pre_escaped else format_command_reply(text)
    payload = _build_payload(binding=binding, text=rendered)
    return await _insert_or_return_existing(
        session,
        idempotency_key=idempotency_key,
        binding_id=binding.id,
        task_id=task.id if task is not None else None,
        message_kind=kind,
        payload=payload,
    )


def _binding_is_active(binding: TelegramGroupBinding) -> bool:
    if binding.is_active:
        return True
    logger.info(
        "telegram_outbox: skip enqueue (binding inactive) binding_id={} chat_id={}",
        binding.id,
        binding.chat_id,
    )
    return False


def _build_payload(*, binding: TelegramGroupBinding, text: str) -> dict[str, Any]:
    """Build the JSONB payload stored on the outbox row.

    Intentionally minimal: chat routing + rendered HTML + parse mode. Bot
    tokens, webhook secrets, and raw user PII never appear here.
    """
    payload: dict[str, Any] = {
        "chat_id": binding.chat_id,
        "message_thread_id": binding.message_thread_id,
        "text": text,
        "parse_mode": "HTML",
    }
    return payload


async def _insert_or_return_existing(
    session: AsyncSession,
    *,
    idempotency_key: str,
    binding_id: Any,
    task_id: Any,
    message_kind: str,
    payload: dict[str, Any],
) -> TelegramOutbox:
    """Look up by ``idempotency_key`` and insert on miss.

    The lookup is performed first to avoid generating an IntegrityError in
    the common (single-writer) case. The insert path is still defended with
    a SAVEPOINT so a concurrent writer that races us between the SELECT and
    INSERT does not poison the outer transaction.
    """
    existing = await session.execute(
        select(TelegramOutbox).where(
            TelegramOutbox.idempotency_key == idempotency_key
        )
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        return row

    row = TelegramOutbox(
        binding_id=binding_id,
        task_id=task_id,
        message_kind=message_kind,
        idempotency_key=idempotency_key,
        payload=payload,
        status="pending",
        retry_count=0,
    )
    session.add(row)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        # A concurrent writer beat us to the unique index. Re-read to find
        # the row they inserted.
        retry = await session.execute(
            select(TelegramOutbox).where(
                TelegramOutbox.idempotency_key == idempotency_key
            )
        )
        raced = retry.scalar_one_or_none()
        if raced is None:
            raise OutboxIdempotencyConflict(
                f"Could not insert or fetch outbox row for key {idempotency_key!r}"
            )
        return raced
    return row
