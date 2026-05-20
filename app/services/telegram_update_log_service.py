# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AuditLog, TelegramUpdateLog

_TOKEN_RE = re.compile(r"\d+:[A-Za-z0-9_-]{30,}")
_SECRET_KEY_RE = re.compile(
    r"(?i)\b(?:"
    r"telegram_bot_token|"
    r"telegram_webhook_secret|"
    r"secret_key|"
    r"embedding_api_key|"
    r"llm_api_key|"
    r"advisor_llm_api_key|"
    r"vision_api_key|"
    r"openai_api_key|"
    r"anthropic_api_key|"
    r"google_api_key|"
    r"voyage_api_key|"
    r"cohere_api_key|"
    r"api_key|"
    r"access_token|"
    r"refresh_token|"
    r"password"
    r")\b"
)
_ANONYMOUS_PRINCIPAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


class DuplicateTelegramUpdate(Exception):
    """Raised when a Telegram webhook update has already been handled."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sanitize(text: str) -> str:
    sanitized = _TOKEN_RE.sub("***", text)
    sanitized = _SECRET_KEY_RE.sub("***", sanitized)
    return sanitized


async def record_received(
    session: AsyncSession,
    *,
    update_id: int,
    chat_id: int | None,
    message_thread_id: int | None,
    telegram_user_id: int | None,
    command: str | None,
    sanitized_meta: dict[str, Any],
) -> TelegramUpdateLog:
    """Insert a pending Telegram update log row, or raise on duplicate."""
    stmt = (
        insert(TelegramUpdateLog)
        .values(
            update_id=update_id,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
            telegram_user_id=telegram_user_id,
            command=command,
            status="pending",
            sanitized_meta=dict(sanitized_meta),
        )
        .on_conflict_do_nothing(index_elements=[TelegramUpdateLog.__table__.c.update_id])
        .returning(TelegramUpdateLog.id)
    )
    result = await session.execute(stmt)
    log_id = result.scalar_one_or_none()
    if log_id is None:
        logger.warning("Telegram update already recorded: update_id={}", update_id)
        raise DuplicateTelegramUpdate(f"Telegram update {update_id} already processed")

    log = await session.get(TelegramUpdateLog, log_id)
    if log is None:
        raise RuntimeError("telegram update log insert failed to round-trip")

    logger.info("Recorded Telegram update: update_id={} log_id={}", update_id, log_id)
    return log


async def _load_log(session: AsyncSession, log_id: uuid.UUID) -> TelegramUpdateLog:
    log = await session.get(TelegramUpdateLog, log_id)
    if log is None:
        raise ValueError(f"telegram update log not found: {log_id}")
    return log


async def mark_processed(
    session: AsyncSession,
    *,
    log_id: uuid.UUID,
    binding_id: uuid.UUID | None = None,
    identity_id: uuid.UUID | None = None,
) -> None:
    log = await _load_log(session, log_id)
    log.status = "processed"
    log.processed_at = _utcnow()
    if binding_id is not None:
        log.binding_id = binding_id
    if identity_id is not None:
        log.identity_id = identity_id
    await session.flush()
    logger.info("Marked Telegram update processed: log_id={}", log_id)


async def mark_failed(
    session: AsyncSession,
    *,
    log_id: uuid.UUID,
    failure_reason: str,
    sanitize: bool = True,
) -> None:
    log = await _load_log(session, log_id)
    log.status = "failed"
    log.processed_at = _utcnow()
    log.failure_reason = _sanitize(failure_reason) if sanitize else failure_reason
    await session.flush()
    logger.warning("Marked Telegram update failed: log_id={} reason={}", log_id, log.failure_reason)


async def mark_ignored(
    session: AsyncSession,
    *,
    log_id: uuid.UUID,
    reason: str,
) -> None:
    log = await _load_log(session, log_id)
    log.status = "ignored"
    log.processed_at = _utcnow()
    log.failure_reason = reason
    await session.flush()
    logger.info("Marked Telegram update ignored: log_id={} reason={}", log_id, reason)


async def write_audit(
    session: AsyncSession,
    *,
    employee_id: uuid.UUID | None,
    action: str,
    target_type: str,
    target_id: uuid.UUID | None,
    metadata: dict[str, Any],
) -> AuditLog:
    entry = AuditLog(
        principal_id=employee_id or _ANONYMOUS_PRINCIPAL_ID,
        principal_type="human" if employee_id is not None else "agent",
        action=action,
        resource_type=target_type,
        resource_id=str(target_id) if target_id is not None else "unknown",
        decision="ALLOW",
        reason=None,
        metadata_=dict(metadata),
    )
    session.add(entry)
    await session.flush()
    logger.info(
        "Wrote Telegram audit entry: action={} target_type={} target_id={}",
        action,
        target_type,
        entry.resource_id,
    )
    return entry
