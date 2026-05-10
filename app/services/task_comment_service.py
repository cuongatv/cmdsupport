"""Task comments and activity stream service.

Comments live alongside the activity stream: every create/edit/delete on a
comment writes a corresponding TaskActivity row. Activity rows are domain
events local to the task and are deliberately separate from AuditLog (which is
owned by routers for cross-cutting compliance/audit reporting).

Mention parsing extracts ``<mention id="{uuid}">@Name</mention>`` markers from
the body and resolves them against the Employee table, returning only ACTIVE
employee UUIDs.

Like the other native task services, no function in this module commits — the
caller (router) owns the transaction boundary.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Employee, Task, TaskActivity, TaskComment
from app.services.task_constants import MAX_DESCRIPTION_BYTES

_MENTION_PATTERN = re.compile(r'<mention id="([^"]+)">')


async def create_comment(
    db: AsyncSession,
    task_id: uuid.UUID,
    body: str,
    author: Employee,
) -> TaskComment:
    """Create a comment on a non-deleted task and emit a "commented" activity."""
    _ensure_body_within_limit(body)

    task = await db.get(Task, task_id)
    if task is None:
        raise ValueError("task not found")
    if task.deleted_at is not None:
        raise ValueError("task deleted")

    mentions = await extract_mentions(body, db)

    comment = TaskComment(
        task_id=task_id,
        author_id=author.id,
        body=body,
    )
    db.add(comment)
    await db.flush()

    db.add(
        TaskActivity(
            task_id=task_id,
            actor_id=author.id,
            verb="commented",
            meta={
                "comment_id": str(comment.id),
                "mentions": [str(mention_id) for mention_id in mentions],
            },
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    return comment


async def update_comment(
    db: AsyncSession,
    comment_id: uuid.UUID,
    body: str,
    actor: Employee,
) -> TaskComment:
    """Edit a non-deleted comment, mark it edited, and emit a "comment_edited" activity."""
    _ensure_body_within_limit(body)

    comment = await db.get(TaskComment, comment_id)
    if comment is None or comment.deleted_at is not None:
        raise ValueError("comment not found")

    now = datetime.now(timezone.utc)
    comment.body = body
    comment.is_edited = True
    comment.updated_at = now

    db.add(
        TaskActivity(
            task_id=comment.task_id,
            actor_id=actor.id,
            verb="comment_edited",
            meta={"comment_id": str(comment.id)},
            created_at=now,
        )
    )
    await db.flush()
    return comment


async def delete_comment(
    db: AsyncSession,
    comment_id: uuid.UUID,
    actor: Employee,
) -> None:
    """Soft-delete a comment and emit a "comment_deleted" activity."""
    comment = await db.get(TaskComment, comment_id)
    if comment is None or comment.deleted_at is not None:
        raise ValueError("comment not found")

    now = datetime.now(timezone.utc)
    comment.deleted_at = now

    db.add(
        TaskActivity(
            task_id=comment.task_id,
            actor_id=actor.id,
            verb="comment_deleted",
            meta={"comment_id": str(comment.id)},
            created_at=now,
        )
    )
    await db.flush()


async def extract_mentions(body: str, db: AsyncSession) -> list[uuid.UUID]:
    """Return the de-duplicated list of ACTIVE employee UUIDs mentioned in body.

    Mentions are parsed from ``<mention id="{uuid}">`` markers. Invalid UUIDs,
    duplicates, missing employees, and inactive employees are dropped. The
    returned order matches first appearance in the body.
    """
    ordered_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()

    for raw in _MENTION_PATTERN.findall(body):
        try:
            mention_id = uuid.UUID(raw)
        except (ValueError, AttributeError):
            continue
        if mention_id in seen:
            continue
        seen.add(mention_id)
        ordered_ids.append(mention_id)

    if not ordered_ids:
        return []

    result = await db.execute(
        select(Employee.id).where(
            Employee.id.in_(ordered_ids),
            Employee.is_active.is_(True),
        )
    )
    valid_ids = set(result.scalars().all())
    return [mention_id for mention_id in ordered_ids if mention_id in valid_ids]


async def list_activities(db: AsyncSession, task_id: uuid.UUID) -> list[TaskActivity]:
    """Return all activities for a task in chronological order."""
    result = await db.execute(
        select(TaskActivity)
        .where(TaskActivity.task_id == task_id)
        .order_by(TaskActivity.created_at, TaskActivity.id)
    )
    return list(result.scalars().all())


def _ensure_body_within_limit(body: str) -> None:
    if len(body.encode("utf-8")) > MAX_DESCRIPTION_BYTES:
        raise ValueError("comment body too long")
