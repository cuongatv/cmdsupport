# pyright: reportMissingImports=false
"""Telegram group binding service.

Manages the binding lifecycle that links a Telegram chat (or forum topic) to a
Department/Squad and its default :class:`TaskProject`:

* :func:`generate_bind_code` mints a single-use ``CMD-XXXXXXXX`` code for an
  authorized requester (system admin or active primary lead of the
  department).
* :func:`activate_binding_from_telegram` is called when the bot observes a
  ``/bind CMD-XXXXXXXX`` message and stamps the actual Telegram ``chat_id``
  onto the pending row.
* :func:`disable_binding` deactivates a binding (admin / lead).
* :func:`handle_chat_migration` follows the Telegram ``migrate_to_chat_id``
  signal so a supergroup upgrade does not break the Squad link.
* :func:`find_active_binding` is a read-only lookup used by routers / jobs to
  route a Telegram update to its Squad.

This service does NOT commit. Callers (routers / arq jobs) own the transaction
boundary, mirroring the convention used by :mod:`app.services.task_service`.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    MembershipRole,
    TaskProject,
    TelegramGroupBinding,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Prefix every bind code carries so end users can recognize it in chat.
BIND_CODE_PREFIX: str = "CMD-"

#: Bind codes self-expire after this window. Mirrors the Telegram UX
#: expectation that an admin generates a code, walks to the group, and pastes
#: it the same day.
BIND_CODE_TTL: timedelta = timedelta(hours=24)

#: Pending bind rows need a value for the NOT NULL ``chat_id`` column. Telegram
#: never issues ``0`` for a real chat (user IDs are positive, group/supergroup
#: IDs are negative), so it is a safe sentinel. The partial unique index
#: ``uq_telegram_active_binding`` is only enforced WHERE ``is_active = true``,
#: so multiple pending rows with ``chat_id = 0`` do not collide.
_PENDING_CHAT_ID_SENTINEL: int = 0

#: Membership roles considered "lead-style" for binding authorization. Mirrors
#: the squad-only role split used by ``membership_service._validate_role_for_unit_type``:
#: department leads (LEAD / DEPUTY_LEAD) and squad leads (PRODUCT_OWNER /
#: SCRUM_MASTER) can manage bindings; plain members and developers cannot.
_LEAD_ROLES: frozenset[MembershipRole] = frozenset(
    {
        MembershipRole.LEAD,
        MembershipRole.DEPUTY_LEAD,
        MembershipRole.PRODUCT_OWNER,
        MembershipRole.SCRUM_MASTER,
    }
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TelegramBindingError(Exception):
    """Base exception for the Telegram binding service."""


class BindCodeNotFound(TelegramBindingError):
    """Raised when an activation request references an unknown bind code."""


class BindCodeExpired(TelegramBindingError):
    """Raised when an activation request arrives after the code's TTL."""


class BindingAlreadyActive(TelegramBindingError):
    """Raised when (chat_id, COALESCE(message_thread_id, -1)) is already bound."""


