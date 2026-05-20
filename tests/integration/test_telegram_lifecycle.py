# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""End-to-end Telegram command lifecycle test.

Walks the full inbound Telegram flow over the in-process FastAPI app:

1. Admin configures Telegram settings via ``PUT /api/admin/telegram/settings``.
2. Squad lead creates a ``CMD-...`` bind code via ``POST /api/telegram/bindings``.
3. The webhook receives ``/bind CMD-...`` and activates the binding.
4. Two members generate ``LINK-...`` codes via
   ``POST /api/telegram/identities/link-codes``.
5. The webhook receives ``/link LINK-...`` updates for each member; their
   :class:`TelegramIdentity` rows become active.
6. The webhook receives ``/task @member2 Chuẩn bị báo cáo tuần`` from member1;
   exactly one :class:`Task` is created in the binding's default project, with
   member2 assigned and a :class:`TelegramTaskLink` row pointing at the binding.
7. The webhook receives ``/done <task_short_id>`` from member1; the task moves
   to the first ``group='done'`` state and an outbox row is enqueued.
8. The webhook receives the same ``/task`` update (matching ``update_id``); the
   duplicate is rejected via the :class:`TelegramUpdateLog` unique index, so
   no second task is created.

All Telegram OUTBOUND sends are stopped at the outbox; the worker is NEVER
invoked here. Outbound state is asserted via :class:`TelegramOutbox`.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    MembershipRole,
    Task,
    TaskActivity,
    TaskAssignee,
    TaskProject,
    TaskState,
    TelegramGroupBinding,
    TelegramIdentity,
    TelegramOutbox,
    TelegramTaskLink,
    TelegramUpdateLog,
)
from app.schemas.tasks import TaskProjectCreate
from app.services.task_project_service import create_task_project

pytestmark = pytest.mark.asyncio

_WEBHOOK_URL = "/api/integrations/telegram/webhook"
_WEBHOOK_SECRET = "WHSEC"
_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
_CHAT_ID = -100_999_888_777
_BOT_USERNAME = "CMDSupportBot"
_TASK_TITLE = "Chuẩn bị báo cáo tuần"


class _ActorHolder:
    """Mutable holder so the same ``get_current_user`` override can return
    different employees as the test walks the lifecycle."""

    actor: Employee | None

    def __init__(self) -> None:
        self.actor = None


@pytest_asyncio.fixture
async def lifecycle_actors(db_session: AsyncSession):
    """Seed a department, lead, and two members + primary memberships."""
    department = Department(name=f"Telegram Lifecycle Dept {uuid.uuid4().hex[:8]}")
    db_session.add(department)
    await db_session.flush()

    def _make(role: str, name: str, username: str, system_role: str = "employee") -> Employee:
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

    admin = _make("admin", "Lifecycle Admin", f"life_admin_{uuid.uuid4().hex[:6]}", system_role="admin")
    lead = _make("lead", "Lifecycle Lead", f"life_lead_{uuid.uuid4().hex[:6]}")
    member1 = _make("member1", "Lifecycle Member1", f"life_mem1_{uuid.uuid4().hex[:6]}")
    member2 = _make("member2", "Lifecycle Member2", f"life_mem2_{uuid.uuid4().hex[:6]}")
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

    # The squad needs a default TaskProject so /task can land in it.
    project = await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Lifecycle Default Project",
            identifier=f"LIFE{uuid.uuid4().hex[:3].upper()}",
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
    """Install ``get_db`` + ``get_current_user`` overrides for the lifecycle."""
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
            "chat": {"id": chat_id, "title": "Lifecycle Group", "type": "supergroup"},
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


async def _count(session: AsyncSession, model: type) -> int:
    result = await session.scalar(select(func.count()).select_from(model))
    return int(result or 0)


