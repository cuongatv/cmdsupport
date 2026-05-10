"""Task attachment metadata service.

This service owns DB metadata for ``TaskAttachment`` rows. It deliberately
does NOT call ``storage_service`` — actual MinIO/S3 I/O is the router's
responsibility. The router uploads bytes after this service creates a
metadata row, and removes the underlying object after this service returns
the ``storage_key`` from ``delete_attachment``.

Validation rules enforced here (``validate_upload``):
    * size must not exceed ``MAX_ATTACHMENT_BYTES``;
    * file extension must not be in the dangerous-extension deny list
      (``.exe``, ``.bat``, ``.ps1``, ``.sh``, ``.scr``, ``.com`` —
      case-insensitive);
    * the parent task must exist and not be soft-deleted;
    * total attachment count for the task must remain below
      ``MAX_ATTACHMENTS_PER_TASK``.

Like the rest of the native task services, this module never commits — the
caller (router) owns the transaction boundary.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Employee, Task, TaskActivity, TaskAttachment
from app.services.task_constants import MAX_ATTACHMENT_BYTES, MAX_ATTACHMENTS_PER_TASK

# Case-insensitive set of denied filename extensions (with leading dot).
_DENIED_EXTENSIONS: frozenset[str] = frozenset(
    {".exe", ".bat", ".ps1", ".sh", ".scr", ".com"}
)


async def validate_upload(
    filename: str,
    size_bytes: int,
    task_id: uuid.UUID,
    db: AsyncSession,
) -> Task:
    """Validate that an attachment may be created on the given task.

    Raises ``ValueError`` with a descriptive message when the upload is:
    oversized, has a denied extension, would exceed the per-task count
    limit, or targets a missing/soft-deleted task. On success returns the
    loaded ``Task`` so callers can derive the project id for storage keys
    without an extra round trip.
    """
    if size_bytes > MAX_ATTACHMENT_BYTES:
        raise ValueError("attachment exceeds maximum size")

    extension = os.path.splitext(filename or "")[1].lower()
    if extension in _DENIED_EXTENSIONS:
        raise ValueError("attachment extension not allowed")

    task = await db.get(Task, task_id)
    if task is None:
        raise ValueError("task not found")
    if task.deleted_at is not None:
        raise ValueError("task deleted")

    existing_count = await db.scalar(
        select(func.count(TaskAttachment.id)).where(
            TaskAttachment.task_id == task_id
        )
    )
    if (existing_count or 0) >= MAX_ATTACHMENTS_PER_TASK:
        raise ValueError("attachment count limit exceeded")

    return task


async def create_attachment_metadata(
    db: AsyncSession,
    task_id: uuid.UUID,
    filename: str,
    content_type: str,
    size_bytes: int,
    actor: Employee,
) -> TaskAttachment:
    """Validate and persist a ``TaskAttachment`` metadata row.

    The ``storage_key`` is generated using the canonical pattern
    ``task-attachments/{task_project_id}/{task_id}/{uuid}-{filename}``.
    The router is responsible for uploading the bytes to MinIO/S3 using
    the returned ``storage_key``.

    Emits an ``attachment_added`` ``TaskActivity`` row alongside the
    metadata so the activity stream stays in sync.

    Does not commit — the caller owns the transaction.
    """
    task = await validate_upload(filename, size_bytes, task_id, db)

    storage_key = (
        f"task-attachments/{task.task_project_id}/{task_id}/"
        f"{uuid.uuid4()}-{filename}"
    )

    attachment = TaskAttachment(
        task_id=task_id,
        uploaded_by_id=actor.id,
        filename=filename,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=size_bytes,
    )
    db.add(attachment)
    await db.flush()

    db.add(
        TaskActivity(
            task_id=task_id,
            actor_id=actor.id,
            verb="attachment_added",
            meta={
                "attachment_id": str(attachment.id),
                "filename": filename,
                "size_bytes": size_bytes,
            },
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    return attachment


async def get_attachment(
    db: AsyncSession,
    attachment_id: uuid.UUID,
) -> TaskAttachment | None:
    """Return the attachment by id, or ``None`` if missing."""
    return await db.get(TaskAttachment, attachment_id)


async def list_attachments(
    db: AsyncSession,
    task_id: uuid.UUID,
) -> list[TaskAttachment]:
    """Return all live attachments for a task in chronological order."""
    result = await db.execute(
        select(TaskAttachment)
        .where(TaskAttachment.task_id == task_id)
        .order_by(TaskAttachment.created_at, TaskAttachment.id)
    )
    return list(result.scalars().all())


async def delete_attachment(
    db: AsyncSession,
    attachment_id: uuid.UUID,
    actor: Employee,
) -> str:
    """Delete a ``TaskAttachment`` row and return its ``storage_key``.

    The caller (router) is responsible for removing the underlying object
    from MinIO/S3 using the returned key. Emits an ``attachment_removed``
    activity so the deletion is visible in the task activity stream.

    Does not commit — the caller owns the transaction.
    """
    attachment = await db.get(TaskAttachment, attachment_id)
    if attachment is None:
        raise ValueError("attachment not found")

    storage_key = attachment.storage_key
    task_id = attachment.task_id
    filename = attachment.filename
    size_bytes = attachment.size_bytes

    await db.delete(attachment)
    await db.flush()

    db.add(
        TaskActivity(
            task_id=task_id,
            actor_id=actor.id,
            verb="attachment_removed",
            meta={
                "attachment_id": str(attachment_id),
                "filename": filename,
                "size_bytes": size_bytes,
            },
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    return storage_key
