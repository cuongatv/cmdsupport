# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
from __future__ import annotations

import hmac
from datetime import datetime, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import TelegramGroupBinding
from app.integrations.telegram.parser import CommandKind, ParsedCommand, parse_message
from app.services import (
    telegram_binding_service,
    telegram_command_service,
    telegram_identity_service,
    telegram_outbox_service,
    telegram_update_log_service,
)
from app.services.config_service import ConfigService
from app.services.telegram_update_log_service import DuplicateTelegramUpdate

router = APIRouter(prefix="/integrations/telegram")

_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
_ACK: dict[str, bool] = {"ok": True}


@router.post("/webhook")
async def telegram_webhook_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret_header: str | None = Header(
        default=None,
        alias=_SECRET_HEADER,
    ),
) -> dict[str, bool]:
    """Receive Telegram webhook updates and enqueue command replies.

    The secret-token check is the only HTTP-auth boundary. After it succeeds,
    every path returns 200 so Telegram does not retry-storm on internal errors.
    """
    configured_secret = await ConfigService(db).get("telegram_webhook_secret")
    if not configured_secret or not secret_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid secret",
        )
    if not hmac.compare_digest(secret_header, configured_secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid secret",
        )

    log_id: Any | None = None
    try:
        payload = await _read_json_dict(request)
        update_id = _optional_int(payload.get("update_id"))
        if update_id is None:
            return _ACK

        message = _dict_or_none(payload.get("message"))
        chat_id, message_thread_id, telegram_user_id, command = _log_context(payload)
        log = await telegram_update_log_service.record_received(
            db,
            update_id=update_id,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
            telegram_user_id=telegram_user_id,
            command=command,
            sanitized_meta=_sanitized_meta(payload),
        )
        log_id = log.id

        if message is not None:
            await _handle_message_update(
                db,
                log_id=log.id,
                update_id=update_id,
                message=message,
            )
        else:
            await _handle_non_message_update(db, log_id=log.id, update=payload)

        await db.commit()
        return _ACK
    except DuplicateTelegramUpdate:
        return _ACK
    except Exception as exc:
        logger.warning(
            "Telegram webhook processing failed after secret validation: error_type={}",
            type(exc).__name__,
        )
        if log_id is not None:
            await _mark_failed_and_commit(db, log_id=log_id, exc=exc)
        else:
            await db.rollback()
        return _ACK


async def _read_json_dict(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return cast(dict[str, Any], payload)


def _dict_or_none(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, Any], value)


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _log_context(
    payload: dict[str, Any],
) -> tuple[int | None, int | None, int | None, str | None]:
    message = _dict_or_none(payload.get("message"))
    if message is not None:
        chat = _dict_or_none(message.get("chat"))
        sender = _dict_or_none(message.get("from"))
        text = _optional_str(message.get("text"))
        return (
            _optional_int(chat.get("id")) if chat is not None else None,
            _optional_int(message.get("message_thread_id")),
            _optional_int(sender.get("id")) if sender is not None else None,
            _first_command(text),
        )

    member_update = _dict_or_none(payload.get("my_chat_member"))
    if member_update is not None:
        chat = _dict_or_none(member_update.get("chat"))
        sender = _dict_or_none(member_update.get("from"))
        return (
            _optional_int(chat.get("id")) if chat is not None else None,
            None,
            _optional_int(sender.get("id")) if sender is not None else None,
            None,
        )

    return None, None, None, None


def _first_command(text: str | None) -> str | None:
    if not text or not text.startswith("/"):
        return None
    return text.split(maxsplit=1)[0]


def _sanitized_meta(payload: dict[str, Any]) -> dict[str, Any]:
    kinds = [key for key in ("message", "my_chat_member") if key in payload]
    return {"update_kind": kinds[0] if kinds else "unsupported"}


async def _handle_message_update(
    session: AsyncSession,
    *,
    log_id: Any,
    update_id: int,
    message: dict[str, Any],
) -> None:
    context = _message_context(message)
    if context.chat_id is None:
        await telegram_update_log_service.mark_ignored(
            session,
            log_id=log_id,
            reason="missing_chat_id",
        )
        return

    if context.migrate_to_chat_id is not None:
        migrated = await telegram_binding_service.handle_chat_migration(
            session,
            from_chat_id=context.chat_id,
            to_chat_id=context.migrate_to_chat_id,
        )
        if migrated is None:
            await telegram_update_log_service.mark_ignored(
                session,
                log_id=log_id,
                reason="migration_binding_not_found",
            )
            return
        await telegram_update_log_service.mark_processed(
            session,
            log_id=log_id,
            binding_id=migrated.id,
        )
        return

    if context.telegram_user_id is None:
        await telegram_update_log_service.mark_ignored(
            session,
            log_id=log_id,
            reason="missing_sender_id",
        )
        return

    bot_username = await ConfigService(session).get("telegram_bot_username")
    parsed = parse_message(message, bot_username=bot_username)
    reply = await telegram_command_service.handle_command(
        session,
        parsed=parsed,
        chat_id=context.chat_id,
        message_thread_id=context.message_thread_id,
        telegram_user_id=context.telegram_user_id,
        telegram_username=context.telegram_username,
        display_name=context.display_name,
        message_id=context.message_id,
        update_id=update_id,
    )
    binding = await telegram_binding_service.find_active_binding(
        session,
        chat_id=context.chat_id,
        message_thread_id=context.message_thread_id,
    )
    identity = await telegram_identity_service.find_identity_by_telegram_user(
        session,
        telegram_user_id=context.telegram_user_id,
    )
    if binding is not None:
        await telegram_outbox_service.enqueue_command_reply(
            session,
            binding=binding,
            text=reply.text,
            kind=_reply_kind(parsed, reply),
            idempotency_key=f"reply:{update_id}",
        )

    await telegram_update_log_service.mark_processed(
        session,
        log_id=log_id,
        binding_id=binding.id if binding is not None else None,
        identity_id=identity.id if identity is not None else None,
    )


