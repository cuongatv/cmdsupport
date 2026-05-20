"""Telegram integration admin REST API.

Endpoints under ``/api/admin/telegram`` for global Telegram settings:

* ``GET  /settings`` — read current integration status (booleans only — never
  returns the raw bot token or webhook secret).
* ``PUT  /settings`` — update integration settings (token / secret /
  webhook_url / bot_username / enabled). Sensitive values are persisted
  encrypted by :class:`ConfigService` and only their *configured* status
  surfaces back through ``TelegramIntegrationStatus``.

Both endpoints require the same admin-level permission as
``app/routers/admin_settings.py`` uses for global org settings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee
from app.schemas.telegram import (
    TelegramDiagnostics,
    TelegramIntegrationStatus,
    TelegramSettingsUpdate,
)
from app.services.audit_service import log_audit
from app.services.auth_service import require_permission
from app.services.config_service import ConfigService
from app.services.telegram_diagnostics_service import collect_diagnostics

router = APIRouter(prefix="/admin/telegram", tags=["telegram-admin"])


# ---------------------------------------------------------------------------
# Config key names (centralized so routers / tests don't drift)
# ---------------------------------------------------------------------------

_KEY_ENABLED = "telegram_enabled"
_KEY_BOT_TOKEN = "telegram_bot_token"  # SENSITIVE — encrypted by ConfigService
_KEY_WEBHOOK_SECRET = "telegram_webhook_secret"  # SENSITIVE
_KEY_WEBHOOK_URL = "telegram_webhook_url"
_KEY_BOT_USERNAME = "telegram_bot_username"
_KEY_WEBHOOK_LAST_SET_AT = "telegram_webhook_last_set_at"


def _truthy(raw: Optional[str]) -> bool:
    """Tolerant bool decoder for stringly-typed config values."""
    if raw is None:
        return False
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _parse_webhook_last_set_at(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        logger.warning(
            "telegram_admin: invalid stored datetime for {} = {!r}",
            _KEY_WEBHOOK_LAST_SET_AT,
            raw,
        )
        return None


async def _read_status(svc: ConfigService) -> TelegramIntegrationStatus:
    enabled_raw = await svc.get(_KEY_ENABLED)
    bot_token = await svc.get(_KEY_BOT_TOKEN)
    webhook_secret = await svc.get(_KEY_WEBHOOK_SECRET)
    webhook_url = await svc.get(_KEY_WEBHOOK_URL)
    bot_username = await svc.get(_KEY_BOT_USERNAME)
    last_set_raw = await svc.get(_KEY_WEBHOOK_LAST_SET_AT)

    return TelegramIntegrationStatus(
        is_enabled=_truthy(enabled_raw),
        bot_token_configured=bool(bot_token),
        webhook_secret_configured=bool(webhook_secret),
        webhook_url=webhook_url or None,
        bot_username=bot_username or None,
        webhook_last_set_at=_parse_webhook_last_set_at(last_set_raw),
    )


@router.get("/settings", response_model=TelegramIntegrationStatus)
async def get_telegram_settings(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:read"),
) -> TelegramIntegrationStatus:
    """Return the current Telegram integration status.

    Never returns the raw bot token or webhook secret — only ``*_configured``
    booleans so the admin UI can render a "Token is set" badge.
    """
    svc = ConfigService(db)
    return await _read_status(svc)


@router.put("/settings", response_model=TelegramIntegrationStatus)
async def update_telegram_settings(
    body: TelegramSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("org:settings:manage"),
) -> TelegramIntegrationStatus:
    """Update Telegram integration settings.

    Only the fields present in the request body are written. The response
    NEVER includes the raw token or webhook secret — only configured booleans
    via :class:`TelegramIntegrationStatus`.
    """
    svc = ConfigService(db)
    keys_updated: list[str] = []

    if body.is_enabled is not None:
        await svc.set(_KEY_ENABLED, "true" if body.is_enabled else "false")
        keys_updated.append(_KEY_ENABLED)

    if body.bot_token is not None and body.bot_token.strip():
        await svc.set(_KEY_BOT_TOKEN, body.bot_token.strip())
        keys_updated.append(_KEY_BOT_TOKEN)

    if body.webhook_secret is not None and body.webhook_secret.strip():
        await svc.set(_KEY_WEBHOOK_SECRET, body.webhook_secret.strip())
        keys_updated.append(_KEY_WEBHOOK_SECRET)

    if body.webhook_url is not None:
        await svc.set(_KEY_WEBHOOK_URL, body.webhook_url.strip())
        keys_updated.append(_KEY_WEBHOOK_URL)

    if body.bot_username is not None:
        await svc.set(_KEY_BOT_USERNAME, body.bot_username.strip())
        keys_updated.append(_KEY_BOT_USERNAME)

    # Stamp the last webhook update marker whenever the webhook URL changes.
    if body.webhook_url is not None or body.webhook_secret is not None:
        await svc.set(
            _KEY_WEBHOOK_LAST_SET_AT,
            datetime.now(timezone.utc).isoformat(),
        )

    # Audit — log only the *names* of the keys touched, never their values.
    if keys_updated:
        await log_audit(
            db,
            user,
            "update",
            "settings",
            "telegram",
            reason=f"Updated keys: {', '.join(keys_updated)}",
        )
        logger.info(
            "telegram_admin.settings_updated employee_id={} keys={}",
            user.id,
            keys_updated,
        )

    await db.commit()
    return await _read_status(svc)


@router.get("/diagnostics", response_model=TelegramDiagnostics)
async def get_telegram_diagnostics(
    db: AsyncSession = Depends(get_db),
    _user: Employee = require_permission("org:settings:read"),
) -> TelegramDiagnostics:
    """Return safe operational diagnostics for the Telegram integration.

    Never returns the raw bot token or webhook secret. Error strings are
    sanitized in the service layer before reaching the response.
    """
    data = await collect_diagnostics(db)
    return TelegramDiagnostics(**data)
