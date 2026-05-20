# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""Unit tests for :mod:`app.services.telegram_binding_service`.

The service does not commit; we rely on the rollback-isolated ``db_session``
fixture to keep tests independent. Telegram payload factories are imported
from :mod:`tests.fixtures.telegram` via ``conftest`` autoload.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.database.models import (
    EmployeeDepartmentMembership,
    MembershipRole,
    TelegramGroupBinding,
)
from app.services import telegram_binding_service as svc

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_primary_membership(
    db_session,
    *,
    employee_id,
    department_id,
    role: MembershipRole,
):
    membership = EmployeeDepartmentMembership(
        employee_id=employee_id,
        department_id=department_id,
        role=role,
        is_primary=True,
        is_active=True,
    )
    db_session.add(membership)
    await db_session.flush()
    return membership


# ---------------------------------------------------------------------------
# generate_bind_code
# ---------------------------------------------------------------------------


async def test_generate_bind_code_by_admin_creates_pending_row(
    db_session,
    department_factory,
    employee_factory,
    task_project_factory,
):
    department = await department_factory(name="Bind Admin Department")
    admin = await employee_factory(department_id=department.id, role="admin")
    project = await task_project_factory(department_id=department.id, creator=admin)

    binding = await svc.generate_bind_code(
        db_session,
        department_id=department.id,
        default_task_project_id=project.id,
        requested_by=admin,
    )

    assert binding.is_active is False
    assert binding.bot_status is None
    assert binding.bind_code is not None
    assert binding.bind_code.startswith(svc.BIND_CODE_PREFIX)
    # CMD- + 8 chars from token_urlsafe(6)
    assert len(binding.bind_code) == len(svc.BIND_CODE_PREFIX) + 8
    assert binding.bind_code_expires_at is not None
    assert binding.bound_by_id == admin.id
    assert binding.department_id == department.id
    assert binding.default_task_project_id == project.id
    # chat_id is a sentinel until /bind activation fills it in.
    assert binding.chat_id == 0


async def test_generate_bind_code_by_squad_lead_creates_pending_row(
    db_session,
    department_factory,
    employee_factory,
):
    department = await department_factory(name="Bind Lead Department")
    lead = await employee_factory(department_id=department.id, role="employee")
    await _make_primary_membership(
        db_session,
        employee_id=lead.id,
        department_id=department.id,
        role=MembershipRole.LEAD,
    )

    binding = await svc.generate_bind_code(
        db_session,
        department_id=department.id,
        default_task_project_id=None,
        requested_by=lead,
    )

    assert binding.is_active is False
    assert binding.bind_code is not None
    assert binding.bind_code.startswith(svc.BIND_CODE_PREFIX)
    assert binding.bound_by_id == lead.id


async def test_generate_bind_code_by_non_lead_raises_authz_error(
    db_session,
    department_factory,
    employee_factory,
):
    department = await department_factory(name="Bind Non-Lead Department")
    member = await employee_factory(department_id=department.id, role="employee")
    await _make_primary_membership(
        db_session,
        employee_id=member.id,
        department_id=department.id,
        role=MembershipRole.MEMBER,
    )

    with pytest.raises(svc.BindingAuthorizationError):
        await svc.generate_bind_code(
            db_session,
            department_id=department.id,
            default_task_project_id=None,
            requested_by=member,
        )

    # Defensive: confirm no pending row leaked through despite the raise.
    pending_count = (
        await db_session.execute(
            select(func.count())
            .select_from(TelegramGroupBinding)
            .where(TelegramGroupBinding.department_id == department.id)
        )
    ).scalar_one()
    assert pending_count == 0


# ---------------------------------------------------------------------------
# activate_binding_from_telegram
# ---------------------------------------------------------------------------


async def test_activate_binding_sets_chat_id_and_active(
    db_session,
    department_factory,
    employee_factory,
):
    department = await department_factory(name="Bind Activate Department")
    admin = await employee_factory(department_id=department.id, role="admin")
    pending = await svc.generate_bind_code(
        db_session,
        department_id=department.id,
        default_task_project_id=None,
        requested_by=admin,
    )
    code = pending.bind_code
    assert code is not None

    activated = await svc.activate_binding_from_telegram(
        db_session,
        code=code,
        chat_id=-1_000_000_999_001,
        message_thread_id=None,
        chat_title="Real Telegram Group",
        chat_type="supergroup",
    )

    assert activated.id == pending.id
    assert activated.is_active is True
    assert activated.bot_status == "member"
    assert activated.chat_id == -1_000_000_999_001
    assert activated.chat_title == "Real Telegram Group"
    assert activated.chat_type == "supergroup"
    assert activated.bind_code is None
    assert activated.bind_code_expires_at is None
    assert activated.bound_at is not None


