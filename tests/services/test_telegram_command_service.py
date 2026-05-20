# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""Tests for app.services.telegram_command_service."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    EmployeeDepartmentMembership,
    MembershipRole,
    Task,
    TaskActivity,
    TaskAssignee,
    TaskState,
    TelegramIdentity,
)
from app.integrations.telegram.parser import CommandKind, MentionTarget, ParsedCommand
from app.services.telegram_command_service import handle_command

pytestmark = pytest.mark.asyncio


def _parsed(
    kind: CommandKind,
    *,
    args: str = "",
    mentions: tuple[MentionTarget, ...] = (),
) -> ParsedCommand:
    return ParsedCommand(
        kind=kind,
        raw_text=f"/{kind.value} {args}".strip(),
        args=args,
        mentions=mentions,
        validation_error=None,
    )


async def _first_state(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    group: str | None = None,
) -> TaskState:
    stmt = select(TaskState).where(TaskState.task_project_id == project_id)
    if group is not None:
        stmt = stmt.where(TaskState.group == group)
    stmt = stmt.order_by(TaskState.position, TaskState.id).limit(1)
    state = await session.scalar(stmt)
    assert state is not None
    return state


async def _create_task(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    creator_id: uuid.UUID,
    title: str = "Existing task",
) -> Task:
    state = await _first_state(session, project_id)
    task = Task(
        task_project_id=project_id,
        state_id=state.id,
        title=title,
        created_by_id=creator_id,
        reporter_id=creator_id,
    )
    session.add(task)
    await session.flush()
    return task


async def test_task_creates_task_link_and_assignee(db_session, bound_telegram_group):
    parsed = _parsed(
        CommandKind.TASK,
        args="Chuẩn bị báo cáo tuần",
        mentions=(MentionTarget(username=None, user_id=100_000_002),),
    )

    reply = await handle_command(
        db_session,
        parsed=parsed,
        chat_id=bound_telegram_group.binding.chat_id,
        message_thread_id=bound_telegram_group.binding.message_thread_id,
        telegram_user_id=bound_telegram_group.lead_identity.telegram_user_id,
        telegram_username=bound_telegram_group.lead_identity.telegram_username,
        display_name=bound_telegram_group.lead.name,
        message_id=77,
        update_id=9001,
    )

    assert reply.kind == "ok"
    assert reply.idempotency_suffix == "update:9001"
    assert "Chuẩn bị báo cáo tuần" in reply.text
    task = await db_session.scalar(
        select(Task).where(Task.title == "Chuẩn bị báo cáo tuần")
    )
    assert task is not None
    assert task.task_project_id == bound_telegram_group.project.id
    assert task.created_by_id == bound_telegram_group.lead.id
    assignee = await db_session.get(
        TaskAssignee, (task.id, bound_telegram_group.member.id)
    )
    assert assignee is not None


async def test_done_moves_task_to_first_done_state_and_records_activity(
    db_session,
    bound_telegram_group,
):
    task = await _create_task(
        db_session,
        project_id=bound_telegram_group.project.id,
        creator_id=bound_telegram_group.lead.id,
    )
    done_state = await _first_state(db_session, bound_telegram_group.project.id, group="done")
    old_state_id = task.state_id

    reply = await handle_command(
        db_session,
        parsed=_parsed(CommandKind.DONE, args=str(task.id)[:8]),
        chat_id=bound_telegram_group.binding.chat_id,
        message_thread_id=bound_telegram_group.binding.message_thread_id,
        telegram_user_id=bound_telegram_group.lead_identity.telegram_user_id,
        telegram_username=bound_telegram_group.lead_identity.telegram_username,
        display_name=bound_telegram_group.lead.name,
        message_id=78,
        update_id=9002,
    )

    assert reply.kind == "ok"
    refreshed = await db_session.get(Task, task.id)
    assert refreshed is not None
    assert refreshed.state_id == done_state.id
    assert refreshed.completed_at is not None
    activity = await db_session.scalar(
        select(TaskActivity).where(
            TaskActivity.task_id == task.id,
            TaskActivity.verb == "state_changed",
        )
    )
    assert activity is not None
    assert activity.actor_id == bound_telegram_group.lead.id
    assert activity.old_value == str(old_state_id)
    assert activity.new_value == str(done_state.id)
    assert activity.meta == {
        "from_state_id": str(old_state_id),
        "to_state_id": str(done_state.id),
        "via": "telegram",
    }


