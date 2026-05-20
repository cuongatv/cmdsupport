# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""Unit tests for :mod:`app.services.telegram_diagnostics_service`."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.database.models import TelegramOutbox
from app.services.telegram_diagnostics_service import collect_diagnostics

pytestmark = pytest.mark.asyncio


async def test_collect_diagnostics_with_no_data(db_session):
    """Empty DB returns configured=False and all counts at zero."""
    data = await collect_diagnostics(db_session)

    assert data["configured"] is False
    assert data["enabled"] is False
    assert data["bot_username"] is None
    assert data["webhook_last_set_at"] is None
    assert data["active_bindings"] == 0
    assert data["disabled_bindings"] == 0
    assert data["active_identities"] == 0
    assert data["outbox_pending"] == 0
    assert data["outbox_sending"] == 0
    assert data["outbox_failed_last_24h"] == 0
    assert data["outbox_sent_last_24h"] == 0
    assert data["last_webhook_received_at"] is None
    assert data["last_outbox_error"] is None
    assert data["last_outbox_error_at"] is None


async def test_collect_diagnostics_counts_active_and_disabled_bindings(
    db_session,
    bound_telegram_group,
    department_factory,
):
    """A second disabled binding adds to disabled_bindings only."""
    from app.database.models import TelegramGroupBinding

    other_dept = await department_factory(name="Telegram Disabled Department")
    disabled = TelegramGroupBinding(
        department_id=other_dept.id,
        chat_id=-100_000_000_999,
        is_active=False,
    )
    db_session.add(disabled)
    await db_session.flush()

    data = await collect_diagnostics(db_session)

    assert data["active_bindings"] == 1
    assert data["disabled_bindings"] == 1
    assert data["active_identities"] == 2


async def test_collect_diagnostics_counts_outbox_buckets(
    db_session, bound_telegram_group
):
    """Outbox buckets reflect pending/sending/failed-24h/sent-24h status."""
    binding = bound_telegram_group.binding
    now = datetime.now(timezone.utc)
    older = now - timedelta(hours=48)
    recent = now - timedelta(minutes=10)

    rows = [
        TelegramOutbox(
            binding_id=binding.id,
            message_kind="task_created",
            idempotency_key="diag:pending:1",
            payload={"chat_id": binding.chat_id, "text": "p1"},
            status="pending",
        ),
        TelegramOutbox(
            binding_id=binding.id,
            message_kind="task_created",
            idempotency_key="diag:pending:2",
            payload={"chat_id": binding.chat_id, "text": "p2"},
            status="pending",
        ),
        TelegramOutbox(
            binding_id=binding.id,
            message_kind="task_created",
            idempotency_key="diag:sending:1",
            payload={"chat_id": binding.chat_id, "text": "s1"},
            status="sending",
        ),
        TelegramOutbox(
            binding_id=binding.id,
            message_kind="task_created",
            idempotency_key="diag:failed:recent",
            payload={"chat_id": binding.chat_id, "text": "f1"},
            status="failed",
            last_attempted_at=recent,
            last_error="rate_limited",
        ),
        TelegramOutbox(
            binding_id=binding.id,
            message_kind="task_created",
            idempotency_key="diag:failed:old",
            payload={"chat_id": binding.chat_id, "text": "f2"},
            status="failed",
            last_attempted_at=older,
            last_error="old failure",
        ),
        TelegramOutbox(
            binding_id=binding.id,
            message_kind="task_created",
            idempotency_key="diag:sent:recent",
            payload={"chat_id": binding.chat_id, "text": "ok1"},
            status="sent",
            sent_at=recent,
        ),
        TelegramOutbox(
            binding_id=binding.id,
            message_kind="task_created",
            idempotency_key="diag:sent:old",
            payload={"chat_id": binding.chat_id, "text": "ok2"},
            status="sent",
            sent_at=older,
        ),
    ]
    db_session.add_all(rows)
    await db_session.flush()

    data = await collect_diagnostics(db_session)

    assert data["outbox_pending"] == 2
    assert data["outbox_sending"] == 1
    assert data["outbox_failed_last_24h"] == 1
    assert data["outbox_sent_last_24h"] == 1


async def test_last_outbox_error_sanitizes_token_shape(
    db_session, bound_telegram_group
):
    """Last outbox error sanitizes Telegram bot-token shape via shared regex."""
    binding = bound_telegram_group.binding
    now = datetime.now(timezone.utc)
    leaky_error = (
        "boom 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 something"
    )

    row = TelegramOutbox(
        binding_id=binding.id,
        message_kind="task_created",
        idempotency_key="diag:leaky-error",
        payload={"chat_id": binding.chat_id, "text": "x"},
        status="failed",
        last_attempted_at=now - timedelta(minutes=1),
        last_error=leaky_error,
    )
    db_session.add(row)
    await db_session.flush()

    data = await collect_diagnostics(db_session)

    assert data["last_outbox_error"] is not None
    assert "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in data[
        "last_outbox_error"
    ]
    assert "***" in data["last_outbox_error"]
    assert data["last_outbox_error_at"] is not None