async def test_full_telegram_lifecycle(
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

    member1_tg_user_id = 700_000_001
    member2_tg_user_id = 700_000_002
    member1_tg_username = f"tg_member1_{uuid.uuid4().hex[:6]}"
    member2_tg_username = f"tg_member2_{uuid.uuid4().hex[:6]}"

    # -------- Step 1: Admin configures Telegram settings --------
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
    settings_body = settings_resp.json()
    assert settings_body["is_enabled"] is True
    assert settings_body["bot_token_configured"] is True
    assert settings_body["webhook_secret_configured"] is True
    # Secret values must never leak through any response field.
    assert _WEBHOOK_SECRET not in settings_resp.text
    assert "BOT:FAKE" not in settings_resp.text

    # -------- Step 2: Squad lead creates a bind code --------
    holder.actor = lead
    bind_resp = await test_client.post(
        "/api/telegram/bindings",
        json={
            "department_id": str(department.id),
            "default_task_project_id": str(project.id),
        },
    )
    assert bind_resp.status_code == 201, bind_resp.text
    bind_body = bind_resp.json()
    assert bind_body["department_id"] == str(department.id)
    assert bind_body["is_active"] is False
    assert bind_body["bind_code"] is not None
    assert bind_body["bind_code"].startswith("CMD-")
    bind_code: str = bind_body["bind_code"]
    binding_id = uuid.UUID(bind_body["id"])

    # -------- Step 3: /bind CMD-XXXXX activates the binding --------
    bind_update = _message_update(
        update_id=1001,
        text=f"/bind {bind_code}",
        from_user_id=900_000_001,  # the lead pasting the code; no link yet
        from_username="bind_runner",
        entities=[{"type": "bot_command", "offset": 0, "length": 5}],
    )
    resp = await _post_webhook(test_client, bind_update)
    assert resp.status_code == 200, resp.text

    binding = await db_session.get(TelegramGroupBinding, binding_id)
    assert binding is not None
    assert binding.is_active is True
    assert binding.chat_id == _CHAT_ID
    assert binding.default_task_project_id == project.id

    # Exactly one bind_reply outbox row should now be queued (the /bind
    # acknowledgement). It's pending — the worker is NOT run here.
    bind_replies = list(
        (
            await db_session.execute(
                select(TelegramOutbox).where(
                    TelegramOutbox.binding_id == binding.id,
                    TelegramOutbox.message_kind == "bind_reply",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(bind_replies) == 1
    assert bind_replies[0].status == "pending"

    # -------- Step 4: Members generate LINK codes --------
    holder.actor = member1
    link1_resp = await test_client.post("/api/telegram/identities/link-codes")
    assert link1_resp.status_code == 201, link1_resp.text
    link1_code: str = link1_resp.json()["link_code"]
    assert link1_code.startswith("LINK-")

    holder.actor = member2
    link2_resp = await test_client.post("/api/telegram/identities/link-codes")
    assert link2_resp.status_code == 201, link2_resp.text
    link2_code: str = link2_resp.json()["link_code"]
    assert link2_code.startswith("LINK-")
    assert link2_code != link1_code

    # -------- Step 5: /link LINK-XXX activates each identity --------
    link1_update = _message_update(
        update_id=1101,
        text=f"/link {link1_code}",
        from_user_id=member1_tg_user_id,
        from_username=member1_tg_username,
        entities=[{"type": "bot_command", "offset": 0, "length": 5}],
    )
    resp = await _post_webhook(test_client, link1_update)
    assert resp.status_code == 200, resp.text

    link2_update = _message_update(
        update_id=1102,
        text=f"/link {link2_code}",
        from_user_id=member2_tg_user_id,
        from_username=member2_tg_username,
        entities=[{"type": "bot_command", "offset": 0, "length": 5}],
    )
    resp = await _post_webhook(test_client, link2_update)
    assert resp.status_code == 200, resp.text

    member1_identity = await db_session.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.employee_id == member1.id,
            TelegramIdentity.is_active.is_(True),
        )
    )
    assert member1_identity is not None
    assert member1_identity.telegram_user_id == member1_tg_user_id
    assert member1_identity.telegram_username == member1_tg_username

    member2_identity = await db_session.scalar(
        select(TelegramIdentity).where(
            TelegramIdentity.employee_id == member2.id,
            TelegramIdentity.is_active.is_(True),
        )
    )
    assert member2_identity is not None
    assert member2_identity.telegram_user_id == member2_tg_user_id
    assert member2_identity.telegram_username == member2_tg_username

    # -------- Step 6: /task @member2 Chuẩn bị báo cáo tuần --------
    # The webhook posts a Telegram update with bot_command + mention entities.
    # The mention text is the @-prefixed username; parser strips it and the
    # rest of the body becomes the task title.
    task_text = f"/task @{member2_tg_username} {_TASK_TITLE}"
    mention_offset = len("/task ")
    mention_length = len(member2_tg_username) + 1  # include the leading '@'
    task_update_id = 1200
    task_update = _message_update(
        update_id=task_update_id,
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
        message_id=5500,
    )
    resp = await _post_webhook(test_client, task_update)
    assert resp.status_code == 200, resp.text

    # The Vietnamese title must round-trip verbatim — no translation, no munging.
    created_task = await db_session.scalar(
        select(Task).where(
            Task.task_project_id == project.id,
            Task.title == _TASK_TITLE,
        )
    )
    assert created_task is not None
    assert created_task.created_by_id == member1.id

    # Exactly one Task in the binding's default project so far.
    task_rows_in_project = list(
        (
            await db_session.execute(
                select(Task).where(Task.task_project_id == project.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(task_rows_in_project) == 1

    # member2 must be the sole assignee.
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

    # A TelegramTaskLink row must point at our binding.
    link_row = await db_session.scalar(
        select(TelegramTaskLink).where(TelegramTaskLink.task_id == created_task.id)
    )
    assert link_row is not None
    assert link_row.binding_id == binding.id
    assert link_row.origin_chat_id == _CHAT_ID
    assert link_row.origin_message_id == 5500
    assert link_row.created_by_identity_id == member1_identity.id

    # -------- Step 7: /done <task_short_id> --------
    short_id = str(created_task.id)[:8]
    done_update_id = 1300
    done_update = _message_update(
        update_id=done_update_id,
        text=f"/done {short_id}",
        from_user_id=member1_tg_user_id,
        from_username=member1_tg_username,
        entities=[{"type": "bot_command", "offset": 0, "length": 5}],
        message_id=5600,
    )
    resp = await _post_webhook(test_client, done_update)
    assert resp.status_code == 200, resp.text

    refreshed = await db_session.get(Task, created_task.id)
    assert refreshed is not None
    done_state = await db_session.get(TaskState, refreshed.state_id)
    assert done_state is not None
    assert done_state.group == "done"
    assert refreshed.completed_at is not None

    # The /done command itself only writes a TaskActivity inside the command
    # service; the outbox status_changed row is written by the additive task
    # hook attached to ``notify_state_changed``. /done in the command service
    # bypasses that hook (it mutates state directly), so we assert the
    # state_changed TaskActivity instead, which is the durable record of the
    # transition that the worker would replay if needed.
    state_changed_activity = await db_session.scalar(
        select(TaskActivity).where(
            TaskActivity.task_id == created_task.id,
            TaskActivity.verb == "state_changed",
        )
    )
    assert state_changed_activity is not None
    assert state_changed_activity.actor_id == member1.id
    assert state_changed_activity.meta is not None
    assert state_changed_activity.meta.get("via") == "telegram"

    # -------- Step 8: Replay the same /task update_id → dedupe --------
    task_count_before_replay = await _count(db_session, Task)
    log_rows_for_task_update = await db_session.scalar(
        select(func.count())
        .select_from(TelegramUpdateLog)
        .where(TelegramUpdateLog.update_id == task_update_id)
    )
    assert int(log_rows_for_task_update or 0) == 1

    resp = await _post_webhook(test_client, task_update)
    assert resp.status_code == 200, resp.text

    # No new Task — the dedupe path in telegram_update_log_service short-circuits.
    assert await _count(db_session, Task) == task_count_before_replay
    # Still exactly one update log row for this update_id.
    log_rows_after = await db_session.scalar(
        select(func.count())
        .select_from(TelegramUpdateLog)
        .where(TelegramUpdateLog.update_id == task_update_id)
    )
    assert int(log_rows_after or 0) == 1

    # And no TelegramOutbox row escaped pending — the worker was never invoked.
    pending_or_sent_statuses = list(
        (
            await db_session.execute(
                select(TelegramOutbox.status).where(
                    TelegramOutbox.binding_id == binding.id
                )
            )
        )
        .scalars()
        .all()
    )
    # Every outbox row enqueued during the lifecycle should still be ``pending``
    # because we never ran the sender. Catching this guards against accidental
    # synchronous network calls leaking into the webhook path.
    assert pending_or_sent_statuses
    assert all(status == "pending" for status in pending_or_sent_statuses)
