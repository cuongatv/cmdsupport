"""Task project, state, and label service layer."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database.models import (
    Department,
    Employee,
    Project,
    Role,
    Task,
    TaskLabel,
    TaskProject,
    TaskProjectTemplate,
    TaskState,
    UnitType,
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
    FEATURE_DISABLED_ERROR_CODE,
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

# Personal-project identifier prefix. Mirrors the default-project layout but
# scoped to an individual employee so the planner / habit views always have a
# canonical container to point at.
_PERSONAL_PROJECT_IDENTIFIER_PREFIX = "MY"
_PERSONAL_PROJECT_NAME_TEMPLATE = "Công việc cá nhân của {name}"


def _default_project_identifier(scope_id: uuid.UUID) -> str:
    """Build a stable, schema-valid identifier for a scope's default project."""
    return f"{_DEFAULT_PROJECT_IDENTIFIER_PREFIX}{scope_id.hex[:6].upper()}"


def _personal_project_identifier(employee_id: uuid.UUID) -> str:
    """Build a stable identifier for an employee's personal task project.

    Schema limit is ``String(10)`` (see ``TaskProject.identifier``); the prefix
    plus six hex characters lands at 8, well under the cap.
    """
    return f"{_PERSONAL_PROJECT_IDENTIFIER_PREFIX}{employee_id.hex[:6].upper()}"


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


