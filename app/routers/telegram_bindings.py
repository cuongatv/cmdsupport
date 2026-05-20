"""Telegram group binding REST API.

Endpoints under ``/api/telegram/bindings`` for Squad lead / admin management
of Telegram chat ↔ department bindings:

* ``POST   /``                — generate a one-time bind code for a chat.
* ``GET    /?department_id=`` — list active+pending bindings for a department.
* ``DELETE /{binding_id}``    — deactivate a binding.

Authorization is delegated to :mod:`app.services.telegram_binding_service`:
the requester must be a system admin OR an active primary lead-style member
of the binding's department. The service raises
:class:`BindingAuthorizationError`, which this router translates to 403.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee, TelegramGroupBinding
from app.schemas.telegram import BindCodeCreateRequest, TelegramBindingResponse
from app.services import telegram_binding_service
from app.services.audit_service import log_audit
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/telegram/bindings", tags=["telegram-bindings"])


@router.post(
    "",
    response_model=TelegramBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_bind_code(
    body: BindCodeCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> TelegramGroupBinding:
    """Mint a pending binding + ``CMD-XXXXXXXX`` bind code.

    The caller must be a system admin or a primary lead of the target
    department; authorization is enforced inside the service.
    """
    try:
        binding = await telegram_binding_service.generate_bind_code(
            db,
            department_id=body.department_id,
            default_task_project_id=body.default_task_project_id,
            requested_by=current_user,
        )
    except telegram_binding_service.BindingAuthorizationError as exc:
        logger.info(
            "telegram_bindings.create_denied employee_id={} department_id={}",
            current_user.id,
            body.department_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    await log_audit(
        db,
        current_user,
        "create",
        "telegram_binding",
        str(binding.id),
        reason=f"Bind code issued for department {body.department_id}",
    )
    await db.commit()
    await db.refresh(binding)
    return binding


@router.get("", response_model=list[TelegramBindingResponse])
async def list_bindings(
    department_id: uuid.UUID = Query(..., description="Department to filter by"),
    include_inactive: bool = Query(
        False,
        description=(
            "Include disabled bindings (``is_active=False`` AND ``disabled_at`` "
            "set). Active + pending rows are always returned."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> list[TelegramGroupBinding]:
    """List bindings for ``department_id``.

    Pending (``is_active=False`` AND ``bind_code IS NOT NULL``) and active
    (``is_active=True``) rows are always included. Disabled rows
    (``is_active=False`` AND ``disabled_at IS NOT NULL``) are included only
    when ``include_inactive=true``.
    """
    stmt = select(TelegramGroupBinding).where(
        TelegramGroupBinding.department_id == department_id
    )
    if not include_inactive:
        # Hide rows that were explicitly disabled (kept for audit) but still
        # surface pending rows (is_active=False but bind_code != NULL).
        stmt = stmt.where(
            (TelegramGroupBinding.is_active.is_(True))
            | (TelegramGroupBinding.bind_code.is_not(None))
        )
    stmt = stmt.order_by(
        TelegramGroupBinding.is_active.desc(),
        TelegramGroupBinding.created_at.desc(),
    )

    # Non-admins can only list bindings for departments they lead. We piggy-back
    # on the service-level authorization for *write* operations by checking
    # whether the user could create one for this department; if not, hide the
    # list rather than leaking row counts.
    if current_user.role != "admin":
        try:
            await telegram_binding_service._ensure_authorized(  # type: ignore[attr-defined]
                db,
                department_id=department_id,
                requested_by=current_user,
            )
        except telegram_binding_service.BindingAuthorizationError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
            ) from exc

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.delete(
    "/{binding_id}",
    response_model=TelegramBindingResponse,
)
async def delete_binding(
    binding_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> TelegramGroupBinding:
    """Deactivate a binding. Authorization mirrors :func:`create_bind_code`."""
    try:
        binding = await telegram_binding_service.disable_binding(
            db,
            binding_id=binding_id,
            requested_by=current_user,
        )
    except telegram_binding_service.BindingAuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    await log_audit(
        db,
        current_user,
        "delete",
        "telegram_binding",
        str(binding.id),
        reason="Binding disabled via REST API",
    )
    await db.commit()
    await db.refresh(binding)
    return binding


# Re-export for tests that want to assert behavior without touching the route
# decorators directly.
__all__ = [
    "router",
    "create_bind_code",
    "list_bindings",
    "delete_binding",
]
