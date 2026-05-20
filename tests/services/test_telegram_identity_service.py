# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
"""Tests for app.services.telegram_identity_service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.database.models import TelegramIdentity
from app.services.telegram_identity_service import (
    LINK_CODE_PREFIX,
    LINK_CODE_TTL,
    IdentityAlreadyExistsForTelegramUser,
    IdentityNotLinked,
    IdentityRevokeNotPermitted,
    LinkCodeAlreadyConsumed,
    LinkCodeExpired,
    consume_link_code,
    find_identity_by_telegram_user,
    generate_link_code,
    require_identity,
    revoke_identity,
)

pytestmark = pytest.mark.asyncio


async def test_generate_link_code_creates_pending_row(
    db_session, employee_factory
):
    employee = await employee_factory()

    identity = await generate_link_code(db_session, employee=employee)

    assert identity.is_active is False
    assert identity.employee_id == employee.id
    assert identity.linked_at is None
    assert identity.revoked_at is None
    assert identity.link_code is not None
    assert identity.link_code.startswith(LINK_CODE_PREFIX)
    assert identity.link_code_expires_at is not None
    now = datetime.now(timezone.utc)
    delta = identity.link_code_expires_at - now
    # TTL is ~10 minutes; allow generous slack for clock skew.
    assert timedelta(minutes=9) <= delta <= LINK_CODE_TTL + timedelta(seconds=5)
    assert identity.telegram_user_id < 0  # negative sentinel


async def test_generate_link_code_replaces_existing_pending_for_same_employee(
    db_session, employee_factory
):
    employee = await employee_factory()

    first = await generate_link_code(db_session, employee=employee)
    first_id = first.id
    first_code = first.link_code

    second = await generate_link_code(db_session, employee=employee)

    assert second.id != first_id
    assert second.link_code != first_code

    count_result = await db_session.execute(
        select(func.count())
        .select_from(TelegramIdentity)
        .where(
            TelegramIdentity.employee_id == employee.id,
            TelegramIdentity.is_active.is_(False),
            TelegramIdentity.link_code.is_not(None),
            TelegramIdentity.linked_at.is_(None),
        )
    )
    assert count_result.scalar_one() == 1


async def test_consume_link_code_activates_identity(
    db_session, employee_factory
):
    employee = await employee_factory()
    pending = await generate_link_code(db_session, employee=employee)

    consumed = await consume_link_code(
        db_session,
        code=pending.link_code,
        telegram_user_id=998877,
        telegram_username="alice_t",
        display_name="Alice T",
    )

    assert consumed.id == pending.id
    assert consumed.is_active is True
    assert consumed.telegram_user_id == 998877
    assert consumed.telegram_username == "alice_t"
    assert consumed.display_name == "Alice T"
    assert consumed.linked_at is not None
    assert consumed.link_code_expires_at is None
    assert consumed.revoked_at is None


async def test_consume_link_code_with_expired_code_raises(
    db_session, employee_factory
):
    employee = await employee_factory()
    pending = await generate_link_code(db_session, employee=employee)
    pending.link_code_expires_at = datetime.now(timezone.utc) - timedelta(
        seconds=1
    )
    await db_session.flush()

    with pytest.raises(LinkCodeExpired):
        await consume_link_code(
            db_session,
            code=pending.link_code,
            telegram_user_id=111222,
            telegram_username=None,
            display_name=None,
        )

    refreshed = await db_session.get(TelegramIdentity, pending.id)
    assert refreshed is not None
    assert refreshed.is_active is False
    assert refreshed.linked_at is None


async def test_consume_link_code_twice_raises_already_consumed(
    db_session, employee_factory
):
    employee = await employee_factory()
    pending = await generate_link_code(db_session, employee=employee)
    code = pending.link_code

    await consume_link_code(
        db_session,
        code=code,
        telegram_user_id=222333,
        telegram_username=None,
        display_name=None,
    )

    with pytest.raises(LinkCodeAlreadyConsumed):
        await consume_link_code(
            db_session,
            code=code,
            telegram_user_id=222334,
            telegram_username=None,
            display_name=None,
        )


async def test_consume_link_code_when_other_employee_already_linked_raises(
    db_session, employee_factory
):
    employee_a = await employee_factory(name="Owner A")
    employee_b = await employee_factory(name="Owner B")

    pending_a = await generate_link_code(db_session, employee=employee_a)
    pending_b = await generate_link_code(db_session, employee=employee_b)
    pending_b_id = pending_b.id
    pending_b_code = pending_b.link_code

    await consume_link_code(
        db_session,
        code=pending_a.link_code,
        telegram_user_id=555666,
        telegram_username="dup",
        display_name="Dup",
    )

    with pytest.raises(IdentityAlreadyExistsForTelegramUser):
        await consume_link_code(
            db_session,
            code=pending_b_code,
            telegram_user_id=555666,
            telegram_username="dup",
            display_name="Dup",
        )

    refreshed_b = await db_session.get(TelegramIdentity, pending_b_id)
    assert refreshed_b is not None
    assert refreshed_b.is_active is False
    assert refreshed_b.linked_at is None
    assert refreshed_b.telegram_user_id < 0


async def test_revoke_identity_by_owner(db_session, employee_factory):
    employee = await employee_factory()
    pending = await generate_link_code(db_session, employee=employee)
    consumed = await consume_link_code(
        db_session,
        code=pending.link_code,
        telegram_user_id=777888,
        telegram_username="own",
        display_name="Own",
    )

    revoked = await revoke_identity(
        db_session, identity_id=consumed.id, requested_by=employee
    )

    assert revoked.is_active is False
    assert revoked.revoked_at is not None


async def test_revoke_identity_by_admin(db_session, employee_factory):
    owner = await employee_factory(name="Owner")
    admin = await employee_factory(name="Admin", role="admin")
    pending = await generate_link_code(db_session, employee=owner)
    consumed = await consume_link_code(
        db_session,
        code=pending.link_code,
        telegram_user_id=111000,
        telegram_username="own",
        display_name="Own",
    )

    revoked = await revoke_identity(
        db_session, identity_id=consumed.id, requested_by=admin
    )

    assert revoked.is_active is False
    assert revoked.revoked_at is not None


async def test_revoke_identity_by_other_user_denied(
    db_session, employee_factory
):
    owner = await employee_factory(name="Owner")
    other = await employee_factory(name="Other")
    pending = await generate_link_code(db_session, employee=owner)
    consumed = await consume_link_code(
        db_session,
        code=pending.link_code,
        telegram_user_id=999000,
        telegram_username="own",
        display_name="Own",
    )

    with pytest.raises(IdentityRevokeNotPermitted):
        await revoke_identity(
            db_session, identity_id=consumed.id, requested_by=other
        )

    refreshed = await db_session.get(TelegramIdentity, consumed.id)
    assert refreshed is not None
    assert refreshed.is_active is True
    assert refreshed.revoked_at is None


async def test_require_identity_returns_active(db_session, employee_factory):
    employee = await employee_factory()
    pending = await generate_link_code(db_session, employee=employee)
    await consume_link_code(
        db_session,
        code=pending.link_code,
        telegram_user_id=333444,
        telegram_username="ok",
        display_name="OK",
    )

    found = await require_identity(db_session, telegram_user_id=333444)
    assert found.employee_id == employee.id
    assert found.is_active is True


async def test_require_identity_raises_when_unlinked(db_session):
    with pytest.raises(IdentityNotLinked):
        await require_identity(db_session, telegram_user_id=987654321)


async def test_find_identity_by_telegram_user_returns_none_when_missing(
    db_session,
):
    result = await find_identity_by_telegram_user(
        db_session, telegram_user_id=10101010
    )
    assert result is None


async def test_find_identity_by_telegram_user_ignores_negative_sentinel(
    db_session, employee_factory
):
    employee = await employee_factory()
    pending = await generate_link_code(db_session, employee=employee)

    # The pending row's telegram_user_id is a negative sentinel; the lookup
    # short-circuits to None for non-positive ids.
    result = await find_identity_by_telegram_user(
        db_session, telegram_user_id=pending.telegram_user_id
    )
    assert result is None
