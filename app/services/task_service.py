"""Task CRUD, subtask, versioning, position, and soft-delete service."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    Employee,
    Task,
    TaskActivity,
    TaskAssignee,
    TaskLabel,
    TaskLabelLink,
    TaskProject,
    TaskState,
)
from app.schemas.tasks import TaskCreate, TaskUpdate
from app.services.audit_service import log_audit
from app.services.task_constants import (
    INITIAL_TASK_VERSION,
    MAX_SUBTASK_DEPTH,
    POSITION_GAP,
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

    await _ensure_state_in_project(db, data.state_id, project_id)

    for employee_id in data.assignee_ids:
        employee = await db.get(Employee, employee_id)
        if employee is None:
            raise ValueError("employee not found")
        if not employee.is_active:
            raise ValueError("inactive employee cannot be assigned")

    if data.parent_task_id is not None:
        parent = await _get_task_in_project(db, data.parent_task_id, project_id)
        if parent is None:
            raise ValueError("parent task not found")
        if MAX_SUBTASK_DEPTH <= 1 and parent.parent_task_id is not None:
            raise ValueError("max subtask depth exceeded")

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
    """Update a non-deleted task using optimistic concurrency without committing."""
    task = await get_task(db, task_id)
    if task is None:
        raise ValueError("not found")

    if data.version != task.version:
        raise ValueError(f"version conflict: expected {task.version}, got {data.version}")

    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    changes.pop("version", None)

    for field, new_value in changes.items():
        if field == "state_id":
            await _ensure_state_in_project(db, new_value, task.task_project_id)
        if field == "parent_task_id":
            await _ensure_parent_allowed(db, task, new_value)

        old_value = getattr(task, field)
        if old_value == new_value:
            continue

        setattr(task, field, new_value)
        db.add(
            TaskActivity(
                task_id=task.id,
                actor_id=actor.id,
                verb=f"{field}_changed",
                field_name=field,
                old_value=_stringify_activity_value(old_value),
                new_value=_stringify_activity_value(new_value),
            )
        )

    task.version += 1
    await log_audit(db, actor, "update", "task", str(task.id))
    await db.flush()
    return task


async def move_task_state(
    db: AsyncSession,
    task_id: uuid.UUID,
    new_state_id: uuid.UUID,
    new_position: float,
    actor: Employee,
) -> Task:
    """Move a task to another state/position and increment its version without committing."""
    task = await get_task(db, task_id)
    if task is None:
        raise ValueError("not found")

    await _ensure_state_in_project(db, new_state_id, task.task_project_id)

    old_state_id = task.state_id
    old_position = task.position
    task.state_id = new_state_id
    task.position = new_position
    task.version += 1

    if old_state_id != new_state_id:
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

    await log_audit(db, actor, "update", "task", str(task.id))
    await db.flush()
    return task


async def soft_delete_task(db: AsyncSession, task_id: uuid.UUID, actor: Employee) -> None:
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
        update(Task)
        .where(Task.id.in_(deleted_task_ids))
        .values(deleted_at=deleted_at)
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
