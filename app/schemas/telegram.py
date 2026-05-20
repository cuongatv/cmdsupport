"""Telegram integration schemas."""

from __future__ import annotations

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
