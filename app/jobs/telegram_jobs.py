# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportMissingParameterType=false, reportExplicitAny=false, reportMissingTypeArgument=false, reportGeneralTypeIssues=false
"""arq job: drain pending Telegram outbox messages.

The job reads the bot token from ConfigService, picks up rows where
``status='pending'`` whose backoff has elapsed, and attempts to send each
message via :class:`TelegramClient`, writing a terminal status per row.

Failure classification:

* :class:`TelegramRateLimitError` -> reschedule using ``retry_after`` seconds.
* :class:`TelegramAPIError` with HTTP 401/403 -> disable the chat binding
  (``is_active=False``, plus ``bot_status='kicked'`` for 403) and mark the
  row ``failed`` without retry.
* Other errors -> exponential backoff up to ``MAX_RETRIES``, then ``failed``.

The bot token is treated as a secret: it is never logged.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Callable

from loguru import logger
from sqlalchemy import select, update

from app.database import async_session_factory
from app.database.models import TelegramGroupBinding, TelegramOutbox
from app.integrations.telegram.client import (
    TelegramAPIError,
    TelegramClient,
    TelegramRateLimitError,
)
from app.services.config_service import ConfigService

MAX_RETRIES = 5
DEFAULT_BACKOFF_SECONDS = 30
CHAT_FORBIDDEN_STATUSES = {401, 403}


@asynccontextmanager
async def _default_session_cm():
    async with async_session_factory() as session:
        yield session


def _make_clock(now: Callable[[], datetime] | None) -> Callable[[], datetime]:
    if now is not None:
        return now
    return lambda: datetime.now(timezone.utc)


async def send_pending_telegram_outbox(
    ctx: dict,
    *,
    client_factory: Callable[[str], object] | None = None,
    session_factory: Callable[[], object] | None = None,
    now: Callable[[], datetime] | None = None,
    batch_limit: int = 20,
) -> int:
    """Drain up to ``batch_limit`` pending Telegram outbox rows.

    Returns the number of rows whose final status is ``sent``.
    """
    clock = _make_clock(now)
    open_session = session_factory or _default_session_cm
    owns_client = client_factory is None
    sent_count = 0

    async with open_session() as session:
        token = await ConfigService(session).get("telegram_bot_token")
        if not token:
            logger.info(
                "send_pending_telegram_outbox: telegram_bot_token not configured; skipping"
            )
            return 0

        now_value = clock()
        stmt = (
            select(TelegramOutbox)
            .where(TelegramOutbox.status == "pending")
            .where(
                (TelegramOutbox.next_attempt_at.is_(None))
                | (TelegramOutbox.next_attempt_at <= now_value)
            )
            .order_by(TelegramOutbox.created_at.asc())
            .limit(batch_limit)
        )
        rows = list((await session.execute(stmt)).scalars().all())
        if not rows:
            logger.debug("send_pending_telegram_outbox: nothing pending")
            return 0

        if client_factory is None:
            client: object = TelegramClient(token=token)
        else:
            client = client_factory(token)

        try:
            for row in rows:
                try:
                    if await _process_row(session, client, row, clock):
                        sent_count += 1
                except Exception:  # pragma: no cover - last-resort safety net
                    logger.exception(
                        "send_pending_telegram_outbox: unexpected error for row {}",
                        row.id,
                    )
                    try:
                        await session.rollback()
                    except Exception:
                        logger.exception(
                            "send_pending_telegram_outbox: rollback failed for row {}",
                            row.id,
                        )
                    try:
                        fresh = await session.get(TelegramOutbox, row.id)
                        if fresh is not None and fresh.status != "sent":
                            fresh.status = "failed"
                            fresh.last_error = "unexpected_worker_error"
                            await session.commit()
                    except Exception:
                        logger.exception(
                            "send_pending_telegram_outbox: failed to mark row {} as failed",
                            row.id,
                        )
        finally:
            if owns_client:
                aclose = getattr(client, "aclose", None)
                if aclose is not None:
                    await aclose()

    return sent_count


async def _process_row(session, client, row: TelegramOutbox, clock) -> bool:
    """Process one outbox row. Returns ``True`` if it ended in ``sent``."""
    row_now = clock()

    # Atomic claim - succeeds only if no other worker has grabbed the row.
    claim = await session.execute(
        update(TelegramOutbox)
        .where(TelegramOutbox.id == row.id)
        .where(TelegramOutbox.status == "pending")
        .values(status="sending", last_attempted_at=row_now)
    )
    if (claim.rowcount or 0) == 0:
        await session.commit()
        return False

    # Sync the ORM view with the raw UPDATE so subsequent writes are clean.
    row.status = "sending"
    row.last_attempted_at = row_now

    binding = await session.get(TelegramGroupBinding, row.binding_id)
    if binding is None or binding.is_active is False:
        row.status = "cancelled"
        row.last_error = "binding_inactive"
        await session.commit()
        logger.info(
            "send_pending_telegram_outbox: row {} cancelled (binding inactive)",
            row.id,
        )
        return False

    payload = row.payload or {}

    try:
        await client.send_message(
            chat_id=payload.get("chat_id"),
            text=payload.get("text", ""),
            parse_mode=payload.get("parse_mode"),
            message_thread_id=payload.get("message_thread_id"),
        )
    except TelegramRateLimitError as err:
        retry_after = max(int(err.retry_after or 0), 1)
        row.status = "pending"
        row.retry_count = (row.retry_count or 0) + 1
        row.next_attempt_at = row_now + timedelta(seconds=retry_after)
        row.last_error = "rate_limited"
        await session.commit()
        logger.warning(
            "send_pending_telegram_outbox: row {} rate limited retry_after={} retry_count={}",
            row.id,
            retry_after,
            row.retry_count,
        )
        return False
    except TelegramAPIError as err:
        status_code = err.status_code
        if status_code in CHAT_FORBIDDEN_STATUSES:
            binding.is_active = False
            binding.disabled_at = row_now
            if status_code == 403:
                binding.bot_status = "kicked"
            row.status = "failed"
            row.last_error = err.description or f"forbidden:{status_code}"
            await session.commit()
            logger.warning(
                "send_pending_telegram_outbox: row {} forbidden status={}; binding disabled",
                row.id,
                status_code,
            )
            return False

        current = row.retry_count or 0
        if current >= MAX_RETRIES:
            row.status = "failed"
            row.last_error = str(err)[:500]
            await session.commit()
            logger.warning(
                "send_pending_telegram_outbox: row {} failed status={} retry_count={} (max retries)",
                row.id,
                status_code,
                current,
            )
            return False

        row.retry_count = current + 1
        backoff = DEFAULT_BACKOFF_SECONDS * (2 ** row.retry_count)
        row.status = "pending"
        row.next_attempt_at = row_now + timedelta(seconds=backoff)
        row.last_error = str(err)[:500]
        await session.commit()
        logger.warning(
            "send_pending_telegram_outbox: row {} retrying status={} retry_count={} backoff={}s",
            row.id,
            status_code,
            row.retry_count,
            backoff,
        )
        return False
    except Exception as err:
        current = row.retry_count or 0
        if current >= MAX_RETRIES:
            row.status = "failed"
            row.last_error = str(err)[:500]
            await session.commit()
            logger.exception(
                "send_pending_telegram_outbox: row {} failed (max retries)",
                row.id,
            )
            return False
        row.retry_count = current + 1
        backoff = DEFAULT_BACKOFF_SECONDS * (2 ** row.retry_count)
        row.status = "pending"
        row.next_attempt_at = row_now + timedelta(seconds=backoff)
        row.last_error = str(err)[:500]
        await session.commit()
        logger.exception(
            "send_pending_telegram_outbox: row {} unexpected error retry_count={} backoff={}s",
            row.id,
            row.retry_count,
            backoff,
        )
        return False

    row.status = "sent"
    row.sent_at = row_now
    row.last_error = None
    await session.commit()
    logger.info(
        "send_pending_telegram_outbox: row {} sent (binding {})",
        row.id,
        binding.id,
    )
    return True
