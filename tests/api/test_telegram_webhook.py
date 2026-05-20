# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import (
    AppConfig,
    Department,
    Employee,
    Task,
    TelegramGroupBinding,
    TelegramIdentity,
    TelegramOutbox,
    TelegramUpdateLog,
)
from app.services import telegram_binding_service
from app.services.config_service import ConfigService

pytestmark = pytest.mark.asyncio

_WEBHOOK_URL = "/api/integrations/telegram/webhook"
_SECRET = "unit-test-telegram-secret"
_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


@pytest.fixture(autouse=True)
async def _override_db(db_session: AsyncSession) -> AsyncIterator[None]:
    from app.main import app

    async def _get_test_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)


async def _set_secret(db_session: AsyncSession) -> None:
    await ConfigService(db_session).set("telegram_webhook_secret", _SECRET)
    await db_session.flush()


async def _post_update(
    test_client,
    payload: dict[str, Any],
    *,
    secret: str | None = _SECRET,
):
    headers = {_SECRET_HEADER: secret} if secret is not None else {}
    return await test_client.post(_WEBHOOK_URL, json=payload, headers=headers)


async def _count(session: AsyncSession, model: type) -> int:
    result = await session.scalar(select(func.count()).select_from(model))
    return int(result or 0)


async def test_invalid_secret_returns_401_no_side_effects(test_client, db_session):
    await _set_secret(db_session)
    before = {
        "logs": await _count(db_session, TelegramUpdateLog),
        "outbox": await _count(db_session, TelegramOutbox),
        "bindings": await _count(db_session, TelegramGroupBinding),
        "identities": await _count(db_session, TelegramIdentity),
        "tasks": await _count(db_session, Task),
    }

    response = await _post_update(
        test_client,
        {"update_id": 101, "unsupported": True},
        secret="wrong-secret",
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid secret"
    assert await _count(db_session, TelegramUpdateLog) == before["logs"]
    assert await _count(db_session, TelegramOutbox) == before["outbox"]
    assert await _count(db_session, TelegramGroupBinding) == before["bindings"]
    assert await _count(db_session, TelegramIdentity) == before["identities"]
    assert await _count(db_session, Task) == before["tasks"]


async def test_missing_secret_header_returns_401(test_client, db_session):
    await _set_secret(db_session)

    response = await _post_update(
        test_client,
        {"update_id": 102, "unsupported": True},
        secret=None,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid secret"


async def test_valid_secret_with_dummy_update_returns_200_and_logs(
    test_client,
    db_session,
):
    await _set_secret(db_session)

    response = await _post_update(test_client, {"update_id": 103})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    logs = list((await db_session.execute(select(TelegramUpdateLog))).scalars().all())
    assert len(logs) == 1
    assert logs[0].update_id == 103
    assert logs[0].status == "ignored"
    assert logs[0].failure_reason == "unsupported_update_kind"


async def test_duplicate_update_id_returns_200_no_double_processing(
    test_client,
    db_session,
):
    await _set_secret(db_session)
    payload = {"update_id": 104, "unsupported": True}

    first = await _post_update(test_client, payload)
    second = await _post_update(test_client, payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"ok": True}
    assert second.json() == {"ok": True}
    result = await db_session.execute(
        select(TelegramUpdateLog).where(TelegramUpdateLog.update_id == 104)
    )
    assert len(list(result.scalars().all())) == 1


async def test_bind_command_activates_binding_and_enqueues_reply(
    test_client,
    db_session,
    department_factory,
    employee_factory,
    task_project_factory,
):
    await _set_secret(db_session)
    department = await department_factory(name="Webhook Bind Department")
    admin = await employee_factory(department_id=department.id, role="admin")
    project = await task_project_factory(department_id=department.id, creator=admin)
    pending = await telegram_binding_service.generate_bind_code(
        db_session,
        department_id=department.id,
        default_task_project_id=project.id,
        requested_by=admin,
    )
    assert pending.bind_code is not None
    bind_code = pending.bind_code
    chat_id = -100_900_800_700

    response = await _post_update(
        test_client,
        {
            "update_id": 105,
            "message": {
                "message_id": 501,
                "chat": {"id": chat_id, "title": "Webhook Group", "type": "supergroup"},
                "from": {"id": 555001, "username": "bind_admin", "first_name": "Bind"},
                "text": f"/bind {bind_code}",
                "entities": [{"type": "bot_command", "offset": 0, "length": 5}],
            },
        },
    )

    assert response.status_code == 200
    await db_session.refresh(pending)
    assert pending.is_active is True
    assert pending.chat_id == chat_id
    outbox_rows = list(
        (
            await db_session.execute(
                select(TelegramOutbox).where(TelegramOutbox.binding_id == pending.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(outbox_rows) == 1
    assert outbox_rows[0].message_kind == "bind_reply"
    assert outbox_rows[0].idempotency_key == "reply:105"
    assert outbox_rows[0].payload["chat_id"] == chat_id


async def test_unsupported_update_kind_is_ignored(test_client, db_session):
    await _set_secret(db_session)

    response = await _post_update(
        test_client,
        {"update_id": 106, "edited_message": {"message_id": 1}},
    )

    assert response.status_code == 200
    log = await db_session.scalar(
        select(TelegramUpdateLog).where(TelegramUpdateLog.update_id == 106)
    )
    assert log is not None
    assert log.status == "ignored"
    assert log.failure_reason == "unsupported_update_kind"


async def test_invalid_secret_when_unconfigured_returns_401_no_side_effects(
    test_client,
    db_session,
):
    # Regression guard: an empty/unconfigured webhook secret must fail closed.
    await db_session.execute(
        AppConfig.__table__.delete().where(AppConfig.key == "telegram_webhook_secret")
    )
    await db_session.flush()
    before = await _count(db_session, TelegramUpdateLog)

    response = await _post_update(
        test_client,
        {"update_id": 107, "unsupported": True},
        secret="anything",
    )

    assert response.status_code == 401
    assert await _count(db_session, TelegramUpdateLog) == before


async def test_invalid_secret_no_tasks_created(
    test_client,
    db_session,
):
    # Covers the requested "no tasks" side effect without depending on task rows
    # from other fixtures in the same DB.
    await _set_secret(db_session)
    department_count = await _count(db_session, Department)
    employee_count = await _count(db_session, Employee)

    response = await _post_update(
        test_client,
        {"update_id": 108, "unsupported": True},
        secret="wrong-secret",
    )

    assert response.status_code == 401
    assert await _count(db_session, Department) == department_count
    assert await _count(db_session, Employee) == employee_count
