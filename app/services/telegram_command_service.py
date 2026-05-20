# pyright: reportMissingImports=false
"""Telegram parsed-command orchestration for CMD Support tasks.

This module is intentionally HTTP-agnostic: it takes the already-parsed Telegram
command plus update context, mutates task-domain rows through the caller's
``AsyncSession``, and returns a small structured reply. The webhook router owns
transaction commit/rollback and enqueueing the reply to the Telegram outbox.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import NoReturn
from uuid import UUID

from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Employee,
    EmployeeDepartmentMembership,
    Task,
    TaskActivity,
    TaskAssignee,
    TaskState,
    TelegramGroupBinding,
    TelegramIdentity,
    TelegramTaskLink,
)
from app.integrations.telegram.parser import CommandKind, MentionTarget, ParsedCommand
from app.services import telegram_binding_service, telegram_identity_service

REPLY_OK = "ok"
REPLY_ERROR = "error"
REPLY_INFO = "info"

_MISSING_BINDING_TEXT = (
    "Nhóm Telegram này chưa được gắn với CMD Support. Liên hệ quản trị viên."
)
_MISSING_IDENTITY_TEXT = (
    "Tài khoản Telegram chưa liên kết. Trong CMD Support, tạo mã /link rồi gửi vào nhóm này."
)
_NOT_MEMBER_TEXT = "Tài khoản Telegram chưa thuộc Squad được gắn với nhóm này."
_ASSIGNEE_NOT_MEMBER_TEXT = "Người được giao chưa liên kết Telegram hoặc không thuộc Squad này."
_NO_DEFAULT_PROJECT_TEXT = "Squad chưa có TaskProject mặc định"


@dataclass(frozen=True)
class CommandReply:
    kind: str
    text: str
    idempotency_suffix: str


class TelegramCommandError(Exception):
    reply: CommandReply

    def __init__(self, reply: CommandReply) -> None:
        self.reply = reply
        super().__init__(reply.text)


@dataclass(frozen=True)
class _CommandContext:
    binding: TelegramGroupBinding | None
    sender_identity: TelegramIdentity | None
    sender_employee: Employee | None
    idempotency_suffix: str


@dataclass(frozen=True)
class _ResolvedAssignee:
    identity: TelegramIdentity
    employee: Employee


def _reply(kind: str, text: str, update_id: int) -> CommandReply:
    return CommandReply(
        kind=kind,
        text=text,
        idempotency_suffix=f"update:{update_id}",
    )


def _raise_reply(kind: str, text: str, update_id: int) -> NoReturn:
    raise TelegramCommandError(_reply(kind, text, update_id))


async def handle_command(
    session: AsyncSession,
    *,
    parsed: ParsedCommand,
    chat_id: int,
    message_thread_id: int | None,
    telegram_user_id: int,
    telegram_username: str | None,
    display_name: str | None,
    message_id: int | None,
    update_id: int,
) -> CommandReply:
    """Handle one parsed Telegram command and return a router-enqueueable reply.

    The function never commits and translates expected user/invariant failures
    into ``CommandReply(kind="error", ...)``. Unexpected exceptions are allowed
    to propagate because they indicate a programmer or infrastructure bug.
    """
    try:
        if parsed.validation_error is not None:
            return _validation_reply(parsed, update_id)

        if parsed.kind == CommandKind.HELP:
            return await _handle_help(update_id)
        if parsed.kind == CommandKind.BIND:
            return await _handle_bind(
                session,
                parsed=parsed,
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                update_id=update_id,
            )
        if parsed.kind == CommandKind.LINK:
            return await _handle_link(
                session,
                parsed=parsed,
                telegram_user_id=telegram_user_id,
                telegram_username=telegram_username,
                display_name=display_name,
                update_id=update_id,
            )
        if parsed.kind == CommandKind.WHOAMI:
            context = await _resolve_context(
                session,
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                telegram_user_id=telegram_user_id,
                update_id=update_id,
                require_binding=False,
                require_sender_membership=False,
            )
            return await _handle_whoami(session, context=context, update_id=update_id)
        if parsed.kind == CommandKind.TASK:
            context = await _resolve_context(
                session,
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                telegram_user_id=telegram_user_id,
                update_id=update_id,
                require_binding=True,
                require_sender_membership=True,
            )
            return await _handle_task(
                session,
                parsed=parsed,
                context=context,
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                message_id=message_id,
                update_id=update_id,
            )
        if parsed.kind == CommandKind.ASSIGN:
            context = await _resolve_context(
                session,
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                telegram_user_id=telegram_user_id,
                update_id=update_id,
                require_binding=True,
                require_sender_membership=True,
            )
            return await _handle_assign(
                session,
                parsed=parsed,
                context=context,
                update_id=update_id,
            )
        if parsed.kind == CommandKind.MYTASKS:
            context = await _resolve_context(
                session,
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                telegram_user_id=telegram_user_id,
                update_id=update_id,
                require_binding=True,
                require_sender_membership=True,
            )
            return await _handle_mytasks(session, context=context, update_id=update_id)
        if parsed.kind == CommandKind.DONE:
            context = await _resolve_context(
                session,
                chat_id=chat_id,
                message_thread_id=message_thread_id,
                telegram_user_id=telegram_user_id,
                update_id=update_id,
                require_binding=True,
                require_sender_membership=True,
            )
            return await _handle_done(
                session,
                parsed=parsed,
                context=context,
                update_id=update_id,
            )
        if parsed.kind == CommandKind.NO_COMMAND:
            return _reply(REPLY_INFO, "Không có lệnh Telegram cần xử lý.", update_id)
        return _reply(
            REPLY_ERROR,
            "Lệnh chưa được hỗ trợ. Gửi /help để xem danh sách lệnh.",
            update_id,
        )
    except TelegramCommandError as exc:
        return exc.reply


def _validation_reply(parsed: ParsedCommand, update_id: int) -> CommandReply:
    if parsed.kind == CommandKind.TASK:
        text = "Vui lòng nhập tiêu đề công việc sau lệnh /task."
    elif parsed.kind == CommandKind.ASSIGN:
        text = "Vui lòng nhập mã công việc và tag người được giao."
    elif parsed.kind in {CommandKind.BIND, CommandKind.LINK}:
        text = "Vui lòng gửi mã sau lệnh."
    else:
        text = parsed.validation_error or "Lệnh không hợp lệ."
    return _reply(REPLY_ERROR, text, update_id)


async def _handle_help(update_id: int) -> CommandReply:
    text = "\n".join(
        [
            "Các lệnh Telegram hỗ trợ:",
            "/bind <mã> - gắn nhóm Telegram với CMD Support",
            "/link <mã> - liên kết tài khoản Telegram với nhân viên",
            "/whoami - kiểm tra tài khoản đang liên kết",
            "/task @user <tiêu đề> - tạo công việc trong Squad hiện tại",
            "/assign <mã công việc> @user - giao công việc",
            "/mytasks - xem 5 công việc gần nhất của bạn",
            "/done <mã công việc> - chuyển công việc sang hoàn thành",
        ]
    )
    return _reply(REPLY_INFO, text, update_id)


async def _handle_bind(
    session: AsyncSession,
    *,
    parsed: ParsedCommand,
    chat_id: int,
    message_thread_id: int | None,
    update_id: int,
) -> CommandReply:
    try:
        binding = await telegram_binding_service.activate_binding_from_telegram(
            session,
            code=parsed.args,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
            chat_title=None,
            chat_type=None,
        )
    except telegram_binding_service.BindCodeNotFound:
        return _reply(REPLY_ERROR, "Mã /bind không tồn tại hoặc đã được sử dụng.", update_id)
    except telegram_binding_service.BindCodeExpired:
        return _reply(REPLY_ERROR, "Mã /bind đã hết hạn. Vui lòng tạo mã mới.", update_id)
    except telegram_binding_service.BindingAlreadyActive:
        return _reply(REPLY_ERROR, "Nhóm Telegram này đã được gắn với CMD Support.", update_id)

    return _reply(REPLY_OK, f"Đã gắn nhóm Telegram với Squad {binding.department_id}.", update_id)


async def _handle_link(
    session: AsyncSession,
    *,
    parsed: ParsedCommand,
    telegram_user_id: int,
    telegram_username: str | None,
    display_name: str | None,
    update_id: int,
) -> CommandReply:
    try:
        identity = await telegram_identity_service.consume_link_code(
            session,
            code=parsed.args,
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            display_name=display_name,
        )
    except telegram_identity_service.LinkCodeNotFound:
        return _reply(REPLY_ERROR, "Mã /link không tồn tại.", update_id)
    except telegram_identity_service.LinkCodeExpired:
        return _reply(REPLY_ERROR, "Mã /link đã hết hạn. Vui lòng tạo mã mới.", update_id)
    except telegram_identity_service.LinkCodeAlreadyConsumed:
        return _reply(REPLY_ERROR, "Mã /link đã được sử dụng.", update_id)
    except telegram_identity_service.IdentityAlreadyExistsForTelegramUser:
        return _reply(
            REPLY_ERROR,
            "Tài khoản Telegram này đã liên kết với một nhân viên khác.",
            update_id,
        )

    employee = await session.get(Employee, identity.employee_id)
    employee_name = employee.name if employee is not None else str(identity.employee_id)
    return _reply(REPLY_OK, f"Đã liên kết Telegram với {employee_name}.", update_id)


async def _handle_whoami(
    session: AsyncSession,
    *,
    context: _CommandContext,
    update_id: int,
) -> CommandReply:
    identity = _require_identity(context, update_id)
    employee = await _employee_for_identity(session, identity, update_id)
    return _reply(REPLY_INFO, f"Telegram đang liên kết với {employee.name}.", update_id)


async def _handle_task(
    session: AsyncSession,
    *,
    parsed: ParsedCommand,
    context: _CommandContext,
    chat_id: int,
    message_thread_id: int | None,
    message_id: int | None,
    update_id: int,
) -> CommandReply:
    binding = _require_binding(context, update_id)
    sender_identity = _require_identity(context, update_id)
    sender_employee = _require_sender_employee(context, update_id)
    project_id = _require_default_project(binding, update_id)
    initial_state = await _initial_state(session, project_id=project_id, update_id=update_id)

    assignee: _ResolvedAssignee | None = None
    if parsed.mentions:
        assignee = await _resolve_assignee_from_mention(
            session,
            mention=parsed.mentions[0],
            binding=binding,
            update_id=update_id,
        )

    task = Task(
        task_project_id=project_id,
        state_id=initial_state.id,
        title=parsed.args.strip(),
        created_by_id=sender_employee.id,
        reporter_id=sender_employee.id,
    )
    session.add(task)
    await session.flush()

    session.add(
        TaskActivity(
            task_id=task.id,
            actor_id=sender_employee.id,
            verb="created",
            meta={"via": "telegram"},
        )
    )
    if assignee is not None:
        session.add(TaskAssignee(task_id=task.id, employee_id=assignee.employee.id))
        session.add(
            TaskActivity(
                task_id=task.id,
                actor_id=sender_employee.id,
                verb="assigned",
                field_name="assignee_id",
                new_value=str(assignee.employee.id),
                meta={"via": "telegram"},
            )
        )

    session.add(
        TelegramTaskLink(
            task_id=task.id,
            binding_id=binding.id,
            origin_chat_id=chat_id,
            origin_message_id=message_id,
            origin_message_thread_id=message_thread_id,
            created_by_identity_id=sender_identity.id,
        )
    )
    await session.flush()

    assignee_text = _assignee_text(assignee)
    return _reply(
        REPLY_OK,
        f"Đã tạo công việc {str(task.id)[:8]}: {task.title}. Phụ trách: {assignee_text}.",
        update_id,
    )


async def _handle_assign(
    session: AsyncSession,
    *,
    parsed: ParsedCommand,
    context: _CommandContext,
    update_id: int,
) -> CommandReply:
    binding = _require_binding(context, update_id)
    sender_employee = _require_sender_employee(context, update_id)
    project_id = _require_default_project(binding, update_id)
    if not parsed.mentions:
        return _reply(REPLY_ERROR, "Vui lòng tag người được giao.", update_id)

    task = await _task_by_ref(session, ref=parsed.args, project_id=project_id, update_id=update_id)
    assignee = await _resolve_assignee_from_mention(
        session,
        mention=parsed.mentions[0],
        binding=binding,
        update_id=update_id,
    )

    existing = await session.scalar(
        select(TaskAssignee).where(
            TaskAssignee.task_id == task.id,
            TaskAssignee.employee_id == assignee.employee.id,
        )
    )
    if existing is None:
        session.add(TaskAssignee(task_id=task.id, employee_id=assignee.employee.id))
        session.add(
            TaskActivity(
                task_id=task.id,
                actor_id=sender_employee.id,
                verb="assigned",
                field_name="assignee_id",
                new_value=str(assignee.employee.id),
                meta={"via": "telegram"},
            )
        )
        await session.flush()

    return _reply(
        REPLY_OK,
        f"Đã giao công việc {str(task.id)[:8]} cho {_assignee_text(assignee)}.",
        update_id,
    )


async def _handle_mytasks(
    session: AsyncSession,
    *,
    context: _CommandContext,
    update_id: int,
) -> CommandReply:
    binding = _require_binding(context, update_id)
    sender_employee = _require_sender_employee(context, update_id)
    project_id = _require_default_project(binding, update_id)

    stmt = (
        select(Task)
        .join(TaskAssignee, TaskAssignee.task_id == Task.id)
        .join(TaskState, TaskState.id == Task.state_id)
        .where(
            Task.task_project_id == project_id,
            TaskAssignee.employee_id == sender_employee.id,
            Task.deleted_at.is_(None),
            TaskState.group != "done",
        )
        .order_by(Task.created_at.desc(), Task.id.desc())
        .limit(5)
    )
    tasks = list((await session.execute(stmt)).scalars().all())
    if not tasks:
        return _reply(REPLY_INFO, "Bạn chưa có công việc đang mở trong Squad này.", update_id)

    lines = ["5 công việc gần nhất của bạn:"]
    lines.extend(f"- {str(task.id)[:8]}: {task.title}" for task in tasks)
    return _reply(REPLY_INFO, "\n".join(lines), update_id)


async def _handle_done(
    session: AsyncSession,
    *,
    parsed: ParsedCommand,
    context: _CommandContext,
    update_id: int,
) -> CommandReply:
    binding = _require_binding(context, update_id)
    sender_employee = _require_sender_employee(context, update_id)
    project_id = _require_default_project(binding, update_id)
    task = await _task_by_ref(session, ref=parsed.args, project_id=project_id, update_id=update_id)
    done_state = await _first_done_state(session, project_id=project_id, update_id=update_id)

    old_state_id = task.state_id
    task.state_id = done_state.id
    task.completed_at = datetime.now(timezone.utc)
    task.version += 1
    session.add(
        TaskActivity(
            task_id=task.id,
            actor_id=sender_employee.id,
            verb="state_changed",
            field_name="state_id",
            old_value=str(old_state_id),
            new_value=str(done_state.id),
            meta={
                "from_state_id": str(old_state_id),
                "to_state_id": str(done_state.id),
                "via": "telegram",
            },
        )
    )
    await session.flush()
    return _reply(REPLY_OK, f"Đã hoàn thành công việc {str(task.id)[:8]}.", update_id)


async def _resolve_context(
    session: AsyncSession,
    *,
    chat_id: int,
    message_thread_id: int | None,
    telegram_user_id: int,
    update_id: int,
    require_binding: bool,
    require_sender_membership: bool,
) -> _CommandContext:
    binding: TelegramGroupBinding | None = None
    if require_binding:
        binding = await telegram_binding_service.find_active_binding(
            session,
            chat_id=chat_id,
            message_thread_id=message_thread_id,
        )
        if binding is None:
            _raise_reply(REPLY_ERROR, _MISSING_BINDING_TEXT, update_id)

    sender_identity = await telegram_identity_service.find_identity_by_telegram_user(
        session,
        telegram_user_id=telegram_user_id,
    )
    if sender_identity is None:
        _raise_reply(REPLY_ERROR, _MISSING_IDENTITY_TEXT, update_id)

    sender_employee = await _employee_for_identity(session, sender_identity, update_id)
    if require_sender_membership:
        assert binding is not None
        if not await _membership_active(
            session,
            employee_id=sender_employee.id,
            department_id=binding.department_id,
        ):
            _raise_reply(REPLY_ERROR, _NOT_MEMBER_TEXT, update_id)

    return _CommandContext(
        binding=binding,
        sender_identity=sender_identity,
        sender_employee=sender_employee,
        idempotency_suffix=f"update:{update_id}",
    )


async def _employee_for_identity(
    session: AsyncSession,
    identity: TelegramIdentity,
    update_id: int,
) -> Employee:
    employee = await session.get(Employee, identity.employee_id)
    if employee is None or not employee.is_active:
        _raise_reply(REPLY_ERROR, _MISSING_IDENTITY_TEXT, update_id)
    return employee


def _require_binding(context: _CommandContext, update_id: int) -> TelegramGroupBinding:
    if context.binding is None:
        _raise_reply(REPLY_ERROR, _MISSING_BINDING_TEXT, update_id)
    return context.binding


def _require_identity(context: _CommandContext, update_id: int) -> TelegramIdentity:
    if context.sender_identity is None:
        _raise_reply(REPLY_ERROR, _MISSING_IDENTITY_TEXT, update_id)
    return context.sender_identity


def _require_sender_employee(context: _CommandContext, update_id: int) -> Employee:
    if context.sender_employee is None:
        _raise_reply(REPLY_ERROR, _MISSING_IDENTITY_TEXT, update_id)
    return context.sender_employee


def _require_default_project(binding: TelegramGroupBinding, update_id: int) -> UUID:
    if binding.default_task_project_id is None:
        _raise_reply(REPLY_ERROR, _NO_DEFAULT_PROJECT_TEXT, update_id)
    return binding.default_task_project_id


async def _resolve_assignee_from_mention(
    session: AsyncSession,
    *,
    mention: MentionTarget,
    binding: TelegramGroupBinding,
    update_id: int,
) -> _ResolvedAssignee:
    identity: TelegramIdentity | None = None
    if mention.user_id is not None:
        identity = await telegram_identity_service.find_identity_by_telegram_user(
            session,
            telegram_user_id=mention.user_id,
        )
    elif mention.username:
        username = mention.username.removeprefix("@").casefold()
        identity = await session.scalar(
            select(TelegramIdentity).where(
                func.lower(TelegramIdentity.telegram_username) == username,
                TelegramIdentity.is_active.is_(True),
            )
        )

    if identity is None:
        _raise_reply(REPLY_ERROR, _ASSIGNEE_NOT_MEMBER_TEXT, update_id)

    employee = await _employee_for_identity(session, identity, update_id)
    if not await _membership_active(
        session,
        employee_id=employee.id,
        department_id=binding.department_id,
    ):
        _raise_reply(REPLY_ERROR, _ASSIGNEE_NOT_MEMBER_TEXT, update_id)
    return _ResolvedAssignee(identity=identity, employee=employee)


async def _membership_active(
    session: AsyncSession,
    *,
    employee_id: UUID,
    department_id: UUID,
) -> bool:
    result = await session.scalar(
        select(EmployeeDepartmentMembership.id)
        .join(Employee, Employee.id == EmployeeDepartmentMembership.employee_id)
        .where(
            EmployeeDepartmentMembership.employee_id == employee_id,
            EmployeeDepartmentMembership.department_id == department_id,
            EmployeeDepartmentMembership.is_active.is_(True),
            Employee.is_active.is_(True),
        )
        .limit(1)
    )
    return result is not None


async def _task_by_ref(
    session: AsyncSession,
    *,
    ref: str,
    project_id: UUID,
    update_id: int,
) -> Task:
    stripped = ref.strip()
    if not stripped:
        _raise_reply(REPLY_ERROR, "Vui lòng nhập mã công việc.", update_id)

    stmt = select(Task).where(
        Task.task_project_id == project_id,
        Task.deleted_at.is_(None),
    )
    try:
        task_id = UUID(stripped)
    except ValueError:
        stmt = stmt.where(cast(Task.id, String).ilike(f"{stripped}%"))
    else:
        stmt = stmt.where(Task.id == task_id)

    matches = list((await session.execute(stmt.limit(2))).scalars().all())
    if not matches:
        _raise_reply(REPLY_ERROR, "Không tìm thấy công việc trong Squad này.", update_id)
    if len(matches) > 1:
        _raise_reply(REPLY_ERROR, "Mã công việc chưa đủ rõ, vui lòng nhập thêm ký tự.", update_id)
    return matches[0]


async def _initial_state(
    session: AsyncSession,
    *,
    project_id: UUID,
    update_id: int,
) -> TaskState:
    state = await session.scalar(
        select(TaskState)
        .where(TaskState.task_project_id == project_id)
        .order_by(TaskState.is_default.desc(), TaskState.position, TaskState.id)
        .limit(1)
    )
    if state is None:
        _raise_reply(REPLY_ERROR, "TaskProject chưa có trạng thái mặc định.", update_id)
    return state


async def _first_done_state(
    session: AsyncSession,
    *,
    project_id: UUID,
    update_id: int,
) -> TaskState:
    state = await session.scalar(
        select(TaskState)
        .where(
            TaskState.task_project_id == project_id,
            TaskState.group == "done",
        )
        .order_by(TaskState.position, TaskState.created_at, TaskState.id)
        .limit(1)
    )
    if state is None:
        _raise_reply(REPLY_ERROR, "TaskProject chưa có trạng thái hoàn thành.", update_id)
    return state


def _assignee_text(assignee: _ResolvedAssignee | None) -> str:
    if assignee is None:
        return "chưa phân công"
    username = assignee.identity.telegram_username
    if username:
        return f"@{username}"
    return assignee.employee.name
