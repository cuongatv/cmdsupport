"""Telegram identity / link-code service.

This module mediates the binding between a Telegram numeric user id and an
internal :class:`~app.database.models.Employee`.

Flow
----
1. The Employee (already authenticated to the CMD Support portal) calls
   :func:`generate_link_code`. A pending row is inserted with ``is_active=False``
   and a short-lived ``link_code`` such as ``LINK-AB3X42-Y``.

2. The Employee types ``/link LINK-AB3X42-Y`` in any Telegram chat the bot can
   see. The Telegram webhook handler invokes :func:`consume_link_code` with
   the *real* numeric ``telegram_user_id`` (and optional username / display
   name) read from the Telegram ``message.from`` object.

3. :func:`consume_link_code` flips the row to ``is_active=True``, stamps
   ``linked_at``, and records the real Telegram identifiers.

The Telegram numeric user id is the only stable identity — usernames are
mutable and untrusted, and never used for authorization.

Concurrency / uniqueness
------------------------
The schema defines a partial unique index
``uq_telegram_active_identity ON telegram_identities(telegram_user_id) WHERE is_active = true``
so only one *active* identity can ever exist per Telegram user id. Pending
rows use a negative sentinel ``telegram_user_id`` (real Telegram ids are
positive 64-bit ints) so they never collide with that index. To keep one
outstanding code per employee at most, :func:`generate_link_code` deletes any
prior pending rows for the same employee before inserting a new one.

Audit
-----
The pending ``link_code`` value is preserved on the row even after consumption
so that follow-up consume attempts can be answered with
:class:`LinkCodeAlreadyConsumed` instead of an opaque not-found error. The
``link_code_expires_at`` field is cleared on consume so the code is no longer
treated as time-bounded. Raw ``link_code`` values are never logged.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Employee, TelegramIdentity

LINK_CODE_PREFIX = "LINK-"
LINK_CODE_TTL = timedelta(minutes=10)


class TelegramIdentityError(Exception):
    """Base class for telegram identity service errors."""


class LinkCodeNotFound(TelegramIdentityError):
    """No pending TelegramIdentity row matches the supplied link code."""


class LinkCodeExpired(TelegramIdentityError):
    """The link code exists but its TTL has elapsed."""


class LinkCodeAlreadyConsumed(TelegramIdentityError):
    """The link code has already been used to activate an identity."""


class IdentityAlreadyExistsForTelegramUser(TelegramIdentityError):
    """An active identity for this Telegram user id already exists for another employee."""


class IdentityNotLinked(TelegramIdentityError):
    """The Telegram user has no active identity row."""


class IdentityRevokeNotPermitted(TelegramIdentityError):
    """The caller is neither the owning employee nor a system admin."""


class IdentityNotFound(TelegramIdentityError):
    """No TelegramIdentity row exists for the requested id."""


def _is_admin(actor: Employee) -> bool:
    return actor.role == "admin"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_pending_sentinel_id() -> int:
    """Return a strictly negative 32-bit-ish integer for use as a placeholder
    ``telegram_user_id`` on pending rows.

    Real Telegram user ids are positive 64-bit ints, so the negative range is
    safe to reserve for "no Telegram user is bound to this row yet". Strict
    negativity is enforced so the sentinel never collides with the
    ``telegram_user_id == 0`` corner case.
    """
    raw = int(secrets.token_hex(7), 16)
    return -(raw % 2_000_000_000) - 1


def _generate_link_code() -> str:
    return f"{LINK_CODE_PREFIX}{secrets.token_urlsafe(6).upper()}"


async def generate_link_code(
    session: AsyncSession,
    *,
    employee: Employee,
) -> TelegramIdentity:
    """Issue (or re-issue) a single-use link code for ``employee``.

    Any prior *pending* rows owned by this employee are deleted first, so only
    one outstanding code exists per employee at any time. The returned row has
    ``is_active=False`` and a negative sentinel ``telegram_user_id`` until the
    code is consumed by :func:`consume_link_code`.

    Caller is responsible for committing the surrounding transaction.
    """
    prior = await session.execute(
        select(TelegramIdentity).where(
            TelegramIdentity.employee_id == employee.id,
            TelegramIdentity.is_active.is_(False),
            TelegramIdentity.link_code.is_not(None),
            TelegramIdentity.linked_at.is_(None),
        )
    )
    for row in prior.scalars().all():
        await session.delete(row)
    await session.flush()

    identity = TelegramIdentity(
        employee_id=employee.id,
        telegram_user_id=_generate_pending_sentinel_id(),
        telegram_username=None,
        display_name=None,
        is_active=False,
        link_code=_generate_link_code(),
        link_code_expires_at=_now() + LINK_CODE_TTL,
        linked_at=None,
        revoked_at=None,
    )
    session.add(identity)
    await session.flush()
    await session.refresh(identity)

    logger.info(
        "telegram_identity.link_code_issued identity_id={} employee_id={} expires_at={}",
        identity.id,
        employee.id,
        identity.link_code_expires_at,
    )
    return identity


async def consume_link_code(
    session: AsyncSession,
    *,
    code: str,
    telegram_user_id: int,
    telegram_username: str | None,
    display_name: str | None,
) -> TelegramIdentity:
    """Activate the pending identity that owns ``code`` and bind it to the
    Telegram user identified by ``telegram_user_id``.

    ``telegram_user_id`` must be the real positive numeric ``from.id`` from the
    Telegram update; usernames are NOT identity and must never be used here.

    Raises:
        LinkCodeNotFound: ``code`` does not match any row.
        LinkCodeAlreadyConsumed: the row owning ``code`` is already active.
        LinkCodeExpired: the row owning ``code`` has expired.
        IdentityAlreadyExistsForTelegramUser: another active row already binds
            ``telegram_user_id`` to a different employee; the pending row is
            left untouched.
    """
    if telegram_user_id <= 0:
        raise LinkCodeNotFound(
            "telegram_user_id must be a positive Telegram user id"
        )

    result = await session.execute(
        select(TelegramIdentity).where(TelegramIdentity.link_code == code)
    )
    identity = result.scalar_one_or_none()
    if identity is None:
        raise LinkCodeNotFound("no pending identity matches the supplied link code")

    if identity.is_active or identity.linked_at is not None:
        raise LinkCodeAlreadyConsumed(
            f"link code already consumed for identity {identity.id}"
        )

    now = _now()
    if (
        identity.link_code_expires_at is None
        or identity.link_code_expires_at < now
    ):
        raise LinkCodeExpired(
            f"link code expired for identity {identity.id}"
        )

    existing_result = await session.execute(
        select(TelegramIdentity).where(
            TelegramIdentity.telegram_user_id == telegram_user_id,
            TelegramIdentity.is_active.is_(True),
            TelegramIdentity.id != identity.id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        logger.warning(
            "telegram_identity.consume_conflict identity_id={} owning_employee_id={} "
            "telegram_user_id={}",
            identity.id,
            existing.employee_id,
            telegram_user_id,
        )
        raise IdentityAlreadyExistsForTelegramUser(
            f"telegram_user_id {telegram_user_id} is already linked to "
            f"another employee"
        )

    identity.telegram_user_id = telegram_user_id
    identity.telegram_username = telegram_username
    identity.display_name = display_name
    identity.is_active = True
    identity.linked_at = now
    identity.link_code_expires_at = None
    identity.revoked_at = None

    await session.flush()
    await session.refresh(identity)

    logger.info(
        "telegram_identity.linked identity_id={} employee_id={} telegram_user_id={}",
        identity.id,
        identity.employee_id,
        telegram_user_id,
    )
    return identity


async def revoke_identity(
    session: AsyncSession,
    *,
    identity_id: uuid.UUID,
    requested_by: Employee,
) -> TelegramIdentity:
    """Deactivate an existing identity.

    Only the owning employee or a system admin may revoke an identity.
    Revoking an already-inactive row is a no-op (no error, no audit duplicate).
    """
    identity = await session.get(TelegramIdentity, identity_id)
    if identity is None:
        raise IdentityNotFound(f"identity {identity_id} not found")

    is_owner = identity.employee_id == requested_by.id
    if not is_owner and not _is_admin(requested_by):
        logger.warning(
            "telegram_identity.revoke_denied identity_id={} requested_by={}",
            identity.id,
            requested_by.id,
        )
        raise IdentityRevokeNotPermitted(
            f"employee {requested_by.id} cannot revoke identity {identity_id}"
        )

    if identity.is_active:
        identity.is_active = False
        identity.revoked_at = _now()
        await session.flush()
        await session.refresh(identity)
        logger.info(
            "telegram_identity.revoked identity_id={} employee_id={} requested_by={}",
            identity.id,
            identity.employee_id,
            requested_by.id,
        )

    return identity


async def find_identity_by_telegram_user(
    session: AsyncSession,
    *,
    telegram_user_id: int,
) -> TelegramIdentity | None:
    """Return the single active identity for ``telegram_user_id`` or ``None``.

    Negative / zero values short-circuit to ``None`` because real Telegram user
    ids are always positive.
    """
    if telegram_user_id <= 0:
        return None
    result = await session.execute(
        select(TelegramIdentity).where(
            TelegramIdentity.telegram_user_id == telegram_user_id,
            TelegramIdentity.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def require_identity(
    session: AsyncSession,
    *,
    telegram_user_id: int,
) -> TelegramIdentity:
    """Return the active identity or raise :class:`IdentityNotLinked`."""
    identity = await find_identity_by_telegram_user(
        session, telegram_user_id=telegram_user_id
    )
    if identity is None:
        raise IdentityNotLinked(
            f"telegram_user_id {telegram_user_id} has no active identity"
        )
    return identity
