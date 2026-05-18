"""Task CRUD, subtask, versioning, position, and soft-delete service."""

from __future__ import annotations

import copy
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    Source,
    Sprint,
    Task,
    TaskActivity,
    TaskAssignee,
    TaskDependency,
    TaskKnowledgeLink,
    TaskLabel,
    TaskLabelLink,
    TaskProject,
    TaskState,
    WikiPage,
)
from app.schemas.tasks import TaskCreate, TaskForwardRequest, TaskUpdate
from app.services.agile_governance import (
    PERMISSION_AGILE_DOD_BYPASS,
    PERMISSION_AGILE_WIP_OVERRIDE,
    dod_checklist_has_incomplete_items,
    maybe_record_permission_advisory,
)
from app.services.audit_service import log_audit
from app.services.sprint_service import assert_sprint_assignable
from app.services.task_access_service import is_eligible_assignee
from app.services.task_constants import (
    ACTIVITY_VERB_KNOWLEDGE_LINK_ADDED,
    ACTIVITY_VERB_KNOWLEDGE_LINK_REMOVED,
    ACTIVITY_VERB_SPRINT_ID_CLEARED_ON_PROJECT_MOVE,
    ACTIVITY_VERB_TASK_BLOCKED,
    ACTIVITY_VERB_TASK_UNBLOCKED,
    INITIAL_TASK_VERSION,
    MAX_SUBTASK_DEPTH,
    POSITION_GAP,
    WIP_EXCEEDED_ERROR_CODE,
)
from app.services.task_notification_service import notify_wip_exceeded
from app.services.task_project_service import get_project_template

# Stable, ASCII-only error codes for the dependency surface. Consumed by the
# router's translator to produce structured 409 payloads.
BLOCKED_CYCLE_ERROR_CODE: str = "BLOCKED_CYCLE"
DUPLICATE_DEPENDENCY_ERROR_CODE: str = "DUPLICATE_DEPENDENCY"
# Phase 4 — Knowledge integration: stable error code for duplicate (task, page)
# pairs. The router translator maps this to a structured 409 payload.
DUPLICATE_KNOWLEDGE_LINK_ERROR_CODE: str = "DUPLICATE_KNOWLEDGE_LINK"


class WipExceededError(Exception):
    """Raised when a task move is rejected by an ``enforce`` WIP policy.

    Carries the stable error ``code`` plus contextual ``state_id``, ``limit``,
    and ``current_count`` so the router (or any caller) can translate the
    failure into an HTTP 409 with a structured detail payload.
    """

    def __init__(
        self,
        *,
        state_id: uuid.UUID,
        limit: int,
        current_count: int,
        code: str = WIP_EXCEEDED_ERROR_CODE,
    ) -> None:
        self.code = code
        self.state_id = state_id
        self.limit = limit
        self.current_count = current_count
        super().__init__(
            f"{code}: state {state_id} has {current_count} tasks "
            f"(limit {limit})"
        )


