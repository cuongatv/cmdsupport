from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.asyncio

NATIVE_TASK_TABLES = {
    "task_projects",
    "task_states",
    "tasks",
    "task_assignees",
    "task_labels",
    "task_label_links",
    "task_comments",
    "task_attachments",
    "task_activities",
    "notifications",
}


async def _insert_department(db_session, department_id: uuid.UUID, name: str = "Tasks Department") -> None:
    await db_session.execute(
        text(
            """
            INSERT INTO departments (id, name)
            VALUES (:id, :name)
            """
        ),
        {"id": department_id, "name": f"{name} {department_id.hex[:8]}"},
    )


async def _insert_workspace(db_session, workspace_id: uuid.UUID, name: str = "Tasks Workspace") -> None:
    await db_session.execute(
        text(
            """
            INSERT INTO projects (id, name)
            VALUES (:id, :name)
            """
        ),
        {"id": workspace_id, "name": f"{name} {workspace_id.hex[:8]}"},
    )


async def _insert_task_project(
    db_session,
    *,
    workspace_id: uuid.UUID | None,
    department_id: uuid.UUID | None,
) -> None:
    await db_session.execute(
        text(
            """
            INSERT INTO task_projects (id, name, identifier, workspace_id, department_id)
            VALUES (:id, :name, :identifier, :workspace_id, :department_id)
            """
        ),
        {
            "id": uuid.uuid4(),
            "name": "Native Tasks",
            "identifier": "NT",
            "workspace_id": workspace_id,
            "department_id": department_id,
        },
    )
    await db_session.commit()


async def test_task_project_scope_xor_workspace_valid(db_session):
    workspace_id = uuid.uuid4()
    await _insert_workspace(db_session, workspace_id)

    await _insert_task_project(
        db_session,
        workspace_id=workspace_id,
        department_id=None,
    )


async def test_task_project_scope_xor_department_valid(db_session):
    department_id = uuid.uuid4()
    await _insert_department(db_session, department_id)

    await _insert_task_project(
        db_session,
        workspace_id=None,
        department_id=department_id,
    )


async def test_task_project_scope_xor_both_null_rejected(db_session):
    with pytest.raises(IntegrityError):
        await _insert_task_project(
            db_session,
            workspace_id=None,
            department_id=None,
        )


async def test_task_project_scope_xor_both_set_rejected(db_session):
    workspace_id = uuid.uuid4()
    department_id = uuid.uuid4()
    await _insert_workspace(db_session, workspace_id)
    await _insert_department(db_session, department_id)

    with pytest.raises(IntegrityError):
        await _insert_task_project(
            db_session,
            workspace_id=workspace_id,
            department_id=department_id,
        )


async def test_all_native_task_tables_exist(db_session):
    result = await db_session.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ANY(:table_names)
            """
        ),
        {"table_names": list(NATIVE_TASK_TABLES)},
    )

    found_tables = set(result.scalars())

    assert found_tables == NATIVE_TASK_TABLES
