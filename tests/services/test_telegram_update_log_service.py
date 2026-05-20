# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.database.models import AuditLog, TelegramUpdateLog
from app.services.telegram_update_log_service import (
    DuplicateTelegramUpdate,
    mark_failed,
    mark_ignored,
    mark_processed,
    record_received,
    write_audit,
)

pytestmark = pytest.mark.asyncio


async def _fetch_update_log(db_session, update_log_id: uuid.UUID) -> TelegramUpdateLog:
    result = await db_session.execute(
        select(TelegramUpdateLog).where(TelegramUpdateLog.id == update_log_id)
    )
    row = result.scalar_one()
    return row


async def test_record_received_creates_row_with_status_pending(db_session):
    log = await record_received(
        db_session,
        update_id=101,
        chat_id=-100_000_000_001,
        message_thread_id=55,
        telegram_user_id=424242,
        command="/start",
        sanitized_meta={"source": "webhook"},
    )

    assert log.update_id == 101
    assert log.status == "pending"
    assert log.chat_id == -100_000_000_001
    assert log.message_thread_id == 55
    assert log.telegram_user_id == 424242
    assert log.command == "/start"
    assert log.sanitized_meta == {"source": "webhook"}
    assert log.received_at is not None

    fetched = await _fetch_update_log(db_session, log.id)
    assert fetched.status == "pending"


async def test_record_received_duplicate_raises(db_session):
    first = await record_received(
        db_session,
        update_id=202,
        chat_id=-100_000_000_002,
        message_thread_id=None,
        telegram_user_id=None,
        command=None,
        sanitized_meta={"kind": "plain"},
    )
    assert first.status == "pending"

    with pytest.raises(DuplicateTelegramUpdate):
        await record_received(
            db_session,
            update_id=202,
            chat_id=-100_000_000_002,
            message_thread_id=None,
            telegram_user_id=None,
            command=None,
            sanitized_meta={"kind": "plain"},
        )

    result = await db_session.execute(
        select(TelegramUpdateLog).where(TelegramUpdateLog.update_id == 202)
    )
    rows = list(result.scalars().all())
    assert len(rows) == 1


async def test_mark_processed_sets_status_and_processed_at_and_binding(db_session):
    log = await record_received(
        db_session,
        update_id=303,
        chat_id=-100_000_000_003,
        message_thread_id=7,
        telegram_user_id=123456,
        command="/create",
        sanitized_meta={"kind": "command"},
    )
    binding_id = uuid.uuid4()
    identity_id = uuid.uuid4()

    await mark_processed(
        db_session,
        log_id=log.id,
        binding_id=binding_id,
        identity_id=identity_id,
    )

    fetched = await _fetch_update_log(db_session, log.id)
    assert fetched.status == "processed"
    assert fetched.processed_at is not None
    assert fetched.binding_id == binding_id
    assert fetched.identity_id == identity_id


async def test_mark_failed_sanitizes_token_lookalike(db_session):
    log = await record_received(
        db_session,
        update_id=404,
        chat_id=-100_000_000_004,
        message_thread_id=None,
        telegram_user_id=999,
        command="/fail",
        sanitized_meta={"kind": "failure"},
    )

    await mark_failed(
        db_session,
        log_id=log.id,
        failure_reason="Webhook error: 123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890 leaked",
    )

    fetched = await _fetch_update_log(db_session, log.id)
    assert fetched.status == "failed"
    assert fetched.processed_at is not None
    assert "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890" not in (fetched.failure_reason or "")
    assert "***" in (fetched.failure_reason or "")


async def test_mark_ignored_sets_status_and_reason(db_session):
    log = await record_received(
        db_session,
        update_id=505,
        chat_id=-100_000_000_005,
        message_thread_id=None,
        telegram_user_id=111,
        command=None,
        sanitized_meta={"kind": "text"},
    )

    await mark_ignored(
        db_session,
        log_id=log.id,
        reason="plain text without command",
    )

    fetched = await _fetch_update_log(db_session, log.id)
    assert fetched.status == "ignored"
    assert fetched.processed_at is not None
    assert fetched.failure_reason == "plain text without command"


async def test_write_audit_persists_row(db_session):
    employee_id = uuid.uuid4()
    entry = await write_audit(
        db_session,
        employee_id=employee_id,
        action="telegram.process",
        target_type="telegram_update",
        target_id=uuid.uuid4(),
        metadata={"update_id": 606, "status": "processed"},
    )

    assert entry.id is not None
    assert entry.principal_id == employee_id
    assert entry.principal_type == "human"
    assert entry.action == "telegram.process"
    assert entry.resource_type == "telegram_update"
    assert entry.resource_id != ""
    assert entry.decision == "ALLOW"
    assert entry.metadata_ == {"update_id": 606, "status": "processed"}

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.id == entry.id)
    )
    persisted = result.scalar_one()
    assert persisted.principal_id == employee_id
    assert persisted.action == "telegram.process"
    assert persisted.resource_type == "telegram_update"