async def create_task(
    db: AsyncSession,
    project_id: uuid.UUID,
    data: TaskCreate,
    creator: Employee,
) -> Task:
    """Create a task with initial version and next lane position without committing."""
    project = await db.get(TaskProject, project_id)
    if project is None or project.is_archived:
        raise ValueError("project not found")

    if data.state_id is None:
        # The router resolves the default state before calling the service; if
        # we still got here without one, treat it as a programmer error rather
        # than silently picking a state, which could land tasks in the wrong
        # column.
        raise ValueError("state_id is required")
    await _ensure_state_in_project(db, data.state_id, project_id)

    for employee_id in data.assignee_ids:
        employee = await db.get(Employee, employee_id)
        if employee is None:
            raise ValueError("employee not found")
        if not employee.is_active:
            raise ValueError("inactive employee cannot be assigned")
        if not await is_eligible_assignee(db, employee, project):
            raise ValueError("employee is out of scope for this task project")

    if data.parent_task_id is not None:
        parent = await _get_task_in_project(db, data.parent_task_id, project_id)
        if parent is None:
            raise ValueError("parent task not found")
        if MAX_SUBTASK_DEPTH <= 1 and parent.parent_task_id is not None:
            raise ValueError("max subtask depth exceeded")

    # Phase 2: sprint must belong to the same project to keep cross-project
    # work out of a sprint's scope. Sprint membership is otherwise unconstrained
    # (planned/active/completed/cancelled all accept new tasks).
    if data.sprint_id is not None:
        sprint = await db.get(Sprint, data.sprint_id)
        if sprint is None or sprint.task_project_id != project_id:
            raise ValueError("sprint not found in this project")

    # Phase 2 DoR/DoD snapshot: copy the project template into the new task at
    # create time. The snapshot is one-time-only — later template edits never
    # touch existing tasks. Explicit client-provided checklists override the
    # snapshot (treat ``None`` as "snapshot from template").
    snapshot_dor: list | None = data.dor_checklist
    snapshot_dod: list | None = data.dod_checklist
    if snapshot_dor is None or snapshot_dod is None:
        template = await get_project_template(db, project_id)
        if template is not None:
            if snapshot_dor is None and template.dor_template:
                snapshot_dor = copy.deepcopy(template.dor_template)
            if snapshot_dod is None and template.dod_template:
                snapshot_dod = copy.deepcopy(template.dod_template)

    task = Task(
        task_project_id=project_id,
        state_id=data.state_id,
        title=data.title,
        description=data.description,
        priority=data.priority,
        parent_task_id=data.parent_task_id,
        reporter_id=data.reporter_id,
        created_by_id=creator.id,
        due_date=data.due_date,
        position=await _next_position_in_state(db, data.state_id, project_id),
        version=INITIAL_TASK_VERSION,
        task_type=data.task_type,
        estimate=data.estimate,
        story_points=data.story_points,
        acceptance_criteria=data.acceptance_criteria,
        dor_checklist=snapshot_dor,
        dod_checklist=snapshot_dod,
        sprint_id=data.sprint_id,
    )
    db.add(task)
    await db.flush()

    db.add(
        TaskActivity(
            task_id=task.id,
            actor_id=creator.id,
            verb="created",
        )
    )

    for employee_id in data.assignee_ids:
        db.add(TaskAssignee(task_id=task.id, employee_id=employee_id))
        db.add(
            TaskActivity(
                task_id=task.id,
                actor_id=creator.id,
                verb="assigned",
                field_name="assignee_id",
                new_value=str(employee_id),
            )
        )

    if data.label_ids:
        await _ensure_labels_in_project(db, data.label_ids, project_id)
        for label_id in data.label_ids:
            db.add(TaskLabelLink(task_id=task.id, label_id=label_id))

    await log_audit(db, creator, "create", "task", str(task.id))
    await db.flush()
    return task


