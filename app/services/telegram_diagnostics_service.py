# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""Telegram integration diagnostics service.

Aggregates safe operational health information for the Telegram integration:

* whether token / webhook secret / enabled toggle are configured
* counts of active / disabled bindings and active identities
* outbox bucket sizes (pending / sending / failed-24h / sent-24h)
* last-received webhook timestamp and last sanitized outbox error

Sensitive values (bot token, webhook secret) are NEVER returned. Error strings
are sanitized using the same regex as
:mod:`app.services.telegram_update_log_service` so a leaked token shape in
``telegram_outbox.last_error`` cannot escape through diagnostics.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    TelegramGroupBinding,
    TelegramIdentity,
    TelegramOutbox,
    TelegramUpdateLog,
)
from app.services.config_service import ConfigService
from app.services.telegram_update_log_service import _sanitize

_KEY_ENABLED = "telegram_enabled"
_KEY_BOT_TOKEN = "telegram_bot_token"
_KEY_WEBHOOK_SECRET = "telegram_webhook_secret"
_KEY_BOT_USERNAME = "telegram_bot_username"
_KEY_WEBHOOK_LAST_SET_AT = "telegram_webhook_last_set_at"


def _truthy(raw: Optional[str]) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_iso(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        logger.warning("telegram_diagnostics: invalid stored datetime value")
        return None


async def collect_diagnostics(session: AsyncSession) -> dict[str, Any]:
    """Collect operational diagnostics for the Telegram integration.

    The service NEVER returns the bot token, webhook secret, or any other
    sensitive value. Error strings are sanitized using the shared
    token-shape regex from ``telegram_update_log_service``.
    """
    svc = ConfigService(session)
    bot_token = await svc.get(_KEY_BOT_TOKEN)
    webhook_secret = await svc.get(_KEY_WEBHOOK_SECRET)
    enabled_raw = await svc.get(_KEY_ENABLED)
    bot_username = await svc.get(_KEY_BOT_USERNAME)
    webhook_last_set_raw = await svc.get(_KEY_WEBHOOK_LAST_SET_AT)

    configured = bool(bot_token) and bool(webhook_secret)
    enabled = _truthy(enabled_raw)
    webhook_last_set_at = _parse_iso(webhook_last_set_raw)

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    active_bindings = await session.scalar(
        select(func.count())
        .select_from(TelegramGroupBinding)
        .where(TelegramGroupBinding.is_active.is_(True))
    ) or 0
    disabled_bindings = await session.scalar(
        select(func.count())
        .select_from(TelegramGroupBinding)
        .where(TelegramGroupBinding.is_active.is_(False))
    ) or 0
    active_identities = await session.scalar(
        select(func.count())
        .select_from(TelegramIdentity)
        .where(TelegramIdentity.is_active.is_(True))
    ) or 0

    outbox_pending = await session.scalar(
        select(func.count())
        .select_from(TelegramOutbox)
        .where(TelegramOutbox.status == "pending")
    ) or 0
    outbox_sending = await session.scalar(
        select(func.count())
        .select_from(TelegramOutbox)
        .where(TelegramOutbox.status == "sending")
    ) or 0
    outbox_failed_last_24h = await session.scalar(
        select(func.count())
        .select_from(TelegramOutbox)
        .where(
            TelegramOutbox.status == "failed",
            TelegramOutbox.last_attempted_at.is_not(None),
            TelegramOutbox.last_attempted_at >= cutoff_24h,
        )
    ) or 0
    outbox_sent_last_24h = await session.scalar(
        select(func.count())
        .select_from(TelegramOutbox)
        .where(
            TelegramOutbox.status == "sent",
            TelegramOutbox.sent_at.is_not(None),
            TelegramOutbox.sent_at >= cutoff_24h,
        )
    ) or 0

    last_webhook_received_at = await session.scalar(
        select(func.max(TelegramUpdateLog.received_at))
    )

    last_error_row = (
        await session.execute(
            select(TelegramOutbox.last_error, TelegramOutbox.last_attempted_at)
            .where(
                TelegramOutbox.status == "failed",
                TelegramOutbox.last_error.is_not(None),
                TelegramOutbox.last_attempted_at.is_not(None),
                TelegramOutbox.last_attempted_at >= cutoff_24h,
            )
            .order_by(TelegramOutbox.last_attempted_at.desc())
            .limit(1)
        )
    ).first()

    last_outbox_error: Optional[str] = None
    last_outbox_error_at: Optional[datetime] = None
    if last_error_row is not None:
        raw_error, attempted_at = last_error_row
        if raw_error is not None:
            last_outbox_error = _sanitize(str(raw_error))
        last_outbox_error_at = attempted_at

    diagnostics: dict[str, Any] = {
        "configured": configured,
        "enabled": enabled,
        "bot_username": bot_username or None,
        "webhook_last_set_at": webhook_last_set_at,
        "active_bindings": int(active_bindings),
        "disabled_bindings": int(disabled_bindings),
        "active_identities": int(active_identities),
        "outbox_pending": int(outbox_pending),
        "outbox_sending": int(outbox_sending),
        "outbox_failed_last_24h": int(outbox_failed_last_24h),
        "outbox_sent_last_24h": int(outbox_sent_last_24h),
        "last_webhook_received_at": last_webhook_received_at,
        "last_outbox_error": last_outbox_error,
        "last_outbox_error_at": last_outbox_error_at,
    }

    logger.info(
        "telegram_diagnostics.collected configured={} enabled={} "
        "active_bindings={} outbox_pending={} outbox_failed_24h={}",
        configured,
        enabled,
        diagnostics["active_bindings"],
        diagnostics["outbox_pending"],
        diagnostics["outbox_failed_last_24h"],
    )
    return diagnostics
