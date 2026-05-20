"""Telegram integration schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TelegramIntegrationStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    is_enabled: bool
    bot_token_configured: bool
    webhook_secret_configured: bool
    webhook_url: Optional[str] = None
    bot_username: Optional[str] = None
    webhook_last_set_at: Optional[datetime] = None


class TelegramSettingsUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    bot_token: Optional[str] = None
    webhook_secret: Optional[str] = None
    webhook_url: Optional[str] = None
    bot_username: Optional[str] = None


class TelegramBindingResponse(BaseModel):
    """Public-safe view of a :class:`TelegramGroupBinding`.

    ``chat_id`` is exposed because it is not a secret; the bot has to be
    invited to the chat explicitly anyway. The ``bind_code`` IS returned —
    it is a single-use setup code that the requester needs to paste into
    Telegram. It is not secret like the bot token.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    department_id: uuid.UUID
    default_task_project_id: Optional[uuid.UUID] = None
    chat_id: int
    message_thread_id: Optional[int] = None
    chat_title: Optional[str] = None
    is_active: bool
    bot_status: Optional[str] = None
    bind_code: Optional[str] = None
    bind_code_expires_at: Optional[datetime] = None
    bound_at: Optional[datetime] = None
    disabled_at: Optional[datetime] = None
    created_at: datetime


class BindCodeCreateRequest(BaseModel):
    """Payload for ``POST /api/telegram/bindings``."""

    department_id: uuid.UUID
    default_task_project_id: Optional[uuid.UUID] = None


class TelegramIdentityResponse(BaseModel):
    """Public-safe view of a :class:`TelegramIdentity`.

    The raw ``telegram_user_id`` is intentionally NOT exposed; we only return
    display-grade fields. The ``link_code`` is also stripped from this view —
    it is returned exactly once via :class:`LinkCodeResponse`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    telegram_username: Optional[str] = None
    display_name: Optional[str] = None
    is_active: bool
    linked_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None


class LinkCodeResponse(BaseModel):
    """One-time setup response for ``POST /api/telegram/identities/link-codes``."""

    link_code: str
    expires_at: datetime


class TelegramDiagnostics(BaseModel):
    """Safe operational diagnostics for the Telegram integration.

    NEVER carries the bot token or webhook secret. Error strings are
    sanitized in the service layer before reaching this DTO.
    """

    model_config = ConfigDict(from_attributes=True)

    configured: bool
    enabled: bool
    bot_username: Optional[str] = None
    webhook_last_set_at: Optional[datetime] = None
    active_bindings: int
    disabled_bindings: int
    active_identities: int
    outbox_pending: int
    outbox_sending: int
    outbox_failed_last_24h: int
    outbox_sent_last_24h: int
    last_webhook_received_at: Optional[datetime] = None
    last_outbox_error: Optional[str] = None
    last_outbox_error_at: Optional[datetime] = None