async def test_activate_binding_with_expired_code_raises(
    db_session,
    department_factory,
    employee_factory,
):
    department = await department_factory(name="Bind Expired Department")
    admin = await employee_factory(department_id=department.id, role="admin")
    pending = await svc.generate_bind_code(
        db_session,
        department_id=department.id,
        default_task_project_id=None,
        requested_by=admin,
    )
    # Force expiry by rewinding the timestamp past the TTL.
    pending.bind_code_expires_at = svc._now() - timedelta(minutes=1)
    await db_session.flush()
    code = pending.bind_code
    assert code is not None

    with pytest.raises(svc.BindCodeExpired):
        await svc.activate_binding_from_telegram(
            db_session,
            code=code,
            chat_id=-1_000_000_999_002,
            message_thread_id=None,
            chat_title="Late Group",
            chat_type="supergroup",
        )

    refreshed = await db_session.get(TelegramGroupBinding, pending.id)
    assert refreshed is not None
    assert refreshed.is_active is False
    assert refreshed.chat_id == 0


async def test_activate_binding_when_duplicate_active_raises(
    db_session,
    bound_telegram_group,
    employee_factory,
):
    # The bound_telegram_group fixture already has an active binding on
    # chat_id=-100_000_000_000_1 with thread=101. Generate a new pending
    # code for the *same* department and try to activate it onto the same
    # (chat_id, thread) pair — the COALESCE-based uniqueness must reject it.
    department = bound_telegram_group.department
    admin = await employee_factory(department_id=department.id, role="admin")

    pending = await svc.generate_bind_code(
        db_session,
        department_id=department.id,
        default_task_project_id=None,
        requested_by=admin,
    )
    code = pending.bind_code
    assert code is not None

    with pytest.raises(svc.BindingAlreadyActive):
        await svc.activate_binding_from_telegram(
            db_session,
            code=code,
            chat_id=bound_telegram_group.binding.chat_id,
            message_thread_id=bound_telegram_group.binding.message_thread_id,
            chat_title="Duplicate Telegram Group",
            chat_type="supergroup",
        )


# ---------------------------------------------------------------------------
# find_active_binding
# ---------------------------------------------------------------------------


async def test_find_active_binding_matches_thread_as_coalesced_minus_one(
    db_session,
    department_factory,
    employee_factory,
):
    department = await department_factory(name="Bind Find Department")
    admin = await employee_factory(department_id=department.id, role="admin")

    # NULL-thread binding (chat_id A).
    null_pending = await svc.generate_bind_code(
        db_session,
        department_id=department.id,
        default_task_project_id=None,
        requested_by=admin,
    )
    chat_a = -1_000_000_888_001
    await svc.activate_binding_from_telegram(
        db_session,
        code=null_pending.bind_code,
        chat_id=chat_a,
        message_thread_id=None,
        chat_title="A",
        chat_type="supergroup",
    )

    # Threaded binding (chat_id B, thread 42).
    threaded_pending = await svc.generate_bind_code(
        db_session,
        department_id=department.id,
        default_task_project_id=None,
        requested_by=admin,
    )
    chat_b = -1_000_000_888_002
    await svc.activate_binding_from_telegram(
        db_session,
        code=threaded_pending.bind_code,
        chat_id=chat_b,
        message_thread_id=42,
        chat_title="B",
        chat_type="supergroup",
    )

    matched_null = await svc.find_active_binding(
        db_session, chat_id=chat_a, message_thread_id=None
    )
    matched_threaded = await svc.find_active_binding(
        db_session, chat_id=chat_b, message_thread_id=42
    )
    miss_threaded = await svc.find_active_binding(
        db_session, chat_id=chat_a, message_thread_id=42
    )
    miss_null = await svc.find_active_binding(
        db_session, chat_id=chat_b, message_thread_id=None
    )

    assert matched_null is not None
    assert matched_null.chat_id == chat_a
    assert matched_null.message_thread_id is None
    assert matched_threaded is not None
    assert matched_threaded.chat_id == chat_b
    assert matched_threaded.message_thread_id == 42
    assert miss_threaded is None
    assert miss_null is None


# ---------------------------------------------------------------------------
# handle_chat_migration
# ---------------------------------------------------------------------------


async def test_handle_chat_migration_updates_chat_id_and_marks_migrated(
    db_session,
    bound_telegram_group,
):
    original_chat_id = bound_telegram_group.binding.chat_id
    new_chat_id = -1_002_000_000_000_777

    migrated = await svc.handle_chat_migration(
        db_session,
        from_chat_id=original_chat_id,
        to_chat_id=new_chat_id,
    )

    assert migrated is not None
    assert migrated.id == bound_telegram_group.binding.id
    assert migrated.chat_id == new_chat_id
    assert migrated.migrated_to_chat_id == new_chat_id
    assert migrated.bot_status == "migrated"
    assert migrated.is_active is True

    # Idempotency: second call with the old chat_id finds nothing.
    again = await svc.handle_chat_migration(
        db_session,
        from_chat_id=original_chat_id,
        to_chat_id=new_chat_id,
    )
    assert again is None


# ---------------------------------------------------------------------------
# disable_binding
# ---------------------------------------------------------------------------


async def test_disable_binding_sets_is_active_false_and_disabled_at(
    db_session,
    bound_telegram_group,
    employee_factory,
):
    admin = await employee_factory(
        department_id=bound_telegram_group.department.id, role="admin"
    )

    disabled = await svc.disable_binding(
        db_session,
        binding_id=bound_telegram_group.binding.id,
        requested_by=admin,
    )

    assert disabled.id == bound_telegram_group.binding.id
    assert disabled.is_active is False
    assert disabled.disabled_at is not None
