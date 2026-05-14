"""Task project, state, and label service layer."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models import (
    Department,
    Employee,
    Project,
    Role,
    Task,
    TaskLabel,
    TaskProject,
    TaskState,
)
from app.schemas.tasks import (
    TaskLabelCreate,
    TaskProjectCreate,
    TaskProjectUpdate,
    TaskStateCreate,
    TaskStateUpdate,
)
from app.services.audit_service import log_audit
from app.services.permission_engine import get_user_department_ids
from app.services.permissions import EMPLOYEE_DEFAULT_PERMISSIONS
from app.services.task_constants import (
    DEFAULT_STATE_GROUPS,
    DEFAULT_STATE_NAMES,
    POSITION_GAP,
)


class TaskProjectAccessDenied(PermissionError):
    """Raised when an actor is not authorized to create a default task project.

    Used by `resolve_default_task_project()` to refuse lazy-creation of a hidden
    container in a department where the actor has no active membership and no
    broad-scope create permission. Inherits ``PermissionError`` so the router's
    ``_call_service`` helper translates it to HTTP 403 without extra wiring.
    """


async def create_task_project(
    db: AsyncSession,
    data: TaskProjectCreate,
    creator: Employee,
) -> TaskProject:
    """Create a task project and its default workflow states without committing."""
    if (data.workspace_id is None) == (data.department_id is None):
        raise ValueError("exactly one of workspace_id or department_id must be set")

    if data.workspace_id is not None:
        parent = await db.get(Project, data.workspace_id)
    else:
        parent = await db.get(Department, data.department_id)
    if parent is None:
        raise ValueError("parent not found")

    project = TaskProject(
        name=data.name,
        description=data.description,
        identifier=data.identifier,
        workspace_id=data.workspace_id,
        department_id=data.department_id,
        created_by_id=creator.id,
        allow_any_employee=data.allow_any_employee,
    )
    db.add(project)
    await db.flush()

    for index, (name, group) in enumerate(
        zip(DEFAULT_STATE_NAMES, DEFAULT_STATE_GROUPS)
    ):
        db.add(
            TaskState(
                task_project_id=project.id,
                name=name,
                group=group,
                position=index * POSITION_GAP,
                is_default=index == 0,
            )
        )
    await log_audit(db, creator, "create", "task_project", str(project.id))
    await db.flush()
    await db.refresh(project, ["states"])
    project.states.sort(key=lambda state: state.position)
    return project


async def update_task_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    data: TaskProjectUpdate,
    actor: Employee,
) -> TaskProject:
    """Update mutable task-project fields without committing."""
    project = await _get_existing_project(db, project_id)
    _ensure_project_mutable(project, actor)

    for field, value in _provided_values(data).items():
        setattr(project, field, value)

    await log_audit(db, actor, "update", "task_project", str(project.id))
    await db.flush()
    return project


async def archive_task_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    actor: Employee,
) -> TaskProject:
    """Archive a task project without committing."""
    project = await _get_existing_project(db, project_id)
    project.is_archived = True
    await log_audit(db, actor, "archive", "task_project", str(project.id))
    await db.flush()
    return project


async def restore_task_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    actor: Employee,
) -> TaskProject:
    """Restore an archived task project without committing. Admin only."""
    if not _is_admin(actor):
        raise PermissionError("admin only")

    project = await _get_existing_project(db, project_id)
    project.is_archived = False
    await log_audit(db, actor, "restore", "task_project", str(project.id))
    await db.flush()
    return project


async def list_task_projects(
    db: AsyncSession,
    workspace_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    include_archived: bool = False,
) -> list[TaskProject]:
    """List task projects, optionally scoped to workspace or department."""
    stmt = select(TaskProject)
    if workspace_id is not None:
        stmt = stmt.where(TaskProject.workspace_id == workspace_id)
    if department_id is not None:
        stmt = stmt.where(TaskProject.department_id == department_id)
    if not include_archived:
        stmt = stmt.where(TaskProject.is_archived.is_(False))
    stmt = stmt.order_by(TaskProject.created_at, TaskProject.id)

    result = await db.execute(stmt)
    return list(result.scalars().all())


# Internal default-project identifier prefix. The user never sees this — the
# project acts as a hidden container so tasks can be created directly by scope
# (workspace / department) without forcing the user to pick a project.
_DEFAULT_PROJECT_IDENTIFIER_PREFIX = "GEN"
_DEFAULT_PROJECT_NAME = "Công việc chung"


def _default_project_identifier(scope_id: uuid.UUID) -> str:
    """Build a stable, schema-valid identifier for a scope's default project."""
    return f"{_DEFAULT_PROJECT_IDENTIFIER_PREFIX}{scope_id.hex[:6].upper()}"


