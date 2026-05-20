# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""Same lifecycle as ``test_telegram_lifecycle.py`` plus the outbox sender.

After the same setup walk-through, the test invokes
``send_pending_telegram_outbox`` with a :class:`FakeTelegramClient` so every
pending row transitions to ``status='sent'``. The fake records the chat_ids
it was asked to send to; we assert each binding's chat_id is among the
recipients. No real Telegram HTTP traffic ever happens.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    MembershipRole,
    Task,
    TaskAssignee,
    TaskProject,
    TelegramGroupBinding,
    TelegramIdentity,
    TelegramOutbox,
    TelegramTaskLink,
)
from app.jobs.telegram_jobs import send_pending_telegram_outbox
from app.schemas.tasks import TaskProjectCreate
from app.services.config_service import ConfigService
from app.services.task_project_service import create_task_project
from tests.fakes.telegram_client import FakeTelegramClient

pytestmark = pytest.mark.asyncio

_WEBHOOK_URL = "/api/integrations/telegram/webhook"
_WEBHOOK_SECRET = "WHSEC"
_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
_CHAT_ID = -100_111_222_333
_BOT_USERNAME = "CMDSupportBot"
_TASK_TITLE = "Chuẩn bị báo cáo tuần"


class _ActorHolder:
    actor: Employee | None

    def __init__(self) -> None:
        self.actor = None


def _frozen_now() -> datetime:
    return datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


def _make_session_factory(session: AsyncSession):
    """Wrap ``session`` so the worker's ``async with factory()`` reuses it
    instead of opening a fresh connection."""

    @asynccontextmanager
    async def factory():
        yield session

    return factory


@pytest_asyncio.fixture
async def lifecycle_actors(db_session: AsyncSession):
    department = Department(
        name=f"Telegram Full-Send Dept {uuid.uuid4().hex[:8]}"
    )
    db_session.add(department)
    await db_session.flush()

    def _make(name: str, username: str, system_role: str = "employee") -> Employee:
        emp = Employee(
            name=name,
            email=f"{uuid.uuid4().hex[:10]}@example.test",
            username=username,
            role=system_role,
            department_id=department.id,
            is_active=True,
        )
        db_session.add(emp)
        return emp

    admin = _make("Full Send Admin", f"fs_admin_{uuid.uuid4().hex[:6]}", system_role="admin")
    lead = _make("Full Send Lead", f"fs_lead_{uuid.uuid4().hex[:6]}")
    member1 = _make("Full Send M1", f"fs_mem1_{uuid.uuid4().hex[:6]}")
    member2 = _make("Full Send M2", f"fs_mem2_{uuid.uuid4().hex[:6]}")
    await db_session.flush()

    db_session.add_all(
        [
            EmployeeDepartmentMembership(
                employee_id=lead.id,
                department_id=department.id,
                role=MembershipRole.LEAD,
                is_active=True,
                is_primary=True,
            ),
            EmployeeDepartmentMembership(
                employee_id=member1.id,
                department_id=department.id,
                role=MembershipRole.MEMBER,
                is_active=True,
                is_primary=True,
            ),
            EmployeeDepartmentMembership(
                employee_id=member2.id,
                department_id=department.id,
                role=MembershipRole.MEMBER,
                is_active=True,
                is_primary=True,
            ),
        ]
    )
    await db_session.flush()

    project = await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Full Send Default Project",
            identifier=f"FS{uuid.uuid4().hex[:3].upper()}",
            department_id=department.id,
            allow_any_employee=False,
        ),
        lead,
    )
    await db_session.flush()
    return {
        "department": department,
        "admin": admin,
        "lead": lead,
        "member1": member1,
        "member2": member2,
        "project": project,
    }


@pytest_asyncio.fixture
async def lifecycle_overrides(
    db_session: AsyncSession,
) -> AsyncIterator[_ActorHolder]:
    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    holder = _ActorHolder()

    async def _db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _user_override() -> Employee:
        actor = holder.actor
        assert actor is not None, "Test forgot to set lifecycle_actor before calling endpoint"
        return actor

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = _user_override
    try:
        yield holder
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