async def test_assign_adds_assignee_from_username_mention(db_session, bound_telegram_group):
    task = await _create_task(
        db_session,
        project_id=bound_telegram_group.project.id,
        creator_id=bound_telegram_group.lead.id,
    )

    reply = await handle_command(
        db_session,
        parsed=_parsed(
            CommandKind.ASSIGN,
            args=str(task.id)[:8],
            mentions=(MentionTarget(username="telegram_member", user_id=None),),
        ),
        chat_id=bound_telegram_group.binding.chat_id,
        message_thread_id=bound_telegram_group.binding.message_thread_id,
        telegram_user_id=bound_telegram_group.lead_identity.telegram_user_id,
        telegram_username=bound_telegram_group.lead_identity.telegram_username,
        display_name=bound_telegram_group.lead.name,
        message_id=79,
        update_id=9003,
    )

    assert reply.kind == "ok"
    assignee = await db_session.get(
        TaskAssignee, (task.id, bound_telegram_group.member.id)
    )
    assert assignee is not None


async def test_task_rejects_cross_squad_assignee_without_creating_task(
    db_session,
    bound_telegram_group,
    department_factory,
    employee_factory,
):
    other_department = await department_factory(name="Other Squad")
    other_employee = await employee_factory(
        department_id=other_department.id,
        name="Other Telegram User",
        username=f"other_{uuid.uuid4().hex[:8]}",
    )
    db_session.add(
        EmployeeDepartmentMembership(
            employee_id=other_employee.id,
            department_id=other_department.id,
            role=MembershipRole.MEMBER,
            is_active=True,
        )
    )
    db_session.add(
        TelegramIdentity(
            employee_id=other_employee.id,
            telegram_user_id=200_000_001,
            telegram_username="outside_member",
            display_name=other_employee.name,
            is_active=True,
        )
    )
    await db_session.flush()

    before_count = await db_session.scalar(
        select(func.count()).select_from(Task).where(
            Task.task_project_id == bound_telegram_group.project.id
        )
    )

    reply = await handle_command(
        db_session,
        parsed=_parsed(
            CommandKind.TASK,
            args="Việc không hợp lệ",
            mentions=(MentionTarget(username="outside_member", user_id=None),),
        ),
        chat_id=bound_telegram_group.binding.chat_id,
        message_thread_id=bound_telegram_group.binding.message_thread_id,
        telegram_user_id=bound_telegram_group.lead_identity.telegram_user_id,
        telegram_username=bound_telegram_group.lead_identity.telegram_username,
        display_name=bound_telegram_group.lead.name,
        message_id=80,
        update_id=9004,
    )

    after_count = await db_session.scalar(
        select(func.count()).select_from(Task).where(
            Task.task_project_id == bound_telegram_group.project.id
        )
    )
    assert reply.kind == "error"
    assert "không thuộc Squad" in reply.text
    assert after_count == before_count


async def test_task_returns_missing_binding_reply(db_session, bound_telegram_group):
    reply = await handle_command(
        db_session,
        parsed=_parsed(CommandKind.TASK, args="Không có binding"),
        chat_id=-999_999_999,
        message_thread_id=None,
        telegram_user_id=bound_telegram_group.lead_identity.telegram_user_id,
        telegram_username=bound_telegram_group.lead_identity.telegram_username,
        display_name=bound_telegram_group.lead.name,
        message_id=81,
        update_id=9005,
    )

    assert reply.kind == "error"
    assert reply.text == "Nhóm Telegram này chưa được gắn với CMD Support. Liên hệ quản trị viên."


async def test_task_returns_missing_identity_reply(db_session, bound_telegram_group):
    reply = await handle_command(
        db_session,
        parsed=_parsed(CommandKind.TASK, args="Không có identity"),
        chat_id=bound_telegram_group.binding.chat_id,
        message_thread_id=bound_telegram_group.binding.message_thread_id,
        telegram_user_id=987_654_321,
        telegram_username="unknown",
        display_name="Unknown",
        message_id=82,
        update_id=9006,
    )

    assert reply.kind == "error"
    assert reply.text == "Tài khoản Telegram chưa liên kết. Trong CMD Support, tạo mã /link rồi gửi vào nhóm này."
