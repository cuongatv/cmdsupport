# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false, reportUnknownArgumentType=false
"""Security + edge-case coverage for the Telegram integration.

Companion to ``tests/api/test_telegram_webhook.py`` (positive paths) and the
service-level test files. These tests focus on the security boundary:

* Webhook secret enforcement (no side effects on bad/missing secrets).
* Admin settings responses NEVER leak the bot token or webhook secret.
* Webhook idempotency on duplicate ``update_id``.
* Telegram command authorization: unlinked sender / non-member assignee.
* HTML injection in task titles is escaped before reaching the outbox.
* The bot token shape never appears in loguru records or outbox payloads.
* Telegram ``migrate_to_chat_id`` and ``my_chat_member`` lifecycle updates
  flip binding state correctly.
* ``/task`` with no title returns a validation error and creates no Task row.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from loguru import logger
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import (
    Employee,
    EmployeeDepartmentMembership,
    MembershipRole,
    Task,
    TaskState,
    TelegramGroupBinding,
    TelegramIdentity,
    TelegramOutbox,
    TelegramUpdateLog,
)
from app.integrations.telegram.client import TelegramRateLimitError
from app.jobs.telegram_jobs import send_pending_telegram_outbox
from app.services import telegram_outbox_service
from app.services.config_service import ConfigService
from tests.fakes.telegram_client import FakeTelegramClient

pytestmark = pytest.mark.asyncio

_WEBHOOK_URL = "/api/integrations/telegram/webhook"
_ADMIN_SETTINGS_URL = "/api/admin/telegram/settings"
_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

_WEBHOOK_SECRET = "telegram-sec-tests-secret"
# Token-shape value (matches the regex `\d+:[A-Za-z0-9_-]{30,}` used by the
# update-log sanitizer) but obviously not a real Telegram bot token.
_BOT_TOKEN_VALUE = "1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_TOKEN_SHAPE_RE = re.compile(r"\d+:[A-Za-z0-9_-]{30,}")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def _override_db(db_session: AsyncSession) -> AsyncIterator[None]:
    """Bind the FastAPI ``get_db`` dependency to the rollback test session."""
    from app.main import app

    async def _get_test_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def webhook_client(
    _override_db: None,
    db_session: AsyncSession,
) -> AsyncIterator[httpx.AsyncClient]:
    """ASGI client that hits the webhook endpoint with the test DB session."""
    from app.main import app

    await ConfigService(db_session).set("telegram_webhook_secret", _WEBHOOK_SECRET)
    await db_session.flush()

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


@pytest_asyncio.fixture
async def admin_employee(db_session: AsyncSession) -> Employee:
    dept_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": dept_id, "name": f"Tg Sec Admin Dept {dept_id.hex[:8]}"},
    )
    emp_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, username, role, department_id, is_active)
            VALUES (:id, :name, :email, :username, 'admin', :dept_id, true)
            """
        ),
        {
            "id": emp_id,
            "name": "Telegram Sec Admin",
            "email": f"{emp_id.hex[:12]}@example.test",
            "username": f"tg_sec_admin_{emp_id.hex[:12]}",
            "dept_id": dept_id,
        },
    )
    employee = await db_session.get(Employee, emp_id)
    assert employee is not None
    return employee


@pytest_asyncio.fixture
async def admin_client(
    db_session: AsyncSession,
    admin_employee: Employee,
) -> AsyncIterator[httpx.AsyncClient]:
    from app.main import app
    from app.services.auth_service import get_current_user

    async def _db_override() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _user_override() -> Employee:
        return admin_employee

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = _user_override

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        try:
            yield client
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


async def _post(
    client: httpx.AsyncClient,
    payload: Mapping[str, object],
    *,
    secret: str | None = _WEBHOOK_SECRET,
) -> httpx.Response:
    headers = {_SECRET_HEADER: secret} if secret is not None else {}
    return await client.post(_WEBHOOK_URL, json=payload, headers=headers)


async def _count(session: AsyncSession, model: type) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


def _wrap_session(session: AsyncSession):
    """Wrap a live session so ``send_pending_telegram_outbox`` can re-use it."""

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield session

    return factory