async def _post_webhook(
    test_client: httpx.AsyncClient,
    payload: dict[str, Any],
    *,
    secret: str = _WEBHOOK_SECRET,
) -> httpx.Response:
    return await test_client.post(
        _WEBHOOK_URL,
        json=payload,
        headers={_SECRET_HEADER: secret},
    )


def _message_update(
    *,
    update_id: int,
    text: str,
    from_user_id: int,
    from_username: str,
    chat_id: int = _CHAT_ID,
    entities: list[dict[str, Any]] | None = None,
    message_id: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "update_id": update_id,
        "message": {
            "message_id": message_id if message_id is not None else update_id,
            "date": 1_700_000_000,
            "chat": {"id": chat_id, "title": "Full Send Group", "type": "supergroup"},
            "from": {
                "id": from_user_id,
                "is_bot": False,
                "username": from_username,
                "first_name": from_username,
            },
            "text": text,
        },
    }
    if entities is not None:
        payload["message"]["entities"] = entities
    return payload


async def test_full_lifecycle_then_outbox_sender_drains_to_fake_client(
    test_client: httpx.AsyncClient,
    db_session: AsyncSession,
    lifecycle_actors: dict[str, Any],
    lifecycle_overrides: _ActorHolder,
) -> None:
    actors = lifecycle_actors
    holder = lifecycle_overrides
    department: Department = actors["department"]
    admin: Employee = actors["admin"]
    lead: Employee = actors["lead"]
    member1: Employee = actors["member1"]
    member2: Employee = actors["member2"]
    project: TaskProject = actors["project"]

    member1_tg_user_id = 800_000_001
    member2_tg_user_id = 800_000_002
    member1_tg_username = f"fs_member1_{uuid.uuid4().hex[:6]}"
    member2_tg_username = f"fs_member2_{uuid.uuid4().hex[:6]}"

    # 1. Admin settings.
    holder.actor = admin
    settings_resp = await test_client.put(
        "/api/admin/telegram/settings",
        json={
            "is_enabled": True,
            "bot_token": "BOT:FAKE",
            "webhook_secret": _WEBHOOK_SECRET,
            "webhook_url": "https://example/api/integrations/telegram/webhook",
            "bot_username": _BOT_USERNAME,
        },
    )
    assert settings_resp.status_code == 200, settings_resp.text

    # 2. Lead generates a bind code.
    holder.actor = lead
    bind_resp = await test_client.post(
        "/api/telegram/bindings",
        json={
            "department_id": str(department.id),
            "default_task_project_id": str(project.id),
        },
    )
    assert bind_resp.status_code == 201, bind_resp.text
    bind_code: str = bind_resp.json()["bind_code"]
    binding_id = uuid.UUID(bind_resp.json()["id"])

    # 3. /bind activates.
    resp = await _post_webhook(
        test_client,
        _message_update(
            update_id=2001,
            text=f"/bind {bind_code}",
            from_user_id=950_000_001,
            from_username="bind_runner",
            entities=[{"type": "bot_command", "offset": 0, "length": 5}],
        ),
    )
    assert resp.status_code == 200, resp.text

    binding = await db_session.get(TelegramGroupBinding, binding_id)
    assert binding is not None
    assert binding.is_active is True
    assert binding.chat_id == _CHAT_ID

    # 4. Members generate link codes.
    holder.actor = member1
    link1_resp = await test_client.post("/api/telegram/identities/link-codes")
    assert link1_resp.status_code == 201, link1_resp.text
    link1_code: str = link1_resp.json()["link_code"]

    holder.actor = member2
    link2_resp = await test_client.post("/api/telegram/identities/link-codes")
    assert link2_resp.status_code == 201, link2_resp.text
    link2_code: str = link2_resp.json()["link_code"]

    # 5. /link activates each identity.
    resp = await _post_webhook(
        test_client,
        _message_update(
            update_id=2101,
            text=f"/link {link1_code}",
            from_user_id=member1_tg_user_id,
            from_username=member1_tg_username,
            entities=[{"type": "bot_command", "offset": 0, "length": 5}],
        ),
    )
    assert resp.status_code == 200, resp.text
    resp = await _post_webhook(
        test_client,
        _message_update(
            update_id=2102,
            text=f"/link {link2_code}",
            from_user_id=member2_tg_user_id,
            from_username=member2_tg_username,
            entities=[{"type": "bot_command", "offset": 0, "length": 5}],
        ),
    )
    assert resp.status_code == 200, resp.text

    assert await db_session.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.employee_id == member1.id,
            TelegramIdentity.is_active.is_(True),
        )
    ) is not None
    assert await db_session.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.employee_id == member2.id,
            TelegramIdentity.is_active.is_(True),
        )
    ) is not None

    # 6. /task creates a Task assigned to member2.
    task_text = f"/task @{member2_tg_username} {_TASK_TITLE}"
    mention_offset = len("/task ")
    mention_length = len(member2_tg_username) + 1
    resp = await _post_webhook(
        test_client,
        _message_update(
            update_id=2200,
            text=task_text,
            from_user_id=member1_tg_user_id,
            from_username=member1_tg_username,
            entities=[
                {"type": "bot_command", "offset": 0, "length": 5},
                {
                    "type": "mention",
                    "offset": mention_offset,
                    "length": mention_length,
                },
            ],
            message_id=6500,
        ),
    )
    assert resp.status_code == 200, resp.text

    created_task = await db_session.scalar(
        select(Task).where(
            Task.task_project_id == project.id,
            Task.title == _TASK_TITLE,
        )
    )
    assert created_task is not None
    assignees = list(
        (
            await db_session.execute(
                select(TaskAssignee).where(TaskAssignee.task_id == created_task.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(assignees) == 1
    assert assignees[0].employee_id == member2.id
    assert await db_session.scalar(
        select(TelegramTaskLink).where(TelegramTaskLink.task_id == created_task.id)
    ) is not None

    # -------- Now run the outbox sender against a FakeTelegramClient --------
    pending_before = list(
        (
            await db_session.execute(
                select(TelegramOutbox).where(
                    TelegramOutbox.binding_id == binding.id,
                    TelegramOutbox.status == "pending",
                )
            )
        )
        .scalars()
        .all()
    )
    assert pending_before, "Expected at least one pending outbox row for the bind reply"
    expected_chat_ids = {row.payload.get("chat_id") for row in pending_before}
    assert binding.chat_id in expected_chat_ids

    # ConfigService stores the bot token under this key. The Admin PUT above
    # already wrote ``telegram_bot_token``; reassert here so the assertion is
    # explicit (an env mistake would otherwise show up as the worker
    # short-circuiting and returning 0).
    stored_token = await ConfigService(db_session).get("telegram_bot_token")
    assert stored_token == "BOT:FAKE"

    fake = FakeTelegramClient()
    sent_count = await send_pending_telegram_outbox(
        {},
        client_factory=lambda _token: fake,
        session_factory=_make_session_factory(db_session),
        now=_frozen_now,
    )

    assert sent_count == len(pending_before)
    assert len(fake.sent) == sent_count
    # The fake recorded one call per pending row, each addressed to one of
    # the chat_ids we observed in the pending payloads.
    sent_chat_ids = {record["chat_id"] for record in fake.sent}
    assert sent_chat_ids == expected_chat_ids
    assert binding.chat_id in sent_chat_ids

    # Every row that started ``pending`` is now ``sent``.
    after = list(
        (
            await db_session.execute(
                select(TelegramOutbox).where(
                    TelegramOutbox.id.in_([row.id for row in pending_before])
                )
            )
        )
        .scalars()
        .all()
    )
    assert {row.status for row in after} == {"sent"}
    assert all(row.sent_at is not None for row in after)
    assert all(row.last_error is None for row in after)