async def resolve_default_task_project(
    db: AsyncSession,
    *,
    workspace_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    actor: Employee,
) -> TaskProject:
    """Return the active default TaskProject for the given scope, creating one if needed.

    Exactly one of workspace_id or department_id must be set. The default project is
    a hidden container so users can create tasks directly by scope without picking a
    project. Existing non-archived projects in the scope are reused (oldest first) to
    avoid fragmenting tasks across multiple silent containers.
    """
    if (workspace_id is None) == (department_id is None):
        raise ValueError("exactly one of workspace_id or department_id must be set")

    if workspace_id is not None:
        parent = await db.get(Project, workspace_id)
    else:
        parent = await db.get(Department, department_id)
    if parent is None:
        raise ValueError("parent not found")

    stmt = select(TaskProject).where(TaskProject.is_archived.is_(False))
    if workspace_id is not None:
        stmt = stmt.where(TaskProject.workspace_id == workspace_id)
    else:
        stmt = stmt.where(TaskProject.department_id == department_id)
    stmt = stmt.order_by(TaskProject.created_at, TaskProject.id).limit(1)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    # Authorize BEFORE creating a hidden default project so an unauthorized
    # caller cannot lazy-spawn a project they will be denied access to. Only
    # department-scoped lazy-creates need the membership gate — workspace
    # creation flows through explicit workspace membership elsewhere.
    if department_id is not None:
        await _authorize_default_dept_project_create(db, actor, department_id)

    scope_id = workspace_id if workspace_id is not None else department_id
    assert scope_id is not None  # narrowed by XOR check above
    project = TaskProject(
        name=_DEFAULT_PROJECT_NAME,
        description=None,
        identifier=_default_project_identifier(scope_id),
        workspace_id=workspace_id,
        department_id=department_id,
        created_by_id=actor.id,
        allow_any_employee=False,
    )
    db.add(project)
    await db.flush()

    for index, (name, group) in enumerate(
        zip(DEFAULT_STATE_NAMES, DEFAULT_STATE_GROUPS)
    ):
        db.add(
            TaskState(
                task_project_id=project.id,
                name=name,
                group=group,
                position=index * POSITION_GAP,
                is_default=index == 0,
            )
        )
    await log_audit(db, actor, "create", "task_project", str(project.id))
    await db.flush()
    await db.refresh(project, ["states"])
    project.states.sort(key=lambda state: state.position)
    return project


async def get_task_project(
    db: AsyncSession, project_id: uuid.UUID
) -> TaskProject | None:
    """Return a non-deleted task project by id, or None."""
    return await db.get(TaskProject, project_id)


