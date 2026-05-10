"""Tests for the task attachment metadata service."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.database.models import Employee, Task, TaskActivity
from app.schemas.tasks import TaskCreate, TaskProjectCreate
from app.services.task_attachment_service import (
    create_attachment_metadata,
    delete_attachment,
    get_attachment,
    list_attachments,
    validate_upload,
)
from app.services.task_constants import MAX_ATTACHMENT_BYTES, MAX_ATTACHMENTS_PER_TASK
from app.services.task_project_service import create_task_project
from app.services.task_service import create_task, soft_delete_task

pytestmark = pytest.mark.asyncio


async def _insert_department(db_session, name: str = "Attach Department") -> uuid.UUID:
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": department_id, "name": f"{name} {department_id.hex[:8]}"},
    )
    return department_id


async def _insert_workspace(db_session, name: str = "Attach Workspace") -> uuid.UUID:
    workspace_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
        {"id": workspace_id, "name": f"{name} {workspace_id.hex[:8]}"},
    )
    return workspace_id


async def _insert_employee(
    db_session,
    *,
    department_id: uuid.UUID | None = None,
    role: str = "employee",
    name: str = "Attach Tester",
    is_active: bool = True,
) -> Employee:
    if department_id is None:
        department_id = await _insert_department(db_session)
    employee_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, role, department_id, is_active)
            VALUES (:id, :name, :email, :role, :department_id, :is_active)
            """
        ),
        {
            "id": employee_id,
            "name": f"{name} {employee_id.hex[:6]}",
            "email": f"{employee_id.hex[:12]}@example.test",
            "role": role,
            "department_id": department_id,
            "is_active": is_active,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


async def _seed_task(db_session) -> tuple[Task, Employee]:
    workspace_id = await _insert_workspace(db_session)
    actor = await _insert_employee(db_session)
    project = await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Attach Project",
            identifier=f"AT{workspace_id.hex[:4].upper()}",
            workspace_id=workspace_id,
        ),
        actor,
    )
    state = sorted(project.states, key=lambda item: item.position)[0]
    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="Attachable Task", state_id=state.id),
        actor,
    )
    return task, actor


async def test_create_attachment_metadata_success(db_session):
    task, actor = await _seed_task(db_session)

    attachment = await create_attachment_metadata(
        db_session,
        task_id=task.id,
        filename="design.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        actor=actor,
    )

    assert attachment.id is not None
    assert attachment.task_id == task.id
    assert attachment.filename == "design.pdf"
    assert attachment.content_type == "application/pdf"
    assert attachment.size_bytes == 1024
    assert attachment.uploaded_by_id == actor.id
    assert attachment.storage_key.startswith(
        f"task-attachments/{task.task_project_id}/{task.id}/"
    )
    assert attachment.storage_key.endswith("-design.pdf")


async def test_validate_upload_rejects_oversized_file(db_session):
    task, _ = await _seed_task(db_session)

    with pytest.raises(ValueError, match="size"):
        await validate_upload(
            filename="huge.pdf",
            size_bytes=MAX_ATTACHMENT_BYTES + 1,
            task_id=task.id,
            db=db_session,
        )


@pytest.mark.parametrize(
    "filename",
    [
        "malware.exe",
        "boot.bat",
        "deploy.ps1",
        "install.sh",
        "screen.scr",
        "old.com",
        "MALWARE.EXE",
        "Boot.Bat",
    ],
)
async def test_validate_upload_rejects_dangerous_extension(db_session, filename):
    task, _ = await _seed_task(db_session)

    with pytest.raises(ValueError, match="extension"):
        await validate_upload(
            filename=filename,
            size_bytes=10,
            task_id=task.id,
            db=db_session,
        )


async def test_validate_upload_rejects_11th_attachment(db_session):
    task, actor = await _seed_task(db_session)
    for i in range(MAX_ATTACHMENTS_PER_TASK):
        await create_attachment_metadata(
            db_session,
            task_id=task.id,
            filename=f"file_{i}.txt",
            content_type="text/plain",
            size_bytes=1,
            actor=actor,
        )

    with pytest.raises(ValueError, match="count"):
        await validate_upload(
            filename="overflow.txt",
            size_bytes=1,
            task_id=task.id,
            db=db_session,
        )


async def test_validate_upload_rejects_deleted_task(db_session):
    task, actor = await _seed_task(db_session)
    await soft_delete_task(db_session, task.id, actor)

    with pytest.raises(ValueError, match="deleted"):
        await validate_upload(
            filename="late.pdf",
            size_bytes=1,
            task_id=task.id,
            db=db_session,
        )


async def test_list_attachments_excludes_deleted(db_session):
    task, actor = await _seed_task(db_session)
    keeper = await create_attachment_metadata(
        db_session,
        task_id=task.id,
        filename="keep.pdf",
        content_type="application/pdf",
        size_bytes=10,
        actor=actor,
    )
    removable = await create_attachment_metadata(
        db_session,
        task_id=task.id,
        filename="drop.pdf",
        content_type="application/pdf",
        size_bytes=10,
        actor=actor,
    )

    await delete_attachment(db_session, removable.id, actor)

    listed = await list_attachments(db_session, task.id)
    listed_ids = {item.id for item in listed}

    assert keeper.id in listed_ids
    assert removable.id not in listed_ids
    assert len(listed) == 1


async def test_attachment_activity_metadata_never_contains_storage_key(db_session):
    task, actor = await _seed_task(db_session)
    attachment = await create_attachment_metadata(
        db_session,
        task_id=task.id,
        filename="safe.pdf",
        content_type="application/pdf",
        size_bytes=42,
        actor=actor,
    )
    await delete_attachment(db_session, attachment.id, actor)

    result = await db_session.execute(
        select(TaskActivity).where(
            TaskActivity.task_id == task.id,
            TaskActivity.verb.in_(["attachment_added", "attachment_removed"]),
        )
    )
    activities = list(result.scalars().all())
    assert len(activities) == 2
    for activity in activities:
        assert activity.meta is not None
        assert "storage_key" not in activity.meta
        assert activity.meta["filename"] == "safe.pdf"
        assert activity.meta["size_bytes"] == 42


async def test_delete_attachment_soft_deletes_and_returns_storage_key(db_session):
    task, actor = await _seed_task(db_session)
    attachment = await create_attachment_metadata(
        db_session,
        task_id=task.id,
        filename="report.pdf",
        content_type="application/pdf",
        size_bytes=42,
        actor=actor,
    )
    expected_storage_key = attachment.storage_key

    returned_key = await delete_attachment(db_session, attachment.id, actor)

    assert returned_key == expected_storage_key

    refreshed = await get_attachment(db_session, attachment.id)
    assert refreshed is None