def _frozen_now() -> datetime:
    return datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


class _RateLimitClient(FakeTelegramClient):
    """Raises the real :class:`TelegramRateLimitError` so the worker's
    rate-limit branch executes."""

    def __init__(self, retry_after: int) -> None:
        super().__init__()
        self._retry_after = retry_after

    async def send_message(  # type: ignore[override]
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        message_thread_id: int | None = None,
    ) -> dict[str, object]:
        raise TelegramRateLimitError(self._retry_after)


# ---------------------------------------------------------------------------
# Webhook secret enforcement
# ---------------------------------------------------------------------------


async def test_invalid_webhook_secret_returns_401_no_side_effects(
    webhook_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    before = {
        "logs": await _count(db_session, TelegramUpdateLog),
        "bindings": await _count(db_session, TelegramGroupBinding),
        "identities": await _count(db_session, TelegramIdentity),
        "outbox": await _count(db_session, TelegramOutbox),
        "tasks": await _count(db_session, Task),
    }

    response = await _post(
        webhook_client,
        {
            "update_id": 9_001,
            "message": {
                "message_id": 1,
                "chat": {"id": -100_555_001, "type": "supergroup"},
                "from": {"id": 555_001},
                "text": "/task @x boom",
                "entities": [{"type": "bot_command", "offset": 0, "length": 5}],
            },
        },
        secret="not-the-real-secret",
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid secret"
    assert await _count(db_session, TelegramUpdateLog) == before["logs"]
    assert await _count(db_session, TelegramGroupBinding) == before["bindings"]
    assert await _count(db_session, TelegramIdentity) == before["identities"]
    assert await _count(db_session, TelegramOutbox) == before["outbox"]
    assert await _count(db_session, Task) == before["tasks"]


async def test_missing_secret_header_returns_401(
    webhook_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    before = await _count(db_session, TelegramUpdateLog)

    response = await _post(
        webhook_client,
        {"update_id": 9_002, "unsupported": True},
        secret=None,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid secret"
    # No new log row should be inserted on auth failure.
    assert await _count(db_session, TelegramUpdateLog) == before


# ---------------------------------------------------------------------------
# Admin settings never leak the bot token / webhook secret
# ---------------------------------------------------------------------------


async def test_admin_settings_response_never_leaks_bot_token(
    admin_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    put_resp = await admin_client.put(
        _ADMIN_SETTINGS_URL,
        json={"bot_token": _BOT_TOKEN_VALUE, "is_enabled": True},
    )
    assert put_resp.status_code == 200, put_resp.text
    assert _BOT_TOKEN_VALUE not in put_resp.text
    assert put_resp.json()["bot_token_configured"] is True

    get_resp = await admin_client.get(_ADMIN_SETTINGS_URL)
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["bot_token_configured"] is True
    # The raw token MUST NOT appear in any response field.
    assert _BOT_TOKEN_VALUE not in get_resp.text
    assert "bot_token" not in body or body.get("bot_token") in (None, "")

    # And the masked-UI projection (used by the admin Settings page) must
    # likewise hide the raw token. ``ConfigService.get_all_for_ui`` returns
    # only the canonical AI-provider keys, so the token must not appear at
    # all in its output.
    ui_view = await ConfigService(db_session).get_all_for_ui()
    flat = repr(ui_view)
    assert _BOT_TOKEN_VALUE not in flat


async def test_webhook_url_response_never_leaks_secret(
    admin_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    raw_secret = "super-webhook-secret-9001"
    put_resp = await admin_client.put(
        _ADMIN_SETTINGS_URL,
        json={
            "webhook_secret": raw_secret,
            "webhook_url": "https://example.test/telegram",
        },
    )
    assert put_resp.status_code == 200, put_resp.text
    assert raw_secret not in put_resp.text
    body = put_resp.json()
    assert body["webhook_secret_configured"] is True
    assert body["webhook_url"] == "https://example.test/telegram"

    get_resp = await admin_client.get(_ADMIN_SETTINGS_URL)
    assert get_resp.status_code == 200, get_resp.text
    assert raw_secret not in get_resp.text

    ui_view = await ConfigService(db_session).get_all_for_ui()
    assert raw_secret not in repr(ui_view)


# ---------------------------------------------------------------------------
# Idempotency on duplicate update_id
# ---------------------------------------------------------------------------


async def test_duplicate_update_id_idempotent(
    webhook_client: httpx.AsyncClient,
    db_session: AsyncSession,
    bound_telegram_group,
) -> None:
    binding = bound_telegram_group.binding
    lead_identity = bound_telegram_group.lead_identity
    tasks_before = await _count(db_session, Task)

    payload = {
        "update_id": 9_010,
        "message": {
            "message_id": 4242,
            "chat": {"id": binding.chat_id, "type": "supergroup"},
            "from": {
                "id": lead_identity.telegram_user_id,
                "username": lead_identity.telegram_username,
                "first_name": "Lead",
            },
            "message_thread_id": binding.message_thread_id,
            "text": "/task Build the new tool",
            "entities": [{"type": "bot_command", "offset": 0, "length": 5}],
        },
    }

    responses = [await _post(webhook_client, payload) for _ in range(3)]
    assert all(resp.status_code == 200 for resp in responses)

    log_rows = (
        await db_session.execute(
            select(TelegramUpdateLog).where(TelegramUpdateLog.update_id == 9_010)
        )
    ).scalars().all()
    assert len(list(log_rows)) == 1

    outbox_rows = (
        await db_session.execute(
            select(TelegramOutbox).where(
                TelegramOutbox.idempotency_key == "reply:9010"
            )
        )
    ).scalars().all()
    assert len(list(outbox_rows)) == 1

    tasks_after = await _count(db_session, Task)
    # Exactly one Task may have been created by the first delivery; later
    # duplicates must not multiply tasks.
    assert tasks_after - tasks_before == 1


# ---------------------------------------------------------------------------
# Authorization: sender and assignee must belong to the bound Squad
# ---------------------------------------------------------------------------


async def test_unlinked_telegram_sender_cannot_create_task(
    webhook_client: httpx.AsyncClient,
    db_session: AsyncSession,
    bound_telegram_group,
) -> None:
    binding = bound_telegram_group.binding
    member_identity = bound_telegram_group.member_identity
    tasks_before = await _count(db_session, Task)

    payload = {
        "update_id": 9_020,
        "message": {
            "message_id": 5050,
            "chat": {"id": binding.chat_id, "type": "supergroup"},
            "from": {
                "id": 999_999_999,  # NOT linked to any employee.
                "username": "ghost_user",
                "first_name": "Ghost",
            },
            "message_thread_id": binding.message_thread_id,
            "text": f"/task @{member_identity.telegram_username} hello",
            "entities": [
                {"type": "bot_command", "offset": 0, "length": 5},
                {
                    "type": "mention",
                    "offset": 6,
                    "length": 1 + len(member_identity.telegram_username or ""),
                },
            ],
        },
    }

    response = await _post(webhook_client, payload)
    assert response.status_code == 200

    assert await _count(db_session, Task) == tasks_before

    log = await db_session.scalar(
        select(TelegramUpdateLog).where(TelegramUpdateLog.update_id == 9_020)
    )
    assert log is not None
    assert log.status == "processed"

    reply = await db_session.scalar(
        select(TelegramOutbox).where(
            TelegramOutbox.idempotency_key == "reply:9020"
        )
    )
    assert reply is not None
    assert reply.message_kind == telegram_outbox_service.MESSAGE_KIND_ERROR_REPLY


async def test_non_member_assignee_rejected(
    webhook_client: httpx.AsyncClient,
    db_session: AsyncSession,
    bound_telegram_group,
    department_factory,
    employee_factory,
) -> None:
    binding = bound_telegram_group.binding
    lead_identity = bound_telegram_group.lead_identity
    tasks_before = await _count(db_session, Task)

    # Set up a sibling Squad B with its own linked Telegram identity that
    # is NOT a member of the bound Squad A.
    squad_b = await department_factory(name="Squad B")
    squad_b_employee = await employee_factory(
        department_id=squad_b.id,
        name="Squad B Member",
        username=f"squad_b_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(
        EmployeeDepartmentMembership(
            employee_id=squad_b_employee.id,
            department_id=squad_b.id,
            role=MembershipRole.MEMBER,
            is_active=True,
        )
    )
    squad_b_username = f"squad_b_user_{uuid.uuid4().hex[:6]}"
    db_session.add(
        TelegramIdentity(
            employee_id=squad_b_employee.id,
            telegram_user_id=200_000_002,
            telegram_username=squad_b_username,
            display_name=squad_b_employee.name,
            is_active=True,
        )
    )
    await db_session.flush()

    mention = f"@{squad_b_username}"
    payload = {
        "update_id": 9_021,
        "message": {
            "message_id": 5051,
            "chat": {"id": binding.chat_id, "type": "supergroup"},
            "from": {
                "id": lead_identity.telegram_user_id,
                "username": lead_identity.telegram_username,
                "first_name": "Lead",
            },
            "message_thread_id": binding.message_thread_id,
            "text": f"/task {mention} cross-squad work",
            "entities": [
                {"type": "bot_command", "offset": 0, "length": 5},
                {"type": "mention", "offset": 6, "length": len(mention)},
            ],
        },
    }

    response = await _post(webhook_client, payload)
    assert response.status_code == 200

    assert await _count(db_session, Task) == tasks_before

    reply = await db_session.scalar(
        select(TelegramOutbox).where(
            TelegramOutbox.idempotency_key == "reply:9021"
        )
    )
    assert reply is not None
    assert reply.message_kind == telegram_outbox_service.MESSAGE_KIND_ERROR_REPLY


# ---------------------------------------------------------------------------
# HTML injection in task title must be escaped in the outbox payload
# ---------------------------------------------------------------------------


async def test_html_injection_in_task_title_is_escaped_in_outbox_payload(
    db_session: AsyncSession,
    bound_telegram_group,
) -> None:
    binding = bound_telegram_group.binding
    project = bound_telegram_group.project
    lead = bound_telegram_group.lead

    state = await db_session.scalar(
        select(TaskState).where(TaskState.task_project_id == project.id).limit(1)
    )
    assert state is not None

    malicious_title = "<b>boom</b> & friends"
    task = Task(
        task_project_id=project.id,
        state_id=state.id,
        title=malicious_title,
        reporter_id=lead.id,
        created_by_id=lead.id,
    )
    db_session.add(task)
    await db_session.flush()

    row = await telegram_outbox_service.enqueue_task_created(
        db_session,
        binding=binding,
        task=task,
        task_url=f"/tasks/{task.id}",
    )
    assert row is not None
    rendered = row.payload["text"]

    # The raw user-supplied HTML must NOT survive into the rendered text.
    assert "<b>boom</b>" not in rendered
    # The escaped form must be present in the title-rendering portion.
    assert "&lt;b&gt;boom&lt;/b&gt;" in rendered
    assert "&amp;" in rendered


# ---------------------------------------------------------------------------
# Token shape never leaks into logs or outbox payloads
# ---------------------------------------------------------------------------


async def test_token_shape_never_in_log_or_payload(
    db_session: AsyncSession,
    bound_telegram_group,
) -> None:
    binding = bound_telegram_group.binding
    project = bound_telegram_group.project
    lead = bound_telegram_group.lead

    state = await db_session.scalar(
        select(TaskState).where(TaskState.task_project_id == project.id).limit(1)
    )
    assert state is not None

    task = Task(
        task_project_id=project.id,
        state_id=state.id,
        title="Plain title",
        reporter_id=lead.id,
        created_by_id=lead.id,
    )
    db_session.add(task)
    await db_session.flush()

    outbox_row = await telegram_outbox_service.enqueue_task_created(
        db_session,
        binding=binding,
        task=task,
        task_url=f"/tasks/{task.id}",
    )
    assert outbox_row is not None

    await ConfigService(db_session).set("telegram_bot_token", _BOT_TOKEN_VALUE)
    await db_session.flush()

    captured: list[str] = []
    sink_id = logger.add(
        lambda message: captured.append(str(message)),
        level="DEBUG",
    )
    try:
        # First call: deliver the row via the rate-limit branch. The worker
        # must NOT log the configured bot token while handling the 429.
        await send_pending_telegram_outbox(
            {},
            client_factory=lambda _token: _RateLimitClient(retry_after=2),
            session_factory=_wrap_session(db_session),
            now=_frozen_now,
        )
    finally:
        logger.remove(sink_id)

    for record in captured:
        assert _BOT_TOKEN_VALUE not in record, record
        # Defence in depth: any token-shaped substring must be absent. The
        # exact configured token is the only token-shaped value in scope,
        # so this check is equivalent but expresses the contract clearly.
        assert _TOKEN_SHAPE_RE.search(record) is None, record

    refreshed = await db_session.scalar(
        select(TelegramOutbox).where(TelegramOutbox.id == outbox_row.id)
    )
    assert refreshed is not None
    payload_repr = repr(refreshed.payload)
    assert _BOT_TOKEN_VALUE not in payload_repr
    assert _TOKEN_SHAPE_RE.search(payload_repr) is None


# ---------------------------------------------------------------------------
# Lifecycle: chat migration + my_chat_member kicked
# ---------------------------------------------------------------------------


async def test_chat_migrate_updates_binding_chat_id(
    webhook_client: httpx.AsyncClient,
    db_session: AsyncSession,
    bound_telegram_group,
) -> None:
    binding = bound_telegram_group.binding
    old_chat_id = binding.chat_id
    new_chat_id = -100_900_900_900

    payload = {
        "update_id": 9_030,
        "message": {
            "message_id": 6060,
            "chat": {"id": old_chat_id, "type": "group"},
            "from": {"id": 100_000_001, "username": "telegram_lead"},
            "migrate_to_chat_id": new_chat_id,
        },
    }

    response = await _post(webhook_client, payload)
    assert response.status_code == 200

    await db_session.refresh(binding)
    assert binding.chat_id == new_chat_id
    assert binding.bot_status == "migrated"
    assert binding.migrated_to_chat_id == new_chat_id


async def test_kicked_via_my_chat_member_disables_binding(
    webhook_client: httpx.AsyncClient,
    db_session: AsyncSession,
    bound_telegram_group,
) -> None:
    binding = bound_telegram_group.binding

    payload = {
        "update_id": 9_031,
        "my_chat_member": {
            "chat": {"id": binding.chat_id, "type": "supergroup"},
            "from": {"id": 100_000_001},
            "old_chat_member": {"user": {"id": 7777, "is_bot": True}, "status": "member"},
            "new_chat_member": {"user": {"id": 7777, "is_bot": True}, "status": "kicked"},
        },
    }

    response = await _post(webhook_client, payload)
    assert response.status_code == 200

    await db_session.refresh(binding)
    assert binding.is_active is False
    assert binding.bot_status == "kicked"
    assert binding.disabled_at is not None


# ---------------------------------------------------------------------------
# Empty /task title returns a validation error, no Task row
# ---------------------------------------------------------------------------


async def test_invalid_command_args_return_validation_error_without_task(
    webhook_client: httpx.AsyncClient,
    db_session: AsyncSession,
    bound_telegram_group,
) -> None:
    binding = bound_telegram_group.binding
    lead_identity = bound_telegram_group.lead_identity
    tasks_before = await _count(db_session, Task)

    payload = {
        "update_id": 9_040,
        "message": {
            "message_id": 7070,
            "chat": {"id": binding.chat_id, "type": "supergroup"},
            "from": {
                "id": lead_identity.telegram_user_id,
                "username": lead_identity.telegram_username,
                "first_name": "Lead",
            },
            "message_thread_id": binding.message_thread_id,
            "text": "/task",
            "entities": [{"type": "bot_command", "offset": 0, "length": 5}],
        },
    }

    response = await _post(webhook_client, payload)
    assert response.status_code == 200

    assert await _count(db_session, Task) == tasks_before

    reply = await db_session.scalar(
        select(TelegramOutbox).where(
            TelegramOutbox.idempotency_key == "reply:9040"
        )
    )
    assert reply is not None
    assert reply.message_kind == telegram_outbox_service.MESSAGE_KIND_ERROR_REPLY
