from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.database.models import (
    Employee,
    Notification,
    Task,
    TaskActivity,
    TaskAssignee,
    TaskComment,
)
from app.routers.tasks import create_comment_endpoint
from app.schemas.tasks import TaskCommentCreate, TaskCreate, TaskProjectCreate
from app.services.task_comment_service import (
    create_comment,
    delete_comment,
    extract_mentions,
    list_activities,
    update_comment,
)
from app.services.task_constants import MAX_DESCRIPTION_BYTES
from app.services.task_project_service import create_task_project
from app.services.task_service import create_task, soft_delete_task

pytestmark = pytest.mark.asyncio


async def _insert_department(db_session, name: str = "Comments Department") -> uuid.UUID:
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": department_id, "name": f"{name} {department_id.hex[:8]}"},
    )
    return department_id


async def _insert_workspace(db_session, name: str = "Comments Workspace") -> uuid.UUID:
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
    name: str = "Comments Tester",
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
    department_id = await _insert_department(db_session)
    author = await _insert_employee(db_session, department_id=department_id)
    project = await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Comments Project",
            identifier=f"CM{department_id.hex[:4].upper()}",
            department_id=department_id,
        ),
        author,
    )
    state = sorted(project.states, key=lambda item: item.position)[0]
    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="Commentable Task", state_id=state.id),
        author,
    )
    return task, author


def _mention(employee_id: uuid.UUID, label: str = "User") -> str:
    return f'<mention id="{employee_id}">@{label}</mention>'


async def _activities_for(db_session, task_id: uuid.UUID) -> list[TaskActivity]:
    result = await db_session.execute(
        select(TaskActivity).where(TaskActivity.task_id == task_id)
    )
    return list(result.scalars().all())


async def test_create_comment_endpoint_notifies_assignees_and_mentions(db_session):
    task, author = await _seed_task(db_session)
    assignee = await _insert_employee(db_session, name="Assignee")
    mentioned = await _insert_employee(db_session, name="Mentioned")
    db_session.add(TaskAssignee(task_id=task.id, employee_id=assignee.id))
    await db_session.flush()

    await create_comment_endpoint(
        task.id,
        TaskCommentCreate(body=f"Please check {_mention(mentioned.id, 'Mentioned')}"),
        db_session,
        author,
    )

    result = await db_session.execute(
        select(Notification).where(Notification.task_id == task.id)
    )
    notifications = list(result.scalars().all())
    assert {(row.recipient_id, row.notification_type) for row in notifications} == {
        (assignee.id, "commented"),
        (mentioned.id, "mentioned"),
    }
    assert all(row.actor_id == author.id for row in notifications)


async def test_comment_create_creates_activity_and_mentions(db_session):
    task, author = await _seed_task(db_session)
    mentioned = await _insert_employee(db_session, name="Mentioned")

    body = f"Hello {_mention(mentioned.id, 'Mentioned')} how are you?"
    comment = await create_comment(db_session, task.id, body, author)

    assert comment.id is not None
    assert comment.body == body
    assert comment.author_id == author.id
    assert comment.task_id == task.id
    assert comment.is_edited is False
    assert comment.deleted_at is None

    activities = await _activities_for(db_session, task.id)
    commented = [activity for activity in activities if activity.verb == "commented"]
    assert len(commented) == 1
    activity = commented[0]
    assert activity.actor_id == author.id
    assert activity.meta is not None
    assert activity.meta.get("comment_id") == str(comment.id)
    assert activity.meta.get("mentions") == [str(mentioned.id)]


async def test_comment_extracts_only_active_employee_mentions(db_session):
    task, author = await _seed_task(db_session)
    first = await _insert_employee(db_session, name="First")
    second = await _insert_employee(db_session, name="Second")

    body = f"hi {_mention(first.id, 'First')} and {_mention(second.id, 'Second')}"
    mentions = await extract_mentions(body, db_session)

    assert mentions == [first.id, second.id]


async def test_comment_extracts_drops_inactive_and_missing_ids(db_session):
    task, author = await _seed_task(db_session)
    active = await _insert_employee(db_session, name="Active")
    inactive = await _insert_employee(db_session, name="Inactive", is_active=False)
    missing_id = uuid.uuid4()

    body = (
        f"{_mention(active.id, 'A')} "
        f"{_mention(inactive.id, 'I')} "
        f"{_mention(missing_id, 'X')} "
        '<mention id="not-a-uuid">@Bad</mention>'
    )
    mentions = await extract_mentions(body, db_session)

    assert mentions == [active.id]


async def test_comment_body_too_long_rejected(db_session):
    task, author = await _seed_task(db_session)

    body = "a" * (MAX_DESCRIPTION_BYTES + 1)
    with pytest.raises(ValueError):
        await create_comment(db_session, task.id, body, author)


async def test_comment_on_deleted_task_rejected(db_session):
    task, author = await _seed_task(db_session)
    await soft_delete_task(db_session, task.id, author)

    with pytest.raises(ValueError, match="task deleted"):
        await create_comment(db_session, task.id, "hi", author)


async def test_comment_edit_marks_edited_at_and_creates_activity(db_session):
    task, author = await _seed_task(db_session)
    comment = await create_comment(db_session, task.id, "original body", author)

    assert comment.is_edited is False
    original_updated_at = comment.updated_at

    edited = await update_comment(db_session, comment.id, "edited body", author)

    assert edited.id == comment.id
    assert edited.body == "edited body"
    assert edited.is_edited is True
    assert edited.updated_at >= original_updated_at

    activities = await _activities_for(db_session, task.id)
    edits = [activity for activity in activities if activity.verb == "comment_edited"]
    assert len(edits) == 1
    assert edits[0].actor_id == author.id
    assert edits[0].meta is not None
    assert edits[0].meta.get("comment_id") == str(comment.id)


async def test_comment_delete_soft_deletes_and_creates_activity(db_session):
    task, author = await _seed_task(db_session)
    comment = await create_comment(db_session, task.id, "to be deleted", author)

    await delete_comment(db_session, comment.id, author)

    refreshed = await db_session.get(TaskComment, comment.id)
    assert refreshed is not None
    assert refreshed.deleted_at is not None

    activities = await _activities_for(db_session, task.id)
    deletes = [activity for activity in activities if activity.verb == "comment_deleted"]
    assert len(deletes) == 1
    assert deletes[0].actor_id == author.id
    assert deletes[0].meta is not None
    assert deletes[0].meta.get("comment_id") == str(comment.id)


async def test_list_activities_chronological(db_session):
    task, author = await _seed_task(db_session)
    comment = await create_comment(db_session, task.id, "first", author)
    await update_comment(db_session, comment.id, "second", author)
    await delete_comment(db_session, comment.id, author)

    activities = await list_activities(db_session, task.id)

    verbs = [activity.verb for activity in activities]
    assert verbs == ["created", "commented", "comment_edited", "comment_deleted"]
    timestamps = [activity.created_at for activity in activities]
    assert timestamps == sorted(timestamps)