class BindingAuthorizationError(TelegramBindingError):
    """Raised when the requester is neither a system admin nor a department lead."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    """Return a tz-aware UTC ``datetime``. Centralized so tests can monkey-patch."""
    return datetime.now(timezone.utc)


def _generate_bind_code() -> str:
    """Mint a fresh ``CMD-XXXXXXXX`` bind code.

    Uses :func:`secrets.token_urlsafe` so the generator is cryptographically
    strong. The output is uppercased for readability in chat; ``-`` and ``_``
    characters from urlsafe base64 are preserved (they paste cleanly into
    Telegram).
    """
    return f"{BIND_CODE_PREFIX}{secrets.token_urlsafe(6).upper()}"


async def _ensure_authorized(
    session: AsyncSession,
    *,
    department_id: uuid.UUID,
    requested_by: Employee,
) -> None:
    """Raise ``BindingAuthorizationError`` unless ``requested_by`` is allowed.

    System admins (``Employee.role == "admin"``) are always allowed.
    Otherwise the requester must hold an *active*, *primary* membership in
    the target department with a lead-style role (see ``_LEAD_ROLES``).
    """
    if requested_by.role == "admin":
        return

    stmt = select(EmployeeDepartmentMembership).where(
        EmployeeDepartmentMembership.employee_id == requested_by.id,
        EmployeeDepartmentMembership.department_id == department_id,
        EmployeeDepartmentMembership.is_active.is_(True),
        EmployeeDepartmentMembership.is_primary.is_(True),
        EmployeeDepartmentMembership.role.in_(_LEAD_ROLES),
    )
    membership = (await session.execute(stmt)).scalar_one_or_none()
    if membership is None:
        raise BindingAuthorizationError(
            "Only system admins or active primary department leads can manage "
            "Telegram bindings"
        )


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def generate_bind_code(
    session: AsyncSession,
    *,
    department_id: uuid.UUID,
    default_task_project_id: uuid.UUID | None,
    requested_by: Employee,
) -> TelegramGroupBinding:
    """Create a pending ``TelegramGroupBinding`` and return it.

    The returned row is ``is_active=False`` with a fresh ``bind_code`` and
    ``bind_code_expires_at = now() + BIND_CODE_TTL``. The actual ``chat_id``
    is filled in later by :func:`activate_binding_from_telegram` when the bot
    observes the ``/bind`` message.

    Raises:
        BindingAuthorizationError: when ``requested_by`` is neither a system
            admin nor a primary lead of ``department_id``.
        ValueError: when ``department_id`` (or ``default_task_project_id``,
            if provided) does not resolve or the project belongs to a
            different department.
    """
    department = await session.get(Department, department_id)
    if department is None:
        raise ValueError(f"Department {department_id} not found")

    if default_task_project_id is not None:
        project = await session.get(TaskProject, default_task_project_id)
        if project is None:
            raise ValueError(f"TaskProject {default_task_project_id} not found")
        if project.department_id != department_id:
            raise ValueError(
                "default_task_project_id does not belong to the given department"
            )

    await _ensure_authorized(
        session, department_id=department_id, requested_by=requested_by
    )

    binding = TelegramGroupBinding(
        department_id=department_id,
        default_task_project_id=default_task_project_id,
        chat_id=_PENDING_CHAT_ID_SENTINEL,
        message_thread_id=None,
        chat_title=None,
        chat_type=None,
        is_active=False,
        bot_status=None,
        bind_code=_generate_bind_code(),
        bind_code_expires_at=_now() + BIND_CODE_TTL,
        bound_by_id=requested_by.id,
    )
    session.add(binding)
    await session.flush()
    # NEVER log the bind_code itself. The code is meant to be shared by the
    # requester into a Telegram chat, but we still treat it as low-trust.
    logger.info(
        "Telegram bind code generated for binding {} (department {})",
        binding.id,
        department_id,
    )
    return binding


async def activate_binding_from_telegram(
    session: AsyncSession,
    *,
    code: str,
    chat_id: int,
    message_thread_id: int | None,
    chat_title: str | None,
    chat_type: str | None,
) -> TelegramGroupBinding:
    """Activate the pending binding identified by ``code``.

    Looks up the pending row (``is_active=False``, matching ``bind_code``),
    validates its TTL, ensures no other active binding owns the same
    ``(chat_id, COALESCE(message_thread_id, -1))`` pair, then stamps the row
    with the captured Telegram chat metadata and clears the bind code.

    Raises:
        BindCodeNotFound: if no pending row matches ``code``.
        BindCodeExpired: if the row exists but ``bind_code_expires_at`` is in
            the past.
        BindingAlreadyActive: if another active row would collide on the
            partial unique index.
    """
    if not code:
        raise BindCodeNotFound("bind code is empty")

    stmt = select(TelegramGroupBinding).where(
        TelegramGroupBinding.bind_code == code,
    )
    binding = (await session.execute(stmt)).scalar_one_or_none()
    if binding is None:
        raise BindCodeNotFound(f"bind code {code!r} not found")

    if binding.is_active:
        # Re-using an already-activated code is a programmer/user error. We
        # surface it as "not found" so the bot does not leak the previous
        # binding's identity into the new chat.
        raise BindCodeNotFound(f"bind code {code!r} already consumed")

    expires_at = binding.bind_code_expires_at
    if expires_at is None or expires_at <= _now():
        raise BindCodeExpired(f"bind code {code!r} has expired")

    duplicate = await find_active_binding(
        session, chat_id=chat_id, message_thread_id=message_thread_id
    )
    if duplicate is not None and duplicate.id != binding.id:
        raise BindingAlreadyActive(
            f"chat_id={chat_id} thread={message_thread_id} is already bound"
        )

    binding.chat_id = chat_id
    binding.message_thread_id = message_thread_id
    binding.chat_title = chat_title
    binding.chat_type = chat_type
    binding.is_active = True
    binding.bot_status = "member"
    binding.bound_at = _now()
    binding.bind_code = None
    binding.bind_code_expires_at = None

    await session.flush()
    logger.info(
        "Telegram binding {} activated for chat_id={} thread={}",
        binding.id,
        chat_id,
        message_thread_id,
    )
    return binding


async def disable_binding(
    session: AsyncSession,
    *,
    binding_id: uuid.UUID,
    requested_by: Employee,
) -> TelegramGroupBinding:
    """Deactivate ``binding_id`` and stamp ``disabled_at``.

    The row is preserved (audit trail / re-bind UX) but flips ``is_active`` to
    ``False`` so it stops routing Telegram updates and frees the
    ``(chat_id, COALESCE(message_thread_id, -1))`` slot.

    Raises:
        BindingAuthorizationError: if the requester is neither admin nor a
            primary lead of the binding's department.
        ValueError: if ``binding_id`` does not exist.
    """
    binding = await session.get(TelegramGroupBinding, binding_id)
    if binding is None:
        raise ValueError(f"TelegramGroupBinding {binding_id} not found")

    await _ensure_authorized(
        session, department_id=binding.department_id, requested_by=requested_by
    )

    binding.is_active = False
    binding.disabled_at = _now()

    await session.flush()
    logger.info(
        "Telegram binding {} disabled by employee {}",
        binding.id,
        requested_by.id,
    )
    return binding


async def handle_chat_migration(
    session: AsyncSession,
    *,
    from_chat_id: int,
    to_chat_id: int,
) -> TelegramGroupBinding | None:
    """Follow a Telegram ``migrate_to_chat_id`` event.

    Telegram emits the migration signal when a group is upgraded to a
    supergroup; the old ``chat_id`` is replaced by a new ``-100…`` ID. We
    atomically update ``chat_id`` on the active binding (so future updates
    keep routing to the same Squad) and record the migration in
    ``migrated_to_chat_id`` / ``bot_status='migrated'`` for diagnostics.

    Returns the migrated binding, or ``None`` when no active binding was
    found for ``from_chat_id``.
    """
    stmt = select(TelegramGroupBinding).where(
        TelegramGroupBinding.chat_id == from_chat_id,
        TelegramGroupBinding.is_active.is_(True),
    )
    binding = (await session.execute(stmt)).scalar_one_or_none()
    if binding is None:
        return None

    binding.bot_status = "migrated"
    binding.migrated_to_chat_id = to_chat_id
    binding.chat_id = to_chat_id

    await session.flush()
    logger.info(
        "Telegram binding {} migrated chat_id {} -> {}",
        binding.id,
        from_chat_id,
        to_chat_id,
    )
    return binding


async def find_active_binding(
    session: AsyncSession,
    *,
    chat_id: int,
    message_thread_id: int | None,
) -> TelegramGroupBinding | None:
    """Return the active binding for ``(chat_id, message_thread_id)`` if any.

    Honors the same ``COALESCE(message_thread_id, -1)`` semantics as the
    ``uq_telegram_active_binding`` partial unique index: a ``None`` thread on
    the query matches bindings with ``message_thread_id IS NULL``; a numeric
    thread matches the exact value.
    """
    stmt = select(TelegramGroupBinding).where(
        TelegramGroupBinding.chat_id == chat_id,
        TelegramGroupBinding.is_active.is_(True),
    )
    if message_thread_id is None:
        stmt = stmt.where(TelegramGroupBinding.message_thread_id.is_(None))
    else:
        stmt = stmt.where(TelegramGroupBinding.message_thread_id == message_thread_id)

    return (await session.execute(stmt)).scalar_one_or_none()