async def get_or_create_personal_project(
    db: AsyncSession,
    employee: Employee,
) -> TaskProject:
    """Return the employee's personal TaskProject, lazy-creating one on first use.

    Personal projects are owner-scoped containers for an employee's own tasks
    (`owner_employee_id` branch of the TaskProject scope XOR). The planner,
    dashboard, and calendar views all need a canonical project to point at, so
    we materialise it on first access rather than during user-onboarding.

    Re-uses the oldest non-archived personal project for the employee if one
    already exists, mirroring `resolve_default_task_project` so duplicate rows
    can't fan out. The function flushes but does not commit — the calling
    request boundary (router) owns the commit.
    """
    stmt = (
        select(TaskProject)
        .where(
            TaskProject.owner_employee_id == employee.id,
            TaskProject.is_archived.is_(False),
        )
        .order_by(TaskProject.created_at, TaskProject.id)
        .limit(1)
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing

    project = TaskProject(
        name=_PERSONAL_PROJECT_NAME_TEMPLATE.format(name=employee.name),
        description=None,
        identifier=_personal_project_identifier(employee.id),
        workspace_id=None,
        department_id=None,
        owner_employee_id=employee.id,
        created_by_id=employee.id,
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
    await log_audit(db, employee, "create", "task_project", str(project.id))
    await db.flush()
    await db.refresh(project, ["states"])
    project.states.sort(key=lambda state: state.position)
    return project


async def get_task_project(
    db: AsyncSession, project_id: uuid.UUID
) -> TaskProject | None:
    """Return a non-deleted task project by id, or None."""
    return await db.get(TaskProject, project_id)


async def get_project_template(
    db: AsyncSession, project_id: uuid.UUID
) -> TaskProjectTemplate | None:
    """Return the DoR/DoD template for a project, or None if none exists.

    Phase 2: used by ``task_service.create_task`` to snapshot ``dor_template``
    and ``dod_template`` into the new task. Later template edits do NOT
    retroactively touch existing tasks — the snapshot is one-time-only.
    """
    result = await db.execute(
        select(TaskProjectTemplate).where(
            TaskProjectTemplate.task_project_id == project_id
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Phase 4 — Vietnamese DoR/DoD defaults per unit type (Agile templates)
# ---------------------------------------------------------------------------

# Default Definition-of-Ready / Definition-of-Done checklist items in
# Vietnamese, keyed by department ``unit_type``. The squad/team flavour gets
# the full Agile checklist; the generic business-group flavour gets a leaner
# set that suits SOP/operations work. Items are returned as lightweight dicts
# so the wire shape matches ``Task.dor_checklist`` / ``Task.dod_checklist``
# (``[{"label": "...", "done": false}]``) without further mapping.

_DEFAULT_DOR_BY_UNIT_TYPE: dict[str, list[str]] = {
    UnitType.SQUAD_TEAM.value: [
        "Yêu cầu đã được xác nhận",
        "Tiêu chí chấp nhận rõ ràng",
        "Ước lượng đã hoàn thành",
        "Phụ thuộc đã được xác định",
        "Thiết kế kỹ thuật đã được thống nhất",
    ],
    UnitType.BUSINESS_GROUP.value: [
        "Yêu cầu đã được xác nhận",
        "Tiêu chí chấp nhận rõ ràng",
        "Người phụ trách đã được phân công",
    ],
}

_DEFAULT_DOD_BY_UNIT_TYPE: dict[str, list[str]] = {
    UnitType.SQUAD_TEAM.value: [
        "Đã kiểm thử",
        "Đã review code",
        "Đã cập nhật tài liệu",
        "Đã triển khai lên môi trường staging",
        "Đã được Product Owner xác nhận",
    ],
    UnitType.BUSINESS_GROUP.value: [
        "Đã kiểm tra chất lượng",
        "Đã cập nhật tài liệu",
        "Đã được phê duyệt",
    ],
}


def get_default_dor_template(unit_type: str | UnitType | None = None) -> list[str]:
    """Return the default Vietnamese DoR checklist labels for a unit type.

    Accepts either the ``UnitType`` enum or its raw string value. Unknown or
    missing types fall back to the generic ``business_group`` flavour so
    callers always get a non-empty list of opinionated defaults.
    """
    key = unit_type.value if isinstance(unit_type, UnitType) else unit_type
    return list(
        _DEFAULT_DOR_BY_UNIT_TYPE.get(
            key or "",
            _DEFAULT_DOR_BY_UNIT_TYPE[UnitType.BUSINESS_GROUP.value],
        )
    )


def get_default_dod_template(unit_type: str | UnitType | None = None) -> list[str]:
    """Return the default Vietnamese DoD checklist labels for a unit type.

    Mirrors :func:`get_default_dor_template`: ``squad_team`` callers get the
    full Agile completion bar, everyone else falls back to the
    ``business_group`` flavour.
    """
    key = unit_type.value if isinstance(unit_type, UnitType) else unit_type
    return list(
        _DEFAULT_DOD_BY_UNIT_TYPE.get(
            key or "",
            _DEFAULT_DOD_BY_UNIT_TYPE[UnitType.BUSINESS_GROUP.value],
        )
    )


async def get_or_create_template(
    db: AsyncSession,
    task_project_id: uuid.UUID,
) -> TaskProjectTemplate:
    """Return the project's DoR/DoD template, creating an empty row on first read.

    Phase 4: the template surface is always readable, even when
    ``FEATURE_AGILE_PHASE_4`` is off, so dashboards that pre-fetch the
    template during a partial rollout do not flood observability with 403s.
    Writes still go through :func:`update_template` which enforces the gate.

    The row is created with empty ``dor_template`` / ``dod_template`` arrays
    so callers never see ``None`` for the JSONB columns. Race condition
    between two concurrent first-reads is translated via a SAVEPOINT-guarded
    flush + unique-constraint retry — same pattern Phase 2 sprint creation
    uses for the active-sprint uniqueness check. Does NOT commit.
    """
    project = await db.get(TaskProject, task_project_id)
    if project is None:
        raise ValueError("task project not found")

    existing = await db.scalar(
        select(TaskProjectTemplate).where(
            TaskProjectTemplate.task_project_id == task_project_id
        )
    )
    if existing is not None:
        return existing

    template = TaskProjectTemplate(
        task_project_id=task_project_id,
        dor_template=[],
        dod_template=[],
    )
    db.add(template)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        # Another transaction won the race; re-read the persisted row so the
        # caller always observes a consistent template instance.
        await db.rollback()
        existing = await db.scalar(
            select(TaskProjectTemplate).where(
                TaskProjectTemplate.task_project_id == task_project_id
            )
        )
        if existing is None:  # pragma: no cover - extremely unlikely
            raise
        return existing
    return template


async def update_template(
    db: AsyncSession,
    task_project_id: uuid.UUID,
    *,
    dor_template: list[Any] | None = None,
    dod_template: list[Any] | None = None,
    actor: Employee,
) -> TaskProjectTemplate:
    """Persist DoR/DoD template arrays for a project (Phase 4 Agile).

    Gated on :data:`settings.FEATURE_AGILE_PHASE_4`; raises
    :class:`PermissionError` carrying the ``FEATURE_DISABLED`` code when the
    flag is off so the router can translate it to 403. Updating the template
    does NOT retroactively touch existing tasks — DoR/DoD snapshots taken
    during ``create_task`` (T6) remain frozen on the task rows. Does NOT
    commit; the caller (router) owns the transaction boundary.
    """
    if not settings.FEATURE_AGILE_PHASE_4:
        raise PermissionError(FEATURE_DISABLED_ERROR_CODE)

    template = await get_or_create_template(db, task_project_id)

    if dor_template is not None:
        template.dor_template = list(dor_template)
    if dod_template is not None:
        template.dod_template = list(dod_template)

    await log_audit(
        db, actor, "update", "task_project_template", str(template.id)
    )
    await db.flush()
    return template


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
    """Create a task state at the next position without committing.

    Phase 1 agile fields (``wip_limit``, ``wip_policy``, ``aging_warn_days``)
    are persisted when supplied; the model defaults (``wip_policy='off'``)
    keep legacy callers fully backward compatible.
    """
    project = await _get_existing_project(db, project_id)
    _ensure_project_mutable(project, actor)

    max_position = await db.scalar(
        select(func.max(TaskState.position)).where(
            TaskState.task_project_id == project_id
        )
    )
    state_kwargs: dict[str, object] = {
        "task_project_id": project_id,
        "name": data.name,
        "group": data.group,
        "color": data.color,
        "position": (max_position + POSITION_GAP)
        if max_position is not None
        else data.position,
        "is_default": False,
    }
    if data.wip_limit is not None:
        state_kwargs["wip_limit"] = data.wip_limit
    if data.wip_policy is not None:
        state_kwargs["wip_policy"] = data.wip_policy
    if data.aging_warn_days is not None:
        state_kwargs["aging_warn_days"] = data.aging_warn_days

    state = TaskState(**state_kwargs)
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