async def create_label(
    db: AsyncSession,
    project_id: uuid.UUID,
    data: TaskLabelCreate,
    actor: Employee,
) -> TaskLabel:
    """Create a task label scoped to a project without committing."""
    project = await _get_existing_project(db, project_id)
    _ensure_project_mutable(project, actor)

    existing = await db.execute(
        select(TaskLabel.id).where(
            TaskLabel.task_project_id == project_id,
            TaskLabel.name == data.name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("label name already exists")

    label = TaskLabel(
        task_project_id=project_id,
        name=data.name,
        color=data.color,
        description=data.description,
    )
    db.add(label)
    await log_audit(db, actor, "create", "task_label", str(label.id))
    await db.flush()
    return label


async def update_label(
    db: AsyncSession,
    label_id: uuid.UUID,
    data: dict[str, object],
    actor: Employee,
) -> TaskLabel:
    """Update a task label without committing."""
    label = await _get_label_with_project(db, label_id)
    _ensure_project_mutable(label.task_project, actor)

    for field in ("name", "color", "description"):
        if field in data and data[field] is not None:
            setattr(label, field, data[field])

    await log_audit(db, actor, "update", "task_label", str(label.id))
    await db.flush()
    return label


async def delete_label(db: AsyncSession, label_id: uuid.UUID, actor: Employee) -> None:
    """Delete a task label without committing."""
    label = await _get_label_with_project(db, label_id)
    _ensure_project_mutable(label.task_project, actor)

    await db.delete(label)
    await log_audit(db, actor, "delete", "task_label", str(label_id))
    await db.flush()


async def create_state(
    db: AsyncSession,
    project_id: uuid.UUID,
    data: TaskStateCreate,
    actor: Employee,
) -> TaskState:
    """Create a task state at the next position without committing."""
    project = await _get_existing_project(db, project_id)
    _ensure_project_mutable(project, actor)

    max_position = await db.scalar(
        select(func.max(TaskState.position)).where(
            TaskState.task_project_id == project_id
        )
    )
    state = TaskState(
        task_project_id=project_id,
        name=data.name,
        group=data.group,
        color=data.color,
        position=(max_position + POSITION_GAP)
        if max_position is not None
        else data.position,
        is_default=False,
    )
    db.add(state)
    await log_audit(db, actor, "create", "task_state", str(state.id))
    await db.flush()
    return state


async def update_state(
    db: AsyncSession,
    state_id: uuid.UUID,
    data: TaskStateUpdate,
    actor: Employee,
) -> TaskState:
    """Update a task state without committing."""
    state = await _get_state_with_project(db, state_id)
    _ensure_project_mutable(state.task_project, actor)

    for field, value in _provided_values(data).items():
        setattr(state, field, value)

    await log_audit(db, actor, "update", "task_state", str(state.id))
    await db.flush()
    return state


async def delete_state(
    db: AsyncSession,
    state_id: uuid.UUID,
    reassign_state_id: uuid.UUID | None,
    actor: Employee,
) -> None:
    """Delete a state, reassigning referencing tasks when required."""
    state = await _get_state_with_project(db, state_id)
    _ensure_project_mutable(state.task_project, actor)

    task_count = await db.scalar(
        select(func.count(Task.id)).where(
            Task.state_id == state_id,
            Task.deleted_at.is_(None),
        )
    )
    if task_count and reassign_state_id is None:
        raise ValueError("state has tasks — provide reassign_state_id")

    if reassign_state_id is not None:
        reassign_state = await db.get(TaskState, reassign_state_id)
        if (
            reassign_state is None
            or reassign_state.task_project_id != state.task_project_id
        ):
            raise ValueError("reassign_state_id not found")
        await db.execute(
            update(Task)
            .where(Task.state_id == state_id)
            .values(state_id=reassign_state_id)
        )

    await db.delete(state)
    await log_audit(db, actor, "delete", "task_state", str(state_id))
    await db.flush()


async def _get_existing_project(db: AsyncSession, project_id: uuid.UUID) -> TaskProject:
    project = await db.get(TaskProject, project_id)
    if project is None:
        raise ValueError("not found")
    return project


async def _get_label_with_project(db: AsyncSession, label_id: uuid.UUID) -> TaskLabel:
    result = await db.execute(
        select(TaskLabel)
        .options(selectinload(TaskLabel.task_project))
        .where(TaskLabel.id == label_id)
    )
    label = result.scalar_one_or_none()
    if label is None:
        raise ValueError("not found")
    return label


async def _get_state_with_project(db: AsyncSession, state_id: uuid.UUID) -> TaskState:
    result = await db.execute(
        select(TaskState)
        .options(selectinload(TaskState.task_project))
        .where(TaskState.id == state_id)
    )
    state = result.scalar_one_or_none()
    if state is None:
        raise ValueError("not found")
    return state


def _ensure_project_mutable(project: TaskProject, actor: Employee) -> None:
    if project.is_archived and not _is_admin(actor):
        raise PermissionError("archived project is read-only")


def _is_admin(actor: Employee) -> bool:
    return actor.role == "admin"


async def _authorize_default_dept_project_create(
    db: AsyncSession,
    actor: Employee,
    department_id: uuid.UUID,
) -> None:
    """Raise TaskProjectAccessDenied if actor cannot lazy-create in this dept.

    Admins and holders of broad-scope create/manage permissions (`task:create:all`
    or `task_project:manage:all`) bypass the membership gate. Everyone else
    must have an active EmployeeDepartmentMembership (or a legacy
    employees.department_id pointer, via get_user_department_ids' fallback) in
    the target department.
    """
    if _is_admin(actor):
        return

    permissions = await _resolve_actor_permissions(db, actor)
    if "task:create:all" in permissions or "task_project:manage:all" in permissions:
        return

    user_dept_ids = await get_user_department_ids(db, actor)
    if department_id not in user_dept_ids:
        raise TaskProjectAccessDenied(
            f"actor is not an active member of department {department_id}"
        )


async def _resolve_actor_permissions(db: AsyncSession, actor: Employee) -> set[str]:
    """Resolve the actor's effective permission set without trusting eager loads."""
    if actor.custom_role_id is None:
        return set(EMPLOYEE_DEFAULT_PERMISSIONS)

    role = await db.get(Role, actor.custom_role_id)
    if role is None:
        return set(EMPLOYEE_DEFAULT_PERMISSIONS)
    return set(role.permissions or [])


def _provided_values(data: TaskProjectUpdate | TaskStateUpdate) -> dict[str, object]:
    return data.model_dump(exclude_unset=True, exclude_none=True)
