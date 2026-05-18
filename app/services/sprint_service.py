"""Sprint service layer (Phase 2 Agile).

Lightweight sprint container scoped to one ``TaskProject``. Owns the full
lifecycle (create / update / start / close / cancel / delete) plus the
project-level invariant "at most one active sprint per task project".

The invariant is enforced at two layers:

* Application pre-check via :func:`_ensure_no_active_sprint_for_project`
  raises :class:`ActiveSprintExistsError` so the router can map to ``409
  ACTIVE_SPRINT_EXISTS`` with a descriptive payload.
* Database partial unique index ``uix_sprints_one_active_per_project``
  (added in migration ``030``) closes the race window. The activate paths
  wrap the flush in a SAVEPOINT so a concurrent winner triggers
  ``IntegrityError``, which is translated back to the same domain error
  without poisoning the outer transaction.

Closing a sprint never silently completes work: any task whose
``state.group`` is not in :data:`_TERMINAL_STATE_GROUPS` gets its
``sprint_id`` cleared. Deleting a sprint unlinks linked tasks rather than
cascade-deleting them.

All mutations call :func:`app.services.audit_service.log_audit`; nothing
here commits — the router boundary owns the commit.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Employee, Sprint, Task, TaskProject, TaskState
from app.schemas.tasks import SprintCreate, SprintUpdate
from app.services.agile_governance import (
    PERMISSION_AGILE_SPRINT_CLOSE,
    maybe_record_permission_advisory,
)
from app.services.audit_service import log_audit

# Stable, ASCII-only error codes consumed by the router for HTTP translation.
# Kept here (not in task_constants) because they are sprint-domain-specific
# and not shared with other agile surfaces.
ACTIVE_SPRINT_EXISTS_ERROR_CODE: str = "ACTIVE_SPRINT_EXISTS"
INVALID_DATE_RANGE_ERROR_CODE: str = "INVALID_DATE_RANGE"
SPRINT_CLOSED_ERROR_CODE: str = "SPRINT_CLOSED"

# Audit action verbs. Mirrors the plan's required vocabulary so downstream
# observability and the future activity feed can pivot on stable strings.
_AUDIT_ACTION_CREATED: str = "sprint_created"
_AUDIT_ACTION_UPDATED: str = "sprint_updated"
_AUDIT_ACTION_STARTED: str = "sprint_started"
_AUDIT_ACTION_CLOSED: str = "sprint_closed"
_AUDIT_ACTION_CANCELLED: str = "sprint_cancelled"
_AUDIT_ACTION_DELETED: str = "sprint_deleted"
_AUDIT_ACTION_UNLINKED: str = "sprint_deleted_unlinked_n_tasks"

# "Open" tasks are those whose state group is NOT one of these terminal
# groups. Closing a sprint clears ``sprint_id`` on open tasks so the sprint's
# scope shrinks to only the work that actually finished inside it.
_TERMINAL_STATE_GROUPS: tuple[str, ...] = ("done", "cancelled")

# Status values that block further sprint assignment / re-activation.
_CLOSED_STATUSES: frozenset[str] = frozenset({"completed", "cancelled"})


class ActiveSprintExistsError(Exception):
    """Raised when a TaskProject already owns an active Sprint.

    Carries the offending ``task_project_id`` so the router can surface a
    payload that is useful to the UI (which sprint to point the user at).
    """

    code: str = ACTIVE_SPRINT_EXISTS_ERROR_CODE

    def __init__(self, task_project_id: uuid.UUID) -> None:
        super().__init__(
            f"task_project {task_project_id} already has an active sprint"
        )
        self.task_project_id = task_project_id


def _validate_date_range(
    start: date | datetime | None,
    end: date | datetime | None,
) -> None:
    """Raise ``ValueError(INVALID_DATE_RANGE)`` when ``start > end``.

    Either side may be ``None`` (open-ended sprints are valid). Inputs may be
    ``date`` or ``datetime``; both are normalised to ``date`` before
    comparison so a mixed update (schema → ``datetime``, ORM → ``date``)
    never crashes with a ``TypeError``.
    """
    if start is None or end is None:
        return
    s = start.date() if isinstance(start, datetime) else start
    e = end.date() if isinstance(end, datetime) else end
    if s > e:
        raise ValueError(INVALID_DATE_RANGE_ERROR_CODE)


async def _ensure_no_active_sprint_for_project(
    db: AsyncSession,
    task_project_id: uuid.UUID,
    *,
    exclude_sprint_id: uuid.UUID | None = None,
) -> None:
    """Raise :class:`ActiveSprintExistsError` if another sprint is active."""
    stmt = select(Sprint.id).where(
        Sprint.task_project_id == task_project_id,
        Sprint.status == "active",
    )
    if exclude_sprint_id is not None:
        stmt = stmt.where(Sprint.id != exclude_sprint_id)
    result = await db.execute(stmt.limit(1))
    if result.scalar_one_or_none() is not None:
        raise ActiveSprintExistsError(task_project_id)


async def _flush_with_active_uniqueness(
    db: AsyncSession,
    task_project_id: uuid.UUID,
) -> None:
    """Flush inside a SAVEPOINT, translating the partial-unique race to a
    domain error.

    The pre-check (:func:`_ensure_no_active_sprint_for_project`) handles the
    common case; this guards the small window where a concurrent caller
    wins the race and the DB rejects our insert/update via the
    ``uix_sprints_one_active_per_project`` partial unique index. Using a
    nested transaction keeps the outer session usable so the router can
    surface a clean ``409`` without a 500-grade transaction abort.
    """
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        if "uix_sprints_one_active_per_project" in str(exc).lower():
            raise ActiveSprintExistsError(task_project_id) from exc
        raise


async def _get_existing_sprint(db: AsyncSession, sprint_id: uuid.UUID) -> Sprint:
    sprint = await db.get(Sprint, sprint_id)
    if sprint is None:
        raise ValueError("sprint not found")
    return sprint


async def create_sprint(
    db: AsyncSession,
    task_project_id: uuid.UUID,
    data: SprintCreate,
    *,
    actor: Employee,
) -> Sprint:
    """Create a sprint (default status ``planned``) without committing.

    When ``data.status == 'active'`` the activate invariant is enforced just
    like :func:`start_sprint`, so the caller does not need a two-step
    create-then-start dance.
    """
    project = await db.get(TaskProject, task_project_id)
    if project is None:
        raise ValueError("task_project not found")

    _validate_date_range(data.start_date, data.end_date)

    if data.status == "active":
        await _ensure_no_active_sprint_for_project(db, task_project_id)

    sprint = Sprint(
        task_project_id=task_project_id,
        name=data.name,
        goal=data.goal,
        start_date=data.start_date,
        end_date=data.end_date,
        status=data.status,
    )
    db.add(sprint)
    await _flush_with_active_uniqueness(db, task_project_id)
    await log_audit(db, actor, _AUDIT_ACTION_CREATED, "sprint", str(sprint.id))
    await db.flush()
    return sprint


async def update_sprint(
    db: AsyncSession,
    sprint_id: uuid.UUID,
    data: SprintUpdate,
    *,
    actor: Employee,
) -> Sprint:
    """Patch mutable fields on a sprint without committing.

    Refuses an update that would re-violate the date-range or active-uniqueness
    invariants. The status transition to ``active`` here is treated the same
    as calling :func:`start_sprint` (pre-check + SAVEPOINT-guarded flush).
    """
    sprint = await _get_existing_sprint(db, sprint_id)
    provided = data.model_dump(exclude_unset=True)
    if not provided:
        return sprint

    next_start = provided.get("start_date", sprint.start_date)
    next_end = provided.get("end_date", sprint.end_date)
    _validate_date_range(next_start, next_end)

    next_status = provided.get("status", sprint.status)
    activating = next_status == "active" and sprint.status != "active"
    if activating:
        await _ensure_no_active_sprint_for_project(
            db, sprint.task_project_id, exclude_sprint_id=sprint.id
        )

    for field, value in provided.items():
        setattr(sprint, field, value)

    if activating:
        await _flush_with_active_uniqueness(db, sprint.task_project_id)
    else:
        await db.flush()

    await log_audit(db, actor, _AUDIT_ACTION_UPDATED, "sprint", str(sprint.id))
    await db.flush()
    return sprint


async def start_sprint(
    db: AsyncSession,
    sprint_id: uuid.UUID,
    *,
    actor: Employee,
) -> Sprint:
    """Transition a sprint to ``active``. Idempotent on already-active sprints.

    Cancelled/completed sprints cannot be restarted (the lifecycle is
    one-shot); attempting to start such a sprint raises
    ``ValueError(SPRINT_CLOSED)`` which the router maps to ``409``.
    """
    sprint = await _get_existing_sprint(db, sprint_id)
    if sprint.status == "active":
        return sprint
    if sprint.status in _CLOSED_STATUSES:
        raise ValueError(SPRINT_CLOSED_ERROR_CODE)

    await _ensure_no_active_sprint_for_project(
        db, sprint.task_project_id, exclude_sprint_id=sprint.id
    )
    sprint.status = "active"
    await _flush_with_active_uniqueness(db, sprint.task_project_id)
    await log_audit(db, actor, _AUDIT_ACTION_STARTED, "sprint", str(sprint.id))
    await db.flush()
    return sprint


async def close_sprint(
    db: AsyncSession,
    sprint_id: uuid.UUID,
    *,
    actor: Employee,
) -> tuple[Sprint, dict[str, str] | None]:
    """Mark a sprint ``completed`` and unlink still-open tasks.

    Tasks already in a terminal-group state (done / cancelled) stay linked
    to the closed sprint so the historical scope is preserved. Open tasks
    have ``sprint_id`` set to NULL so they remain in the backlog for the
    next planning round. The unlink emits a ``sprint_deleted_unlinked_n_tasks``
    audit row (with the count in the reason) only when at least one task
    was actually unlinked.

    Phase 5 governance (Stage A): when the actor lacks
    ``agile.sprint.close`` AND ``settings.FEATURE_AGILE_PHASE_5`` is on,
    a ``permission_denied_advisory`` audit row is written and the second
    tuple element carries the advisory metadata for the response. The
    sprint is still closed — Stage A is advisory-only.
    """
    sprint = await _get_existing_sprint(db, sprint_id)
    if sprint.status in _CLOSED_STATUSES:
        return sprint, None

    open_ids_stmt = (
        select(Task.id)
        .join(TaskState, TaskState.id == Task.state_id)
        .where(
            Task.sprint_id == sprint.id,
            TaskState.group.notin_(_TERMINAL_STATE_GROUPS),
            Task.deleted_at.is_(None),
        )
    )
    open_ids = list((await db.execute(open_ids_stmt)).scalars().all())
    if open_ids:
        await db.execute(
            update(Task).where(Task.id.in_(open_ids)).values(sprint_id=None)
        )
        await log_audit(
            db,
            actor,
            _AUDIT_ACTION_UNLINKED,
            "sprint",
            str(sprint.id),
            reason=f"unlinked {len(open_ids)} open task(s) on close",
        )

    sprint.status = "completed"
    await db.flush()
    await log_audit(db, actor, _AUDIT_ACTION_CLOSED, "sprint", str(sprint.id))

    advisory = await maybe_record_permission_advisory(
        db,
        actor=actor,
        permission=PERMISSION_AGILE_SPRINT_CLOSE,
        resource_type="sprint",
        resource_id=sprint.id,
    )

    await db.flush()
    return sprint, advisory


async def cancel_sprint(
    db: AsyncSession,
    sprint_id: uuid.UUID,
    *,
    actor: Employee,
) -> Sprint:
    """Mark a sprint ``cancelled`` without committing.

    Cancel does NOT touch linked tasks (the user can decide whether to keep
    the historical link or move them via a separate flow). Cancelling a
    sprint that is already terminal is a no-op so the caller can be naive.
    """
    sprint = await _get_existing_sprint(db, sprint_id)
    if sprint.status in _CLOSED_STATUSES:
        return sprint
    sprint.status = "cancelled"
    await db.flush()
    await log_audit(db, actor, _AUDIT_ACTION_CANCELLED, "sprint", str(sprint.id))
    await db.flush()
    return sprint


async def delete_sprint(
    db: AsyncSession,
    sprint_id: uuid.UUID,
    *,
    actor: Employee,
) -> None:
    """Hard-delete a sprint, unlinking referencing tasks first.

    The FK ``tasks.sprint_id -> sprints.id`` is ``ON DELETE SET NULL`` at the
    DB layer, so even without this explicit unlink the cascade would be
    safe. We still issue the explicit UPDATE so ORM identity-map state
    stays consistent with what the DB will see post-commit and so the
    audit reason can quote the unlinked count.
    """
    sprint = await _get_existing_sprint(db, sprint_id)
    linked_ids_stmt = select(Task.id).where(Task.sprint_id == sprint.id)
    linked_ids = list((await db.execute(linked_ids_stmt)).scalars().all())
    if linked_ids:
        await db.execute(
            update(Task).where(Task.id.in_(linked_ids)).values(sprint_id=None)
        )
        await log_audit(
            db,
            actor,
            _AUDIT_ACTION_UNLINKED,
            "sprint",
            str(sprint.id),
            reason=f"unlinked {len(linked_ids)} task(s) on delete",
        )

    await db.delete(sprint)
    await log_audit(db, actor, _AUDIT_ACTION_DELETED, "sprint", str(sprint_id))
    await db.flush()


async def list_sprints(
    db: AsyncSession, task_project_id: uuid.UUID
) -> list[Sprint]:
    """Return all sprints for a project, oldest first."""
    result = await db.execute(
        select(Sprint)
        .where(Sprint.task_project_id == task_project_id)
        .order_by(Sprint.created_at, Sprint.id)
    )
    return list(result.scalars().all())


async def get_sprint(db: AsyncSession, sprint_id: uuid.UUID) -> Sprint:
    """Return a sprint by id; raise ``ValueError`` if not found."""
    return await _get_existing_sprint(db, sprint_id)


async def assert_sprint_assignable(
    db: AsyncSession, sprint_id: uuid.UUID
) -> Sprint:
    """Resolve a sprint and refuse it if it has already closed/cancelled.

    Intended for T8 ``task_service`` callers that need to validate a
    ``Task.sprint_id`` assignment before persisting. Centralising the check
    keeps the SPRINT_CLOSED contract in one place.
    """
    sprint = await _get_existing_sprint(db, sprint_id)
    if sprint.status in _CLOSED_STATUSES:
        raise ValueError(SPRINT_CLOSED_ERROR_CODE)
    return sprint
