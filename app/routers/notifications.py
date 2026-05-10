"""In-app notification polling and read API.

Endpoints are scoped to the authenticated user — every query filters by
``Notification.recipient_id == current_user.id``. The frontend polls these
endpoints (see ``app/services/task_notification_service`` for the no-websocket
design rationale).

Service functions (``task_notification_service``) only ``flush``; this router
owns the transaction boundary and calls ``db.commit()``.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee, Notification
from app.schemas.tasks import NotificationOut
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
async def list_notifications_endpoint(
    unread_only: bool = False,
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> list[Notification]:
    """List the current user's notifications, newest first."""
    stmt = select(Notification).where(Notification.recipient_id == current_user.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/unread-count")
async def unread_count_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> dict[str, int]:
    """Return the number of unread notifications for the current user."""
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.recipient_id == current_user.id,
            Notification.is_read.is_(False),
        )
    )
    return {"count": int(result.scalar() or 0)}


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_one_read_endpoint(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> Notification:
    """Mark a single notification as read. 404 if not found, 403 if not yours."""
    notification = await db.get(Notification, notification_id)
    if notification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="notification not found")
    if notification.recipient_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        await db.flush()
    await db.commit()
    await db.refresh(notification)
    return notification


@router.post("/read-all")
async def mark_all_read_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: Employee = Depends(get_current_user),
) -> dict[str, int]:
    """Mark every unread notification belonging to the current user as read."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(Notification)
        .where(
            Notification.recipient_id == current_user.id,
            Notification.read_at.is_(None),
        )
        .values(is_read=True, read_at=now)
    )
    await db.commit()
    return {"updated": int(result.rowcount or 0)}
