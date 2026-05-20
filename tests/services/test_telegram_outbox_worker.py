# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportMissingParameterType=false, reportExplicitAny=false
"""Tests for app/jobs/telegram_jobs.py:send_pending_telegram_outbox."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import TelegramOutbox
from app.integrations.telegram.client import (
    TelegramAPIError,
    TelegramRateLimitError,
)
from app.jobs.telegram_jobs import (
    DEFAULT_BACKOFF_SECONDS,
    MAX_RETRIES,
    send_pending_telegram_outbox,
)
from app.services.config_service import ConfigService
from tests.fakes.telegram_client import FakeTelegramClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _frozen_now() -> datetime:
    return datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


def _make_session_factory(session: AsyncSession):
    """Wrap an existing session so the worker's ``async with`` does not close it."""

    @asynccontextmanager
    async def factory():
        yield session

    return factory


async def _seed_outbox(
    session: AsyncSession,
    *,
    binding_id,
    chat_id: int,
    text: str = "hi",
    parse_mode: str | None = "HTML",
    message_thread_id: int | None = None,
    status: str = "pending",
    retry_count: int = 0,
    next_attempt_at: datetime | None = None,
) -> TelegramOutbox:
    payload: dict[str, object] = {"chat_id": chat_id, "text": text}
    if parse_mode is not None:
        payload["parse_mode"] = parse_mode
    if message_thread_id is not None:
        payload["message_thread_id"] = message_thread_id

    row = TelegramOutbox(
        binding_id=binding_id,
        message_kind="task_created",
        idempotency_key=f"test:{uuid.uuid4()}",
        payload=payload,
        status=status,
        retry_count=retry_count,
        next_attempt_at=next_attempt_at,
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# Fake client variants
# ---------------------------------------------------------------------------


class _RateLimitClient(FakeTelegramClient):
    """Raises the real :class:`TelegramRateLimitError`."""

    def __init__(self, retry_after: int) -> None:
        super().__init__()
        self._raise_retry_after = retry_after

    async def send_message(  # type: ignore[override]
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        message_thread_id: int | None = None,
    ) -> dict[str, object]:
        raise TelegramRateLimitError(self._raise_retry_after)


class _ForbiddenClient(FakeTelegramClient):
    """Raises a 403 :class:`TelegramAPIError`."""

    async def send_message(  # type: ignore[override]
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        message_thread_id: int | None = None,
    ) -> dict[str, object]:
        raise TelegramAPIError(
            status_code=403,
            description="Forbidden: bot was kicked from the supergroup chat",
        )


class _GenericServerErrorClient(FakeTelegramClient):
    """Raises a generic non-forbidden :class:`TelegramAPIError`."""

    async def send_message(  # type: ignore[override]
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        message_thread_id: int | None = None,
    ) -> dict[str, object]:
        raise TelegramAPIError(status_code=500, description="Internal Server Error")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_send_pending_sends_one_and_marks_sent(
    db_session: AsyncSession, bound_telegram_group
) -> None:
    binding = bound_telegram_group.binding
    row = await _seed_outbox(
        db_session,
        binding_id=binding.id,
        chat_id=binding.chat_id,
        text="hi",
    )
    await ConfigService(db_session).set("telegram_bot_token", "BOT:FAKE")
    await db_session.flush()

    fake = FakeTelegramClient()
    count = await send_pending_telegram_outbox(
        {},
        client_factory=lambda _token: fake,
        session_factory=_make_session_factory(db_session),
        now=_frozen_now,
    )

    assert count == 1
    assert row.status == "sent"
    assert row.sent_at is not None
    assert row.last_error is None
    assert len(fake.sent) == 1
    assert fake.sent[0]["chat_id"] == binding.chat_id
    assert fake.sent[0]["text"] == "hi"


async def test_send_pending_handles_rate_limit_and_schedules_retry(
    db_session: AsyncSession, bound_telegram_group
) -> None:
    binding = bound_telegram_group.binding
    row = await _seed_outbox(
        db_session,
        binding_id=binding.id,
        chat_id=binding.chat_id,
    )
    await ConfigService(db_session).set("telegram_bot_token", "BOT:FAKE")
    await db_session.flush()

    fake = _RateLimitClient(retry_after=11)
    count = await send_pending_telegram_outbox(
        {},
        client_factory=lambda _token: fake,
        session_factory=_make_session_factory(db_session),
        now=_frozen_now,
    )

    assert count == 0
    assert row.status == "pending"
    assert row.retry_count == 1
    assert row.next_attempt_at is not None
    assert row.next_attempt_at >= _frozen_now() + timedelta(seconds=11)
    assert row.last_error == "rate_limited"


async def test_send_pending_marks_failed_on_403_and_disables_binding(
    db_session: AsyncSession, bound_telegram_group
) -> None:
    binding = bound_telegram_group.binding
    row = await _seed_outbox(
        db_session,
        binding_id=binding.id,
        chat_id=binding.chat_id,
    )
    await ConfigService(db_session).set("telegram_bot_token", "BOT:FAKE")
    await db_session.flush()

    count = await send_pending_telegram_outbox(
        {},
        client_factory=lambda _token: _ForbiddenClient(),
        session_factory=_make_session_factory(db_session),
        now=_frozen_now,
    )

    assert count == 0
    assert row.status == "failed"
    assert row.last_error is not None
    assert binding.is_active is False
    assert binding.bot_status == "kicked"
    assert binding.disabled_at is not None


async def test_send_pending_no_token_returns_zero_without_sends(
    db_session: AsyncSession, bound_telegram_group
) -> None:
    binding = bound_telegram_group.binding
    row = await _seed_outbox(
        db_session,
        binding_id=binding.id,
        chat_id=binding.chat_id,
    )
    # NOTE: no token set.

    fake = FakeTelegramClient()
    count = await send_pending_telegram_outbox(
        {},
        client_factory=lambda _token: fake,
        session_factory=_make_session_factory(db_session),
        now=_frozen_now,
    )

    assert count == 0
    assert row.status == "pending"
    assert row.last_attempted_at is None
    assert fake.sent == []


async def test_send_pending_skips_inactive_binding(
    db_session: AsyncSession, bound_telegram_group
) -> None:
    binding = bound_telegram_group.binding
    binding.is_active = False
    await db_session.flush()

    row = await _seed_outbox(
        db_session,
        binding_id=binding.id,
        chat_id=binding.chat_id,
    )
    await ConfigService(db_session).set("telegram_bot_token", "BOT:FAKE")
    await db_session.flush()

    fake = FakeTelegramClient()
    count = await send_pending_telegram_outbox(
        {},
        client_factory=lambda _token: fake,
        session_factory=_make_session_factory(db_session),
        now=_frozen_now,
    )

    assert count == 0
    assert row.status == "cancelled"
    assert row.last_error == "binding_inactive"
    assert fake.sent == []


async def test_send_pending_max_retries_marks_failed(
    db_session: AsyncSession, bound_telegram_group
) -> None:
    binding = bound_telegram_group.binding
    row = await _seed_outbox(
        db_session,
        binding_id=binding.id,
        chat_id=binding.chat_id,
        retry_count=MAX_RETRIES,
    )
    await ConfigService(db_session).set("telegram_bot_token", "BOT:FAKE")
    await db_session.flush()

    count = await send_pending_telegram_outbox(
        {},
        client_factory=lambda _token: _GenericServerErrorClient(),
        session_factory=_make_session_factory(db_session),
        now=_frozen_now,
    )

    assert count == 0
    assert row.status == "failed"
    # retry_count stays at MAX_RETRIES (no further increment)
    assert row.retry_count == MAX_RETRIES
    assert row.last_error is not None
    # Sanity: backoff constant is exposed for callers that want to introspect.
    assert DEFAULT_BACKOFF_SECONDS == 30
