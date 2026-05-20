"""Telegram identity REST API.

Endpoints under ``/api/telegram/identities`` for end-user self-service of the
Telegram link flow:

* ``POST   /link-codes`` — mint a one-time ``LINK-XXXXXXXX`` code; the user
  pastes this into Telegram via ``/link``.
* ``GET    /me``         — fetch the current user's active identity.
* ``DELETE /me``         — revoke the current user's active identity.

The numeric ``telegram_user_id`` is intentionally never exposed — only
display fields surface back to the caller via :class:`TelegramIdentityResponse`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee, TelegramIdentity
from app.schemas.telegram import LinkCodeResponse, TelegramIdentityResponse
from app.services import telegram_identity_service
from app.services.audit_service import log_audit
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/telegram/identities", tags=["telegram-identities"])


async def _get_active_identity(
    db: AsyncSession, employee: Employee
) -> TelegramIdentity | None:
    """Return the current active identity for ``employee`` or ``None``."""
    stmt = select(TelegramIdentity).where(
        TelegramIdentity.employee_id == employee.id,
        TelegramIdentity.is_active.is_(True),
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.post(
    "/link-codes",
    response_model=LinkCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_link_code(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> LinkCodeResponse:
    """Issue a one-time link code for the current user.

    The code is returned to the caller exactly once. Existing pending codes
    for the same user are invalidated inside the service.
    """
    identity = await telegram_identity_service.generate_link_code(
        db, employee=current_user
    )

    # link_code / expires_at are always present immediately after generation;
    # assert non-None for the type checker and surface a 500 if the service
    # contract is violated.
    if identity.link_code is None or identity.link_code_expires_at is None:
        logger.error(
            "telegram_identities.link_code_missing identity_id={} employee_id={}",
            identity.id,
            current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Link code generation did not produce a code",
        )

    await log_audit(
        db,
        current_user,
        "create",
        "telegram_identity",
        str(identity.id),
        reason="Link code issued",
    )
    await db.commit()

    return LinkCodeResponse(
        link_code=identity.link_code,
        expires_at=identity.link_code_expires_at,
    )


@router.get("/me", response_model=TelegramIdentityResponse)
async def get_my_identity(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> TelegramIdentity:
    """Return the current user's active Telegram identity (404 if none)."""
    identity = await _get_active_identity(db, current_user)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Telegram identity for this user",
        )
    return identity


@router.delete("/me", response_model=TelegramIdentityResponse)
async def revoke_my_identity(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> TelegramIdentity:
    """Revoke the current user's active Telegram identity."""
    identity = await _get_active_identity(db, current_user)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active Telegram identity for this user",
        )

    revoked = await telegram_identity_service.revoke_identity(
        db,
        identity_id=identity.id,
        requested_by=current_user,
    )
    await log_audit(
        db,
        current_user,
        "delete",
        "telegram_identity",
        str(revoked.id),
        reason="Identity revoked by owner",
    )
    await db.commit()
    await db.refresh(revoked)
    return revoked


__all__ = [
    "router",
    "create_link_code",
    "get_my_identity",
    "revoke_my_identity",
]