async def get_task(
    db: AsyncSession,
    task_id: uuid.UUID,
    include_deleted: bool = False,
) -> Task | None:
    """Return a task by id, excluding soft-deleted tasks by default."""
    stmt = _task_select().where(Task.id == task_id)
    if not include_deleted:
        stmt = stmt.where(Task.deleted_at.is_(None))

    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_tasks(
    db: AsyncSession,
    project_id: uuid.UUID,
    state_id: uuid.UUID | None = None,
    include_deleted: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[Task]:
    """List tasks by project, optionally filtered by state, ordered for Kanban display."""
    stmt = _task_select().where(Task.task_project_id == project_id)
    if state_id is not None:
        stmt = stmt.where(Task.state_id == state_id)
    if not include_deleted:
        stmt = stmt.where(Task.deleted_at.is_(None))
    stmt = stmt.order_by(Task.position, Task.created_at).limit(limit).offset(offset)

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_task(
    db: AsyncSession,
    task_id: uuid.UUID,
    data: TaskUpdate,
    actor: Employee,
) -> Task:
    """Update a non-deleted task using optimistic concurrency without committing.

    Phase 2 semantics additions:

    * ``blocked_reason`` transitions: setting it from empty → non-empty flips
      the task to "blocked" and stamps ``blocked_at`` + ``blocked_by_id``;
      setting it from non-empty → empty/None clears all three. The blocked
      transitions emit dedicated ``task_blocked`` / ``task_unblocked``
      activity verbs (NOT a generic ``blocked_reason_changed``) so the
      activity feed reads naturally for end users.
    * ``sprint_id`` assignment is validated against
      :func:`sprint_service.assert_sprint_assignable` so a task cannot be
      reattached to a closed/cancelled sprint, and against the task's own
      ``task_project_id`` so cross-project sprint leakage is impossible
      (mirrors the same check on :func:`create_task`).
    """
    task = await get_task(db, task_id)
    if task is None:
        raise ValueError("not found")

    if data.version != task.version:
        raise ValueError(
            f"version conflict: expected {task.version}, got {data.version}"
        )

    # ``exclude_unset=True`` only — we still need to see fields the client
    # explicitly set to ``None`` so blocked_reason=None can clear the block.
    # The generic loop below additionally filters ``None`` so non-blocked
    # fields keep their pre-Phase-2 "None means don't change" semantics.
    set_fields = data.model_dump(exclude_unset=True)
    set_fields.pop("version", None)

    block_clear_requested = (
        "blocked_reason" in set_fields and not set_fields.get("blocked_reason")
    )
    block_set_requested = bool(set_fields.get("blocked_reason"))

    # Generic loop: skip ``blocked_*`` (handled below explicitly) and skip
    # ``None`` values to preserve the pre-Phase-2 contract on non-blocked
    # fields (e.g. ``description=None`` should NOT clear the description).
    skip_fields = {"blocked_reason", "blocked_at", "blocked_by_id"}
    changes = {
        field: value
        for field, value in set_fields.items()
        if field not in skip_fields and value is not None
    }

    project_move_cleared_sprint_id: uuid.UUID | None = None
    target_project_id = changes.get("task_project_id", task.task_project_id)
    if "task_project_id" in changes and changes["task_project_id"] != task.task_project_id:
        target_project = await db.get(TaskProject, target_project_id)
        if target_project is None or target_project.is_archived:
            raise ValueError("project not found")
        if "state_id" not in changes:
            raise ValueError("state_id is required when moving task across projects")
        if task.sprint_id is not None and "sprint_id" not in changes:
            project_move_cleared_sprint_id = task.sprint_id
            changes["sprint_id"] = None

    for field, new_value in changes.items():
        if field == "state_id":
            await _ensure_state_in_project(db, new_value, target_project_id)
        if field == "parent_task_id":
            await _ensure_parent_allowed(db, task, new_value)
        if field == "sprint_id" and new_value is not None:
            sprint = await assert_sprint_assignable(db, new_value)
            if sprint.task_project_id != target_project_id:
                raise ValueError("sprint not found in this project")

        old_value = getattr(task, field)
        if old_value == new_value:
            continue

        setattr(task, field, new_value)
        activity_verb = f"{field}_changed"
        if field == "sprint_id" and project_move_cleared_sprint_id == old_value:
            activity_verb = ACTIVITY_VERB_SPRINT_ID_CLEARED_ON_PROJECT_MOVE
        db.add(
            TaskActivity(
                task_id=task.id,
                actor_id=actor.id,
                verb=activity_verb,
                field_name=field,
                old_value=_stringify_activity_value(old_value),
                new_value=_stringify_activity_value(new_value),
            )
        )

    # Explicit blocked/unblocked handling. Runs AFTER the generic loop so the
    # activity feed shows other field changes first, then the blocked verb.
    if block_set_requested:
        new_reason = set_fields["blocked_reason"]
        was_unblocked = not task.blocked_reason
        old_reason = task.blocked_reason
        if old_reason != new_reason:
            task.blocked_reason = new_reason
            if was_unblocked:
                task.blocked_at = datetime.now(timezone.utc)
                task.blocked_by_id = actor.id
            db.add(
                TaskActivity(
                    task_id=task.id,
                    actor_id=actor.id,
                    verb=ACTIVITY_VERB_TASK_BLOCKED,
                    field_name="blocked_reason",
                    old_value=_stringify_activity_value(old_reason),
                    new_value=new_reason,
                )
            )
    elif block_clear_requested and task.blocked_reason is not None:
        old_reason = task.blocked_reason
        task.blocked_reason = None
        task.blocked_at = None
        task.blocked_by_id = None
        db.add(
            TaskActivity(
                task_id=task.id,
                actor_id=actor.id,
                verb=ACTIVITY_VERB_TASK_UNBLOCKED,
                field_name="blocked_reason",
                old_value=old_reason,
            )
        )

    task.version += 1
    await log_audit(db, actor, "update", "task", str(task.id))
    await db.flush()
    return task


# ---------------------------------------------------------------------------
# Phase 2 — Task dependency CRUD
# ---------------------------------------------------------------------------


async def add_task_dependency(
    db: AsyncSession,
    from_task_id: uuid.UUID,
    to_task_id: uuid.UUID,
    dep_type: str = "blocks",
    *,
    actor: Employee,
) -> TaskDependency:
    """Create a ``(from_task_id → to_task_id)`` dependency edge.

    Semantics: ``from_task_id`` depends on ``to_task_id`` (``from`` is
    blocked by ``to``). Raises:

    * :class:`ValueError` with code ``BLOCKED_CYCLE`` if the new edge would
      complete a cycle through existing ``blocks`` edges.
    * :class:`ValueError` with code ``DUPLICATE_DEPENDENCY`` if the pair is
      already present (both pre-check and SAVEPOINT-translated unique-index
      race land in the same domain error).
    * :class:`ValueError` ``"task not found"`` when either endpoint is
      missing or soft-deleted.

    Does NOT commit. The caller (router) owns the transaction boundary;
    cross-department access checks must also be done by the caller because
    permission-engine awareness is a router-layer concern.
    """
    if from_task_id == to_task_id:
        # Defence-in-depth: the CHECK constraint also rejects this at the DB
        # layer, but raising in the service gives a friendlier error and
        # avoids the IntegrityError noise in the logs.
        raise ValueError("dependency cannot reference the same task on both ends")

    from_task = await get_task(db, from_task_id)
    to_task = await get_task(db, to_task_id)
    if from_task is None or to_task is None:
        raise ValueError("task not found")

    # Cycle detection. We are adding (from → to) meaning "from depends on
    # to". A cycle exists iff ``to`` already (transitively) depends on
    # ``from`` through existing ``blocks`` edges. Walk forward from ``to``
    # through (from_task_id → to_task_id) edges and check whether we hit
    # ``from``. PostgreSQL recursive CTE keeps this single-roundtrip even
    # for deep chains.
    cycle_stmt = text(
        """
        WITH RECURSIVE deps AS (
            SELECT to_task_id AS reachable
            FROM task_dependencies
            WHERE from_task_id = :start_id AND dep_type = 'blocks'
            UNION
            SELECT td.to_task_id
            FROM task_dependencies td
            JOIN deps d ON td.from_task_id = d.reachable
            WHERE td.dep_type = 'blocks'
        )
        SELECT 1 FROM deps WHERE reachable = :end_id LIMIT 1
        """
    )
    cycle_hit = await db.scalar(
        cycle_stmt, {"start_id": to_task_id, "end_id": from_task_id}
    )
    if cycle_hit is not None:
        raise ValueError(BLOCKED_CYCLE_ERROR_CODE)

    # Duplicate pre-check. The DB unique constraint is the source of truth;
    # this is the cheaper happy-path response that avoids a SAVEPOINT.
    existing = await db.scalar(
        select(TaskDependency.id).where(
            TaskDependency.from_task_id == from_task_id,
            TaskDependency.to_task_id == to_task_id,
        )
    )
    if existing is not None:
        raise ValueError(DUPLICATE_DEPENDENCY_ERROR_CODE)

    dep = TaskDependency(
        from_task_id=from_task_id,
        to_task_id=to_task_id,
        dep_type=dep_type,
        created_by_id=actor.id,
    )
    db.add(dep)
    # SAVEPOINT-guarded flush translates the small race window where two
    # callers slip past the pre-check into the same domain error rather
    # than poisoning the outer transaction with an IntegrityError.
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        if "uq_task_dep_pair" in str(exc).lower():
            raise ValueError(DUPLICATE_DEPENDENCY_ERROR_CODE) from exc
        raise

    await log_audit(db, actor, "create", "task_dependency", str(dep.id))
    await db.flush()
    return dep


async def remove_task_dependency(
    db: AsyncSession,
    from_task_id: uuid.UUID,
    to_task_id: uuid.UUID,
    *,
    actor: Employee,
) -> None:
    """Delete the ``(from_task_id → to_task_id)`` dependency row.

    Raises :class:`ValueError` ``"dependency not found"`` when the edge is
    not present. Does NOT commit.
    """
    dep = await db.scalar(
        select(TaskDependency).where(
            TaskDependency.from_task_id == from_task_id,
            TaskDependency.to_task_id == to_task_id,
        )
    )
    if dep is None:
        raise ValueError("dependency not found")
    dep_id = dep.id
    await db.delete(dep)
    await log_audit(db, actor, "delete", "task_dependency", str(dep_id))
    await db.flush()


async def list_task_dependencies(
    db: AsyncSession,
    task_id: uuid.UUID,
) -> list[TaskDependency]:
    """Return outgoing dependencies for a task (what this task depends on).

    Outgoing means rows where ``from_task_id == task_id`` — i.e. the tasks
    that block ``task_id``. The inverse direction ("tasks I block") is not
    returned here; future surfaces that need it can call with the inverse
    filter directly.
    """
    result = await db.execute(
        select(TaskDependency)
        .where(TaskDependency.from_task_id == task_id)
        .order_by(TaskDependency.created_at, TaskDependency.id)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Phase 4 — Task knowledge link CRUD
# ---------------------------------------------------------------------------


async def add_knowledge_link(
    db: AsyncSession,
    task_id: uuid.UUID,
    wiki_page_id: uuid.UUID | None = None,
    link_type: str = "reference",
    *,
    actor: Employee,
    source_id: uuid.UUID | None = None,
) -> TaskKnowledgeLink:
    """Create a task knowledge link to exactly one wiki page or source.

    Gated on :data:`settings.FEATURE_AGILE_PHASE_4`; raises
    :class:`PermissionError` carrying the ``FEATURE_DISABLED`` code when the
    flag is off so the router can translate it to a 403. Raises:

    * :class:`ValueError` ``"task not found"`` if the task is missing or
      soft-deleted.
    * :class:`ValueError` ``"wiki page not found"`` if a wiki target is missing.
    * :class:`ValueError` ``"source not found"`` if a source target is missing.
    * :class:`ValueError` with code ``DUPLICATE_KNOWLEDGE_LINK`` if the
      ``(task_id, wiki_page_id)`` pair is already present (both pre-check
      and SAVEPOINT-translated unique-index race land here).

    Cross-department / per-task access checks must be done by the caller
    (router) before reaching this service — permission engine awareness
    is a router-layer concern. Does NOT commit.
    """
    if not settings.FEATURE_AGILE_PHASE_4:
        raise PermissionError("FEATURE_DISABLED")

    if (wiki_page_id is None) == (source_id is None):
        raise ValueError("exactly one knowledge target is required")

    task = await get_task(db, task_id)
    if task is None:
        raise ValueError("task not found")

    if wiki_page_id is not None:
        wiki_page = await db.get(WikiPage, wiki_page_id)
        if wiki_page is None:
            raise ValueError("wiki page not found")

        # Duplicate pre-check. The DB unique constraint is the source of truth;
        # this is the cheap happy-path response that avoids a SAVEPOINT.
        existing = await db.scalar(
            select(TaskKnowledgeLink.id).where(
                TaskKnowledgeLink.task_id == task_id,
                TaskKnowledgeLink.wiki_page_id == wiki_page_id,
            )
        )
        if existing is not None:
            raise ValueError(DUPLICATE_KNOWLEDGE_LINK_ERROR_CODE)
    else:
        source = await db.get(Source, source_id)
        if source is None:
            raise ValueError("source not found")

    link = TaskKnowledgeLink(
        task_id=task_id,
        wiki_page_id=wiki_page_id,
        source_id=source_id,
        link_type=link_type,
        created_by_id=actor.id,
    )
    db.add(link)
    # SAVEPOINT-guarded flush translates the race window where two callers
    # slip past the pre-check into the same domain error rather than
    # poisoning the outer transaction with an IntegrityError.
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        if "uq_task_knowledge_link_pair" in str(exc).lower():
            raise ValueError(DUPLICATE_KNOWLEDGE_LINK_ERROR_CODE) from exc
        raise

    db.add(
        TaskActivity(
            task_id=task_id,
            actor_id=actor.id,
            verb=ACTIVITY_VERB_KNOWLEDGE_LINK_ADDED,
            field_name="wiki_page_id" if wiki_page_id is not None else "source_id",
            new_value=str(wiki_page_id if wiki_page_id is not None else source_id),
            meta={"link_type": link_type},
        )
    )
    await log_audit(db, actor, "create", "task_knowledge_link", str(link.id))
    await db.flush()
    return link


async def remove_knowledge_link(
    db: AsyncSession,
    task_id: uuid.UUID,
    wiki_page_id: uuid.UUID,
    *,
    actor: Employee,
) -> None:
    """Delete the ``(task_id, wiki_page_id)`` knowledge-link row.

    Gated on :data:`settings.FEATURE_AGILE_PHASE_4`; raises
    :class:`PermissionError` carrying the ``FEATURE_DISABLED`` code when
    the flag is off. Raises :class:`ValueError`
    ``"knowledge link not found"`` when the link does not exist. Does
    NOT commit.
    """
    if not settings.FEATURE_AGILE_PHASE_4:
        raise PermissionError("FEATURE_DISABLED")

    link = await db.scalar(
        select(TaskKnowledgeLink).where(
            TaskKnowledgeLink.task_id == task_id,
            TaskKnowledgeLink.wiki_page_id == wiki_page_id,
        )
    )
    if link is None:
        raise ValueError("knowledge link not found")
    link_id = link.id
    link_type = link.link_type
    await db.delete(link)
    db.add(
        TaskActivity(
            task_id=task_id,
            actor_id=actor.id,
            verb=ACTIVITY_VERB_KNOWLEDGE_LINK_REMOVED,
            field_name="wiki_page_id",
            old_value=str(wiki_page_id),
            meta={"link_type": link_type},
        )
    )
    await log_audit(db, actor, "delete", "task_knowledge_link", str(link_id))
    await db.flush()


async def list_knowledge_links(
    db: AsyncSession,
    task_id: uuid.UUID,
) -> list[TaskKnowledgeLink]:
    """Return all knowledge links for a task.

    Read-only and always accessible — the Phase 4 feature flag gates writes
    only, mirroring the Phase 2 dependency read contract so dashboards that
    pre-fetch the link set during a partial rollout do not flood
    observability with 403s. The caller (router) is still responsible for
    the per-task access check.
    """
    result = await db.execute(
        select(TaskKnowledgeLink)
        .where(TaskKnowledgeLink.task_id == task_id)
        .order_by(TaskKnowledgeLink.created_at, TaskKnowledgeLink.id)
    )
    return list(result.scalars().all())


async def move_task_state(
    db: AsyncSession,
    task_id: uuid.UUID,
    new_state_id: uuid.UUID,
    new_position: float,
    actor: Employee,
    *,
    expected_version: int | None = None,
) -> tuple[Task, dict[str, object] | None, list[dict[str, str]]]:
    """Move a task to another state/position, increment version, return advisories.

    Returns ``(task, wip_advisory, permission_advisories)`` where:

    * ``wip_advisory`` is a dict describing a Phase 1 WIP ``warn`` event (and
      the matching ``wip_advisory_warned`` activity row is added), or ``None``
      when no WIP advisory was emitted.
    * ``permission_advisories`` is a (possibly empty) list of Stage A
      governance advisories — one entry per missing ``agile.*`` permission.
      Currently emitted for:

        - ``agile.wip.override`` — when a WIP advisory fired AND the actor
          lacks the override permission. Stage A only logs; Stage B will
          eventually gate the bypass.
        - ``agile.dod.bypass`` — when the target state is in the ``done``
          group AND the task's DoD snapshot still has un-done items.

      Each entry is ``{"code": "PERMISSION_DENIED_ADVISORY", "permission":
      "agile.xxx.xxx"}`` and never blocks the move.

    Raises :class:`WipExceededError` if the target state's
    ``wip_policy='enforce'`` and moving would push it over ``wip_limit`` (the
    task is NOT moved in that case). Optimistic concurrency uses
    ``expected_version`` when provided.
    """
    task = await get_task(db, task_id)
    if task is None:
        raise ValueError("not found")

    if expected_version is not None and expected_version != task.version:
        raise ValueError(
            f"version conflict: expected {task.version}, got {expected_version}"
        )

    target_state = await _ensure_state_in_project(
        db, new_state_id, task.task_project_id
    )

    old_state_id = task.state_id
    old_position = task.position
    state_changing = old_state_id != new_state_id

    advisory = await _check_wip_for_move(
        db,
        target_state=target_state,
        moving_task=task,
        state_changing=state_changing,
    )

    task.state_id = new_state_id
    task.position = new_position
    task.version += 1

    if state_changing:
        db.add(
            TaskActivity(
                task_id=task.id,
                actor_id=actor.id,
                verb="state_changed",
                field_name="state_id",
                old_value=str(old_state_id),
                new_value=str(new_state_id),
                meta={"old_position": old_position, "new_position": new_position},
            )
        )

    if advisory is not None:
        db.add(
            TaskActivity(
                task_id=task.id,
                actor_id=actor.id,
                verb="wip_advisory_warned",
                field_name="state_id",
                old_value=str(old_state_id) if state_changing else None,
                new_value=str(new_state_id),
                meta=advisory,
            )
        )
        # Phase 1: persist a ``task_wip_exceeded`` notification for the task's
        # active assignees (skipping the actor — they already saw the toast).
        # Notification creation flushes; the surrounding flush still runs below.
        await notify_wip_exceeded(db, task, target_state, actor=actor)

    await log_audit(db, actor, "update", "task", str(task.id))

    # Phase 5 governance — Stage A advisory only. The helper short-circuits
    # when the feature flag is off so legacy callers see identical behaviour.
    permission_advisories: list[dict[str, str]] = []
    if advisory is not None:
        wip_perm = await maybe_record_permission_advisory(
            db,
            actor=actor,
            permission=PERMISSION_AGILE_WIP_OVERRIDE,
            resource_type="task",
            resource_id=task.id,
        )
        if wip_perm is not None:
            permission_advisories.append(wip_perm)

    if (
        state_changing
        and target_state.group == "done"
        and dod_checklist_has_incomplete_items(task.dod_checklist)
    ):
        dod_perm = await maybe_record_permission_advisory(
            db,
            actor=actor,
            permission=PERMISSION_AGILE_DOD_BYPASS,
            resource_type="task",
            resource_id=task.id,
        )
        if dod_perm is not None:
            permission_advisories.append(dod_perm)

    await db.flush()
    return task, advisory, permission_advisories


async def _check_wip_for_move(
    db: AsyncSession,
    *,
    target_state: TaskState,
    moving_task: Task,
    state_changing: bool,
) -> dict[str, object] | None:
    """Return advisory dict when warn policy fires, raise on enforce, else None.

    Skips silently when the Phase 1 feature flag is off, when the policy is
    ``off``, or when ``wip_limit`` is unset — preserving legacy behaviour for
    states that haven't opted in.
    """
    if not settings.FEATURE_AGILE_PHASE_1:
        return None

    policy = (target_state.wip_policy or "off").lower()
    limit = target_state.wip_limit
    if policy == "off" or limit is None:
        return None

    count_stmt = select(func.count(Task.id)).where(
        Task.state_id == target_state.id,
        Task.deleted_at.is_(None),
    )
    # A same-state reorder ("Backlog -> Backlog") must not count the moving
    # task twice; only exclude when it's already in the target state.
    if not state_changing:
        count_stmt = count_stmt.where(Task.id != moving_task.id)
    current_count = await db.scalar(count_stmt) or 0

    # Post-move count: a state change adds one to the target lane; a same-state
    # reorder leaves the count unchanged (we already excluded the moving task).
    projected_count = current_count + 1 if state_changing else current_count
    if projected_count < limit:
        return None

    if policy == "enforce":
        raise WipExceededError(
            state_id=target_state.id,
            limit=limit,
            current_count=current_count,
        )

    # warn
    return {
        "code": WIP_EXCEEDED_ERROR_CODE,
        "policy": "warn",
        "state_id": str(target_state.id),
        "wip_limit": limit,
        "current_count": current_count,
        "projected_count": projected_count,
    }


async def forward_task(
    db: AsyncSession,
    task_id: uuid.UUID,
    data: TaskForwardRequest,
    actor: Employee,
) -> tuple[Task, list[uuid.UUID], list[uuid.UUID], uuid.UUID, uuid.UUID]:
    """Forward (chuyển tiếp) a task: replace assignee(s), optionally cross-unit.

    Returns ``(task, removed_assignee_ids, added_assignee_ids,
    source_department_id, target_department_id)`` so the router can fan-out
    notifications outside the DB transaction. Does NOT commit — caller owns the
    transaction boundary.
    """
    task = await get_task(db, task_id)
    if task is None:
        raise ValueError("not found")

    if task.completed_at is not None:
        raise ValueError("cannot forward a completed task")
    if task.deleted_at is not None:
        raise ValueError("cannot forward a deleted task")

    if data.version != task.version:
        raise ValueError(
            f"version conflict: expected {task.version}, got {data.version}"
        )

    project = task.task_project or await db.get(TaskProject, task.task_project_id)
    if project is None:
        raise ValueError("task project not found")
    if project.owner_employee_id is not None:
        raise ValueError("cannot forward a personal task")

    # Snapshot current assignees BEFORE any mutation. Used for source-unit
    # inference (workspace tasks) and for the activity log.
    old_assignee_ids = [assignee.employee_id for assignee in task.assignees]

    source_department_id = await _infer_source_department_id(
        db, project, old_assignee_ids
    )
    if source_department_id is None:
        raise ValueError(
            "cannot infer source department for this task; assign someone first"
        )

    target_department_id = data.target_department_id or source_department_id

    target_department = await db.get(Department, target_department_id)
    if target_department is None:
        raise ValueError("target department not found")
    if target_department.is_archived:
        raise ValueError("target department is archived")

    new_assignee = await db.get(Employee, data.new_assignee_id)
    if new_assignee is None:
        raise ValueError("new assignee not found")
    if not new_assignee.is_active:
        raise ValueError("inactive employee cannot be assigned")

    membership_exists = await db.scalar(
        select(func.count())
        .select_from(EmployeeDepartmentMembership)
        .where(
            EmployeeDepartmentMembership.employee_id == new_assignee.id,
            EmployeeDepartmentMembership.department_id == target_department_id,
            EmployeeDepartmentMembership.is_active.is_(True),
        )
    )
    # Union with legacy employees.department_id pointer — BIDV pilot data
    # predates the multi-unit membership backfill, so some employees only have
    # the legacy FK. Mirror task_access_service.list_eligible_assignees.
    legacy_member = (
        new_assignee.department_id == target_department_id
    )
    if not membership_exists and not legacy_member:
        raise ValueError(
            "new assignee is not an active member of the target department"
        )

    # No-op guard: forwarding to the only current assignee with keep=False
    # collapses to "nothing changes". Forwarding to an existing assignee with
    # keep=True is also a no-op.
    if data.keep_previous_assignees and data.new_assignee_id in old_assignee_ids:
        raise ValueError("new assignee is already on this task")
    if (
        not data.keep_previous_assignees
        and old_assignee_ids == [data.new_assignee_id]
    ):
        raise ValueError("new assignee is already the sole assignee")

    removed_ids: list[uuid.UUID] = []
    if not data.keep_previous_assignees:
        for assignee in list(task.assignees):
            await db.delete(assignee)
            removed_ids.append(assignee.employee_id)

    added_ids: list[uuid.UUID] = []
    if data.new_assignee_id not in old_assignee_ids:
        db.add(TaskAssignee(task_id=task.id, employee_id=data.new_assignee_id))
        added_ids.append(data.new_assignee_id)

    task.version += 1

    is_cross_unit = source_department_id != target_department_id
    db.add(
        TaskActivity(
            task_id=task.id,
            actor_id=actor.id,
            verb="forwarded",
            field_name="assignee",
            old_value=",".join(str(eid) for eid in old_assignee_ids) or None,
            new_value=str(data.new_assignee_id),
            meta={
                "reason": data.reason.strip(),
                "from_department_id": str(source_department_id),
                "to_department_id": str(target_department_id),
                "is_cross_unit": is_cross_unit,
                "kept_previous": data.keep_previous_assignees,
                "removed_assignee_ids": [str(eid) for eid in removed_ids],
            },
        )
    )

    await log_audit(db, actor, "forward", "task", str(task.id))
    await db.flush()
    return task, removed_ids, added_ids, source_department_id, target_department_id


async def _infer_source_department_id(
    db: AsyncSession,
    project: TaskProject,
    current_assignee_ids: list[uuid.UUID],
) -> uuid.UUID | None:
    """Pick the "source unit" of a task for forwarding purposes.

    - Department-scoped project → the project's department.
    - Workspace-scoped project → the first current assignee's primary
      department (falls back to ``Employee.department_id``).
    - Personal project is rejected upstream; return None defensively.
    """
    if project.department_id is not None:
        return project.department_id

    if project.workspace_id is not None and current_assignee_ids:
        for assignee_id in current_assignee_ids:
            employee = await db.get(Employee, assignee_id)
            if employee is None:
                continue
            primary_dept_id = await db.scalar(
                select(EmployeeDepartmentMembership.department_id).where(
                    EmployeeDepartmentMembership.employee_id == employee.id,
                    EmployeeDepartmentMembership.is_active.is_(True),
                    EmployeeDepartmentMembership.is_primary.is_(True),
                )
            )
            if primary_dept_id is not None:
                return primary_dept_id
            if employee.department_id is not None:
                return employee.department_id

    return None


async def soft_delete_task(
    db: AsyncSession, task_id: uuid.UUID, actor: Employee
) -> None:
    """Soft-delete a task and its direct subtasks without committing."""
    task = await get_task(db, task_id)
    if task is None:
        raise ValueError("not found")

    deleted_at = datetime.now(timezone.utc)
    result = await db.execute(
        select(Task.id).where((Task.id == task_id) | (Task.parent_task_id == task_id))
    )
    deleted_task_ids = list(result.scalars().all())
    await db.execute(
        update(Task).where(Task.id.in_(deleted_task_ids)).values(deleted_at=deleted_at)
    )
    for deleted_task_id in deleted_task_ids:
        db.add(
            TaskActivity(
                task_id=deleted_task_id,
                actor_id=actor.id,
                verb="deleted",
                created_at=deleted_at,
            )
        )
    await log_audit(db, actor, "delete", "task", str(task_id))
    await db.flush()


async def restore_task(db: AsyncSession, task_id: uuid.UUID, actor: Employee) -> Task:
    """Restore a soft-deleted task without committing."""
    task = await get_task(db, task_id, include_deleted=True)
    if task is None:
        raise ValueError("not found")

    task.deleted_at = None
    await log_audit(db, actor, "restore", "task", str(task.id))
    await db.flush()
    return task


async def _next_position_in_state(
    db: AsyncSession,
    state_id: uuid.UUID,
    project_id: uuid.UUID,
) -> float:
    """Return the next position in a project/state lane."""
    max_position = await db.scalar(
        select(func.max(Task.position)).where(
            Task.task_project_id == project_id,
            Task.state_id == state_id,
        )
    )
    return (max_position + POSITION_GAP) if max_position is not None else POSITION_GAP


def _task_select():
    return select(Task).options(
        selectinload(Task.task_project),
        selectinload(Task.assignees),
        selectinload(Task.label_links),
        selectinload(Task.subtasks),
    )


async def _ensure_state_in_project(
    db: AsyncSession,
    state_id: uuid.UUID,
    project_id: uuid.UUID,
) -> TaskState:
    state = await db.get(TaskState, state_id)
    if state is None or state.task_project_id != project_id:
        raise ValueError("state not in project")
    return state


async def _get_task_in_project(
    db: AsyncSession,
    task_id: uuid.UUID,
    project_id: uuid.UUID,
) -> Task | None:
    result = await db.execute(
        select(Task).where(
            Task.id == task_id,
            Task.task_project_id == project_id,
            Task.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def _ensure_parent_allowed(
    db: AsyncSession,
    task: Task,
    parent_task_id: uuid.UUID | None,
) -> None:
    if parent_task_id is None:
        return
    if parent_task_id == task.id:
        raise ValueError("parent task not found")

    parent = await _get_task_in_project(db, parent_task_id, task.task_project_id)
    if parent is None:
        raise ValueError("parent task not found")
    if MAX_SUBTASK_DEPTH <= 1 and parent.parent_task_id is not None:
        raise ValueError("max subtask depth exceeded")


async def _ensure_labels_in_project(
    db: AsyncSession,
    label_ids: list[uuid.UUID],
    project_id: uuid.UUID,
) -> None:
    result = await db.execute(
        select(TaskLabel.id).where(
            TaskLabel.id.in_(label_ids),
            TaskLabel.task_project_id == project_id,
        )
    )
    found_ids = set(result.scalars().all())
    if found_ids != set(label_ids):
        raise ValueError("label not in project")


def _stringify_activity_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