async def _handle_non_message_update(
    session: AsyncSession,
    *,
    log_id: Any,
    update: dict[str, Any],
) -> None:
    member_update = _dict_or_none(update.get("my_chat_member"))
    if member_update is None:
        await telegram_update_log_service.mark_ignored(
            session,
            log_id=log_id,
            reason="unsupported_update_kind",
        )
        return

    chat = _dict_or_none(member_update.get("chat"))
    chat_id = _optional_int(chat.get("id")) if chat is not None else None
    new_chat_member = _dict_or_none(member_update.get("new_chat_member"))
    status_value = (
        _optional_str(new_chat_member.get("status"))
        if new_chat_member is not None
        else None
    )
    migrate_to_chat_id = _optional_int(member_update.get("migrate_to_chat_id"))
    if chat_id is not None and migrate_to_chat_id is not None:
        migrated = await telegram_binding_service.handle_chat_migration(
            session,
            from_chat_id=chat_id,
            to_chat_id=migrate_to_chat_id,
        )
        if migrated is None:
            await telegram_update_log_service.mark_ignored(
                session,
                log_id=log_id,
                reason="migration_binding_not_found",
            )
            return
        await telegram_update_log_service.mark_processed(
            session,
            log_id=log_id,
            binding_id=migrated.id,
        )
        return

    if chat_id is None or status_value not in {"kicked", "left"}:
        await telegram_update_log_service.mark_ignored(
            session,
            log_id=log_id,
            reason="unsupported_update_kind",
        )
        return

    binding = await _disable_binding_for_bot_status(
        session,
        chat_id=chat_id,
        bot_status=status_value,
    )
    if binding is None:
        await telegram_update_log_service.mark_ignored(
            session,
            log_id=log_id,
            reason="bot_status_binding_not_found",
        )
        return

    await telegram_update_log_service.mark_processed(
        session,
        log_id=log_id,
        binding_id=binding.id,
    )


async def _disable_binding_for_bot_status(
    session: AsyncSession,
    *,
    chat_id: int,
    bot_status: str,
) -> TelegramGroupBinding | None:
    binding = await session.scalar(
        select(TelegramGroupBinding).where(
            TelegramGroupBinding.chat_id == chat_id,
            TelegramGroupBinding.is_active.is_(True),
        )
    )
    if binding is None:
        return None

    binding.bot_status = bot_status
    binding.is_active = False
    binding.disabled_at = datetime.now(timezone.utc)
    await session.flush()
    logger.info(
        "Telegram binding {} disabled after bot membership status {}",
        binding.id,
        bot_status,
    )
    return binding


def _reply_kind(
    parsed: ParsedCommand,
    reply: telegram_command_service.CommandReply,
) -> str:
    if reply.kind == telegram_command_service.REPLY_ERROR:
        return telegram_outbox_service.MESSAGE_KIND_ERROR_REPLY
    if parsed.kind == CommandKind.BIND:
        return telegram_outbox_service.MESSAGE_KIND_BIND_REPLY
    if parsed.kind == CommandKind.LINK:
        return telegram_outbox_service.MESSAGE_KIND_LINK_REPLY
    return telegram_outbox_service.MESSAGE_KIND_ERROR_REPLY


async def _mark_failed_and_commit(
    session: AsyncSession,
    *,
    log_id: Any,
    exc: Exception,
) -> None:
    try:
        await telegram_update_log_service.mark_failed(
            session,
            log_id=log_id,
            failure_reason=f"{type(exc).__name__}: {str(exc)[:500]}",
        )
        await session.commit()
    except Exception:
        await session.rollback()
        logger.warning("Could not mark Telegram webhook update failed")


class _MessageContext:
    def __init__(
        self,
        *,
        chat_id: int | None,
        message_thread_id: int | None,
        telegram_user_id: int | None,
        telegram_username: str | None,
        display_name: str | None,
        message_id: int | None,
        migrate_to_chat_id: int | None,
    ) -> None:
        self.chat_id = chat_id
        self.message_thread_id = message_thread_id
        self.telegram_user_id = telegram_user_id
        self.telegram_username = telegram_username
        self.display_name = display_name
        self.message_id = message_id
        self.migrate_to_chat_id = migrate_to_chat_id


def _message_context(message: dict[str, Any]) -> _MessageContext:
    chat = _dict_or_none(message.get("chat"))
    sender = _dict_or_none(message.get("from"))
    first_name = _optional_str(sender.get("first_name")) if sender is not None else None
    return _MessageContext(
        chat_id=_optional_int(chat.get("id")) if chat is not None else None,
        message_thread_id=_optional_int(message.get("message_thread_id")),
        telegram_user_id=_optional_int(sender.get("id")) if sender is not None else None,
        telegram_username=(
            _optional_str(sender.get("username")) if sender is not None else None
        ),
        display_name=first_name,
        message_id=_optional_int(message.get("message_id")),
        migrate_to_chat_id=_optional_int(message.get("migrate_to_chat_id")),
    )
