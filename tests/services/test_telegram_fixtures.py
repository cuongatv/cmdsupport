# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.database.models import (
    EmployeeDepartmentMembership,
    TelegramGroupBinding,
    TelegramIdentity,
)
from tests.fakes.telegram_client import FakeTelegramClient, TelegramRateLimitError
from tests.fixtures.telegram import BoundTelegramGroupFixture

pytestmark = pytest.mark.asyncio


async def test_bound_telegram_group_creates_active_binding_memberships_and_identities(
    db_session,
    bound_telegram_group: BoundTelegramGroupFixture,
):
    binding_count = (
        await db_session.execute(
            select(func.count()).select_from(TelegramGroupBinding).where(
                TelegramGroupBinding.department_id == bound_telegram_group.department.id,
                TelegramGroupBinding.is_active.is_(True),
            )
        )
    ).scalar_one()
    membership_count = (
        await db_session.execute(
            select(func.count()).select_from(EmployeeDepartmentMembership).where(
                EmployeeDepartmentMembership.department_id
                == bound_telegram_group.department.id,
                EmployeeDepartmentMembership.is_active.is_(True),
            )
        )
    ).scalar_one()
    identity_count = (
        await db_session.execute(
            select(func.count()).select_from(TelegramIdentity).where(
                TelegramIdentity.employee_id.in_(
                    [bound_telegram_group.lead.id, bound_telegram_group.member.id]
                ),
                TelegramIdentity.is_active.is_(True),
            )
        )
    ).scalar_one()

    assert binding_count == 1
    assert membership_count == 2
    assert identity_count == 2
    assert isinstance(bound_telegram_group.binding.chat_id, int)
    assert bound_telegram_group.binding.chat_id < 0
    assert (
        bound_telegram_group.binding.default_task_project_id
        == bound_telegram_group.project.id
    )


async def test_fake_telegram_client_records_sent_messages():
    client = FakeTelegramClient()

    response = await client.send_message(
        chat_id=-1000000000001,
        text="hello telegram",
        parse_mode="HTML",
        message_thread_id=12,
    )

    assert response == {"ok": True, "result": {"message_id": 1}}
    assert client.sent == [
        {
            "chat_id": -1000000000001,
            "text": "hello telegram",
            "parse_mode": "HTML",
            "message_thread_id": 12,
            "message_id": 1,
            "response_status": 200,
        }
    ]


async def test_fake_telegram_client_raises_rate_limit_error():
    client = FakeTelegramClient(retry_after=11)

    with pytest.raises(TelegramRateLimitError) as exc_info:
        await client.send_message(chat_id=-1000000000002, text="retry later")

    assert exc_info.value.retry_after == 11
    assert client.sent == []
