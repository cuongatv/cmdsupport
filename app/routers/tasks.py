"""Native task management router."""
from __future__ import annotations

import uuid
from datetime import datetime
from math import ceil
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import (
    Employee,
    Task,
    TaskActivity,
    TaskAssignee,
    TaskAttachment,
    TaskComment,
    TaskLabel,
    TaskProject,
    TaskState,
)
from app.schemas.tasks import (
    DashboardOut,
    PaginatedResponse,
    TaskActivityOut,
    TaskAssigneeOut,
    TaskAttachmentOut,
    TaskCommentCreate,
    TaskCommentOut,
    TaskCommentUpdate,
    TaskCreate,
    TaskLabelCreate,
    TaskLabelOut,
    TaskMoveRequest,
    TaskOut,
    TaskProjectCreate,
    TaskProjectOut,
    TaskProjectUpdate,
    TaskStateCreate,
    TaskStateOut,
    TaskStateUpdate,
    TaskUpdate,
)
from app.services.audit_service import log_audit
from app.services.auth_service import get_current_user, require_permission
from app.services.storage_service import storage_service
from app.services.task_access_service import (
    can_access_task,
    can_access_task_project,
    list_eligible_assignees,
    validate_assignee,
)
from app.services.task_attachment_service import (
    create_attachment_metadata,
)
from app.services.task_attachment_service import (
    delete_attachment as delete_task_attachment,
)
from app.services.task_attachment_service import (
    get_attachment as get_task_attachment,
)
from app.services.task_attachment_service import (
    list_attachments as list_task_attachments,
)
from app.services.task_comment_service import (
    create_comment as create_task_comment,
)
from app.services.task_comment_service import (
    delete_comment as delete_task_comment,
)
from app.services.task_comment_service import (
    list_activities as list_task_activities,
)
from app.services.task_comment_service import (
    update_comment as update_task_comment,
)
from app.services.task_constants import PRIORITY_LEVELS
from app.services.task_dashboard_service import get_dashboard
from app.services.task_filter_service import TaskFilters, filter_tasks
from app.services.task_notification_service import (
    notify_commented,
    notify_mentioned,
    notify_state_changed,
)
from app.services.task_project_service import (
    archive_task_project,
    list_task_projects,
    update_task_project,
)
from app.services.task_project_service import (
    create_label as create_task_label,
)
from app.services.task_project_service import (
    create_state as create_task_state,
)
from app.services.task_project_service import (
    create_task_project as create_project,
)
from app.services.task_project_service import (
    delete_label as delete_task_label,
)
from app.services.task_project_service import (
    delete_state as delete_task_state,
)
from app.services.task_project_service import (
    get_task_project as get_project,
)
from app.services.task_project_service import (
    update_label as update_task_label,
)
from app.services.task_project_service import (
    update_state as update_task_state,
)
from app.services.task_service import (
    create_task as create_task_record,
)
from app.services.task_service import (
    get_task as get_task_record,
)
from app.services.task_service import (
    soft_delete_task,
)
from app.services.task_service import (
    update_task as update_task_record,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskLabelUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    description: str | None = None


class AddAssigneesRequest(BaseModel):
    employee_ids: list[uuid.UUID]


class EligibleAssigneeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: EmailStr
    department_id: uuid.UUID | None


@router.get("/status")
async def get_task_status(
    current_user: Employee = Depends(get_current_user),
) -> dict[str, bool]:
    """Check native task module availability."""
    return {"native": True}


@router.post(
    "/projects",
    response_model=TaskProjectOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_project_endpoint(
    body: TaskProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> TaskProject:
    project = await _call_service(create_project(db, body, user))
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/projects", response_model=list[TaskProjectOut])
async def list_task_projects_endpoint(
    workspace_id: uuid.UUID | None = None,
    department_id: uuid.UUID | None = None,
    include_archived: bool = False,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> list[TaskProject]:
    projects = await list_task_projects(db, workspace_id, department_id, include_archived)
    return [
        project
        for project in projects
        if await can_access_task_project(db, user, project)
    ]


@router.get("/projects/{project_id}", response_model=TaskProjectOut)
async def get_task_project_endpoint(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> TaskProject:
    project = await _get_accessible_project(db, project_id, user)
    return project


@router.patch("/projects/{project_id}", response_model=TaskProjectOut)
async def update_task_project_endpoint(
    project_id: uuid.UUID,
    body: TaskProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> TaskProject:
    await _ensure_project_access(db, project_id, user)
    project = await _call_service(update_task_project(db, project_id, body, user))
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/projects/{project_id}/archive", response_model=TaskProjectOut)
async def archive_task_project_endpoint(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> TaskProject:
    await _ensure_project_access(db, project_id, user)
    project = await _call_service(archive_task_project(db, project_id, user))
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/projects/{project_id}/states", response_model=list[TaskStateOut])
async def list_states_endpoint(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> list[TaskState]:
    await _ensure_project_access(db, project_id, user)
    result = await db.execute(
        select(TaskState)
        .where(TaskState.task_project_id == project_id)
        .order_by(TaskState.position, TaskState.created_at)
    )
    return list(result.scalars().all())


@router.post(
    "/projects/{project_id}/states",
    response_model=TaskStateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_state_endpoint(
    project_id: uuid.UUID,
    body: TaskStateCreate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> TaskState:
    await _ensure_project_access(db, project_id, user)
    state_row = await _call_service(create_task_state(db, project_id, body, user))
    await db.commit()
    await db.refresh(state_row)
    return state_row


@router.patch("/projects/{project_id}/states/{state_id}", response_model=TaskStateOut)
async def update_state_endpoint(
    project_id: uuid.UUID,
    state_id: uuid.UUID,
    body: TaskStateUpdate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> TaskState:
    await _ensure_project_access(db, project_id, user)
    state_row = await _get_project_state(db, project_id, state_id)
    state_row = await _call_service(update_task_state(db, state_row.id, body, user))
    await db.commit()
    await db.refresh(state_row)
    return state_row


@router.delete("/projects/{project_id}/states/{state_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_state_endpoint(
    project_id: uuid.UUID,
    state_id: uuid.UUID,
    reassign_state_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> None:
    await _ensure_project_access(db, project_id, user)
    await _get_project_state(db, project_id, state_id)
    await _call_service(delete_task_state(db, state_id, reassign_state_id, user))
    await db.commit()


@router.get("/projects/{project_id}/labels", response_model=list[TaskLabelOut])
async def list_labels_endpoint(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> list[TaskLabel]:
    await _ensure_project_access(db, project_id, user)
    result = await db.execute(
        select(TaskLabel)
        .where(TaskLabel.task_project_id == project_id)
        .order_by(TaskLabel.name, TaskLabel.id)
    )
    return list(result.scalars().all())


@router.post(
    "/projects/{project_id}/labels",
    response_model=TaskLabelOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_label_endpoint(
    project_id: uuid.UUID,
    body: TaskLabelCreate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> TaskLabel:
    await _ensure_project_access(db, project_id, user)
    label = await _call_service(create_task_label(db, project_id, body, user))
    await db.commit()
    await db.refresh(label)
    return label


@router.patch("/projects/{project_id}/labels/{label_id}", response_model=TaskLabelOut)
async def update_label_endpoint(
    project_id: uuid.UUID,
    label_id: uuid.UUID,
    body: TaskLabelUpdate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> TaskLabel:
    await _ensure_project_access(db, project_id, user)
    await _get_project_label(db, project_id, label_id)
    label = await _call_service(
        update_task_label(
            db,
            label_id,
            body.model_dump(exclude_unset=True, exclude_none=True),
            user,
        )
    )
    await db.commit()
    await db.refresh(label)
    return label


@router.delete("/projects/{project_id}/labels/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_label_endpoint(
    project_id: uuid.UUID,
    label_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task_project:manage"),
) -> None:
    await _ensure_project_access(db, project_id, user)
    await _get_project_label(db, project_id, label_id)
    await _call_service(delete_task_label(db, label_id, user))
    await db.commit()


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task_endpoint(
    body: TaskCreate,
    task_project_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:create"),
) -> Task:
    await _ensure_project_access(db, task_project_id, user)
    task = await _call_service(create_task_record(db, task_project_id, body, user))
    await _enqueue_assignment_notifications(task.id, body.assignee_ids)
    await db.commit()
    await db.refresh(task)
    return task


@router.get("", response_model=PaginatedResponse[TaskOut])
async def list_tasks_endpoint(
    task_project_id: uuid.UUID = Query(...),
    search: str | None = None,
    state_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
    reporter_id: uuid.UUID | None = None,
    priority: str | None = None,
    label_id: uuid.UUID | None = None,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    overdue: bool = False,
    include_deleted: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: Literal["created_at", "updated_at", "due_date", "priority", "title", "position"] = "created_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> PaginatedResponse[TaskOut]:
    task_project = await _get_accessible_project(db, task_project_id, user)
    if include_deleted and user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin access required")
    if priority is not None and priority not in PRIORITY_LEVELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid priority")

    filters = TaskFilters(
        search=search,
        state_id=state_id,
        assignee_id=assignee_id,
        reporter_id=reporter_id,
        priority=priority,
        label_id=label_id,
        due_from=due_from,
        due_to=due_to,
        overdue=overdue,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    tasks, total = await filter_tasks(db, user, task_project, filters)
    return PaginatedResponse[TaskOut](
        items=tasks,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
    )


@router.get("/{task_id}", response_model=TaskOut)
async def get_task_endpoint(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> Task:
    task = await _get_accessible_task(db, task_id, user)
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task_endpoint(
    task_id: uuid.UUID,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:edit"),
) -> Task:
    await _get_accessible_task(db, task_id, user)
    task = await _call_service(update_task_record(db, task_id, body, user))
    await db.commit()
    await db.refresh(task)
    return task


@router.post("/{task_id}/move", response_model=TaskOut)
async def move_task_endpoint(
    task_id: uuid.UUID,
    body: TaskMoveRequest,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:edit"),
) -> Task:
    task = await _get_accessible_task(db, task_id, user)
    project = await db.get(TaskProject, task.task_project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    if project.is_archived:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="project archived")

    old_state = await _get_project_state(db, task.task_project_id, task.state_id)
    new_state = await _get_project_state(db, task.task_project_id, body.state_id)
    state_changed = task.state_id != body.state_id
    old_position = task.position

    if state_changed and body.version != task.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="version conflict")

    task.position = body.position
    if state_changed:
        task.state_id = body.state_id
        task.version += 1
        db.add(
            TaskActivity(
                task_id=task.id,
                actor_id=user.id,
                verb="state_changed",
                field_name="state_id",
                old_value=str(old_state.id),
                new_value=str(new_state.id),
                meta={
                    "old_state": old_state.name,
                    "new_state": new_state.name,
                    "old_state_group": old_state.group,
                    "new_state_group": new_state.group,
                    "old_position": old_position,
                    "new_position": body.position,
                },
            )
        )
        await notify_state_changed(db, task, old_state.name, user)

    await log_audit(db, user, "move", "task", str(task.id))
    await db.flush()
    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task_endpoint(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:delete"),
) -> None:
    await _get_accessible_task(db, task_id, user)
    await _call_service(soft_delete_task(db, task_id, user))
    await db.commit()


@router.get("/projects/{project_id}/eligible-assignees", response_model=list[EligibleAssigneeOut])
async def eligible_assignees_endpoint(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> list[Employee]:
    project = await _get_accessible_project(db, project_id, user)
    return await list_eligible_assignees(db, project)


@router.get("/projects/{project_id}/dashboard", response_model=DashboardOut)
async def project_dashboard_endpoint(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> DashboardOut:
    project = await _get_accessible_project(db, project_id, user)
    return await get_dashboard(db, user, project)


@router.post("/{task_id}/assignees", response_model=list[TaskAssigneeOut], status_code=status.HTTP_201_CREATED)
async def add_assignees_endpoint(
    task_id: uuid.UUID,
    body: AddAssigneesRequest,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:edit"),
) -> list[TaskAssignee]:
    task = await _get_accessible_task(db, task_id, user)
    project = await _get_accessible_project(db, task.task_project_id, user)
    created: list[TaskAssignee] = []

    for employee_id in _dedupe_ids(body.employee_ids):
        employee = await db.get(Employee, employee_id)
        if employee is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="employee not found")
        await _call_service(validate_assignee(db, project, employee))
        existing = await db.get(TaskAssignee, {"task_id": task_id, "employee_id": employee_id})
        if existing is not None:
            continue
        assignee = TaskAssignee(task_id=task_id, employee_id=employee_id)
        db.add(assignee)
        db.add(
            TaskActivity(
                task_id=task_id,
                actor_id=user.id,
                verb="assigned",
                field_name="assignee_id",
                new_value=str(employee_id),
            )
        )
        created.append(assignee)

    await log_audit(db, user, "assign", "task", str(task_id))
    await db.flush()
    await _enqueue_assignment_notifications(task_id, [row.employee_id for row in created])
    await db.commit()
    return created


@router.delete("/{task_id}/assignees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_assignee_endpoint(
    task_id: uuid.UUID,
    employee_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:edit"),
) -> None:
    await _get_accessible_task(db, task_id, user)
    assignee = await db.get(TaskAssignee, {"task_id": task_id, "employee_id": employee_id})
    if assignee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="assignee not found")
    await db.delete(assignee)
    db.add(
        TaskActivity(
            task_id=task_id,
            actor_id=user.id,
            verb="unassigned",
            field_name="assignee_id",
            old_value=str(employee_id),
        )
    )
    await log_audit(db, user, "unassign", "task", str(task_id))
    await db.flush()
    await db.commit()


@router.post("/{task_id}/comments", response_model=TaskCommentOut, status_code=status.HTTP_201_CREATED)
async def create_comment_endpoint(
    task_id: uuid.UUID,
    body: TaskCommentCreate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> TaskComment:
    task = await _get_accessible_task(db, task_id, user)
    comment = await _call_service(create_task_comment(db, task_id, body.body, user))
    mention_ids = await _comment_mention_ids(db, comment.id)
    assignee_ids = await _task_assignee_ids(db, task_id)
    await notify_commented(db, task, user, assignee_ids)
    await notify_mentioned(db, task, mention_ids, actor=user)
    await log_audit(db, user, "create", "task_comment", str(comment.id))
    await db.commit()
    await db.refresh(comment)
    return comment


@router.get("/{task_id}/comments", response_model=list[TaskCommentOut])
async def list_comments_endpoint(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> list[TaskComment]:
    await _get_accessible_task(db, task_id, user)
    result = await db.execute(
        select(TaskComment)
        .where(TaskComment.task_id == task_id, TaskComment.deleted_at.is_(None))
        .order_by(TaskComment.created_at, TaskComment.id)
    )
    return list(result.scalars().all())


@router.patch("/{task_id}/comments/{comment_id}", response_model=TaskCommentOut)
async def update_comment_endpoint(
    task_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: TaskCommentUpdate,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> TaskComment:
    await _get_accessible_task(db, task_id, user)
    await _get_task_comment(db, task_id, comment_id)
    comment = await _call_service(update_task_comment(db, comment_id, body.body, user))
    await log_audit(db, user, "update", "task_comment", str(comment.id))
    await db.commit()
    await db.refresh(comment)
    return comment


@router.delete("/{task_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment_endpoint(
    task_id: uuid.UUID,
    comment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> None:
    await _get_accessible_task(db, task_id, user)
    await _get_task_comment(db, task_id, comment_id)
    await _call_service(delete_task_comment(db, comment_id, user))
    await log_audit(db, user, "delete", "task_comment", str(comment_id))
    await db.commit()


@router.get("/{task_id}/activities", response_model=list[TaskActivityOut])
async def list_activities_endpoint(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> list[TaskActivity]:
    await _get_accessible_task(db, task_id, user)
    return await list_task_activities(db, task_id)


@router.post(
    "/{task_id}/attachments",
    response_model=TaskAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment_endpoint(
    task_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:edit"),
) -> TaskAttachmentOut:
    task = await _get_accessible_task(db, task_id, user)
    await _ensure_project_writable(db, task.task_project_id)

    file_data = await file.read()
    size_bytes = len(file_data)
    filename = file.filename or "unknown"
    content_type = file.content_type or "application/octet-stream"

    attachment = await _call_service(
        create_attachment_metadata(db, task_id, filename, content_type, size_bytes, user)
    )
    storage_key = attachment.storage_key

    try:
        storage_service.upload_file(
            object_name=storage_key,
            data=file_data,
            content_type=content_type,
        )
    except Exception as exc:  # storage failed → abort transaction
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="storage upload failed",
        ) from exc

    await log_audit(db, user, "create", "task_attachment", str(attachment.id))
    await db.commit()
    await db.refresh(attachment)
    return TaskAttachmentOut.model_validate(attachment)


@router.get("/{task_id}/attachments", response_model=list[TaskAttachmentOut])
async def list_attachments_endpoint(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> list[TaskAttachmentOut]:
    await _get_accessible_task(db, task_id, user)
    rows = await list_task_attachments(db, task_id)
    return [TaskAttachmentOut.model_validate(row) for row in rows]


@router.get(
    "/{task_id}/attachments/{attachment_id}/download",
    response_model=TaskAttachmentOut,
)
async def download_attachment_endpoint(
    task_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:read"),
) -> TaskAttachmentOut:
    await _get_accessible_task(db, task_id, user)
    attachment = await _get_task_attachment(db, task_id, attachment_id)
    presigned_url = storage_service.get_presigned_url(attachment.storage_key)
    payload = TaskAttachmentOut.model_validate(attachment)
    payload.presigned_url = presigned_url
    return payload


@router.delete(
    "/{task_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_attachment_endpoint(
    task_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = require_permission("task:edit"),
) -> None:
    task = await _get_accessible_task(db, task_id, user)
    await _ensure_project_writable(db, task.task_project_id)
    await _get_task_attachment(db, task_id, attachment_id)

    storage_key = await _call_service(delete_task_attachment(db, attachment_id, user))
    try:
        storage_service.delete_object(storage_key)
    except Exception:  # noqa: BLE001 — best-effort orphan cleanup
        # Object may already be missing; metadata removal is the source of truth.
        pass
    await log_audit(db, user, "delete", "task_attachment", str(attachment_id))
    await db.commit()


async def _get_accessible_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    user: Employee,
) -> TaskProject:
    project = await get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    if not await can_access_task_project(db, user, project):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="project access denied")
    return project


async def _ensure_project_access(db: AsyncSession, project_id: uuid.UUID, user: Employee) -> None:
    await _get_accessible_project(db, project_id, user)


async def _get_accessible_task(db: AsyncSession, task_id: uuid.UUID, user: Employee) -> Task:
    task = await get_task_record(db, task_id)
    if task is None:
        deleted = await get_task_record(db, task_id, include_deleted=True)
        if deleted is not None:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="task deleted")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    if not await can_access_task(db, user, task):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="task access denied")
    return task


async def _get_project_state(db: AsyncSession, project_id: uuid.UUID, state_id: uuid.UUID) -> TaskState:
    state_row = await db.get(TaskState, state_id)
    if state_row is None or state_row.task_project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="state not found")
    return state_row


async def _get_project_label(db: AsyncSession, project_id: uuid.UUID, label_id: uuid.UUID) -> TaskLabel:
    label = await db.get(TaskLabel, label_id)
    if label is None or label.task_project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="label not found")
    return label


async def _get_task_comment(db: AsyncSession, task_id: uuid.UUID, comment_id: uuid.UUID) -> TaskComment:
    comment = await db.get(TaskComment, comment_id)
    if comment is None or comment.task_id != task_id or comment.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="comment not found")
    return comment


async def _get_task_attachment(
    db: AsyncSession,
    task_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> TaskAttachment:
    attachment = await get_task_attachment(db, attachment_id)
    if attachment is None or attachment.task_id != task_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="attachment not found",
        )
    return attachment


async def _ensure_project_writable(db: AsyncSession, project_id: uuid.UUID) -> None:
    project = await db.get(TaskProject, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )
    if project.is_archived:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="project archived",
        )


async def _call_service(coro: Any) -> Any:
    try:
        return await coro
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        message = str(exc)
        if "version conflict" in message:
            code = status.HTTP_409_CONFLICT
            detail = "version conflict"
        elif "task deleted" in message:
            code = status.HTTP_410_GONE
            detail = "task deleted"
        elif "exceeds maximum size" in message:
            code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
            detail = "attachment exceeds maximum size"
        elif "not found" in message:
            code = status.HTTP_404_NOT_FOUND
            detail = message
        else:
            code = status.HTTP_400_BAD_REQUEST
            detail = message
        raise HTTPException(status_code=code, detail=detail) from exc


def _dedupe_ids(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    deduped: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for item in ids:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


async def _comment_mention_ids(db: AsyncSession, comment_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(TaskActivity.meta).where(
            TaskActivity.verb == "commented",
            TaskActivity.meta["comment_id"].astext == str(comment_id),
        )
    )
    meta = result.scalar_one_or_none()
    if meta is None:
        return []

    mention_ids: list[uuid.UUID] = []
    for raw_id in meta.get("mentions", []):
        try:
            mention_ids.append(uuid.UUID(str(raw_id)))
        except (TypeError, ValueError):
            continue
    return mention_ids


async def _task_assignee_ids(db: AsyncSession, task_id: uuid.UUID) -> list[uuid.UUID]:
    result = await db.execute(
        select(TaskAssignee.employee_id).where(TaskAssignee.task_id == task_id)
    )
    return list(result.scalars().all())


async def _enqueue_assignment_notifications(task_id: uuid.UUID, assignee_ids: list[uuid.UUID]) -> None:
    if not assignee_ids:
        return
    try:
        from app.worker import get_arq_pool

        pool = await get_arq_pool()
        await pool.enqueue_job(
            "task_assignment_notification",
            task_id=str(task_id),
            assignee_ids=[str(employee_id) for employee_id in _dedupe_ids(assignee_ids)],
        )
    except Exception:
        # Notifications are best-effort; task mutations must not fail when Redis is unavailable.
        return
