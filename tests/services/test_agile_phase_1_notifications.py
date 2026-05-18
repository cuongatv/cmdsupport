"""Service-layer tests for Phase 1 notifications (WIP exceeded + aging scan)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from app.config import settings
from app.database.models import (
    Employee,
    Notification,
    Task,
    TaskAssignee,
    TaskState,
)
from app.schemas.tasks import TaskCreate, TaskProjectCreate
from app.services.task_notification_service import (
    NOTIFICATION_TYPE_TASK_AGING_ALERT,
    NOTIFICATION_TYPE_TASK_WIP_EXCEEDED,
    scan_aging_tasks,
)
from app.services.task_project_service import create_task_project
from app.services.task_service import create_task, move_task_state

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers (mirror the patterns in tests/services/test_agile_phase_1.py and
# tests/services/test_task_notifications.py to keep fixture style consistent).
# ---------------------------------------------------------------------------


async def _insert_department(db_session) -> uuid.UUID:
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {"id": department_id, "name": f"Aging Dept {department_id.hex[:8]}"},
    )
    return department_id


async def _insert_workspace(db_session) -> uuid.UUID:
    workspace_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO projects (id, name) VALUES (:id, :name)"),
        {"id": workspace_id, "name": f"Aging WS {workspace_id.hex[:8]}"},
    )
    return workspace_id


async def _insert_employee(
    db_session, *, name: str = "Aging Tester", is_active: bool = True
) -> Employee:
    department_id = await _insert_department(db_session)
    employee_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, role, department_id, is_active)
            VALUES (:id, :name, :email, 'employee', :department_id, :is_active)
            """
        ),
        {
            "id": employee_id,
            "name": f"{name} {employee_id.hex[:6]}",
            "email": f"{employee_id.hex[:12]}@example.test",
            "department_id": department_id,
            "is_active": is_active,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


async def _make_project(db_session):
    workspace_id = await _insert_workspace(db_session)
    creator = await _insert_employee(db_session, name="Aging Creator")
    project = await create_task_project(
        db_session,
        TaskProjectCreate(
            name="Aging Project",
            identifier=f"AG{workspace_id.hex[:4].upper()}",
            workspace_id=workspace_id,
        ),
        creator,
    )
    states = sorted(project.states, key=lambda item: item.position)
    return project, states, creator


async def _set_aging_threshold(db_session, state: TaskState, *, days: int | None) -> None:
    state.aging_warn_days = days
    db_session.add(state)
    await db_session.flush()


async def _force_task_updated_at(db_session, task_id: uuid.UUID, when: datetime) -> None:
    """Rewrite ``tasks.updated_at`` past the ORM's ``onupdate`` trigger.

    The ORM column has ``onupdate=func.now()`` so we cannot just assign and
    flush — the server-side default would overwrite our value. Raw SQL UPDATE
    bypasses the SQLAlchemy onupdate hook. The scan service uses
    ``populate_existing=True`` on its candidate query so the rewrite is visible
    even when SQLAlchemy already has the row in its identity map.
    """
    await db_session.execute(
        text("UPDATE tasks SET updated_at = :when WHERE id = :id"),
        {"when": when, "id": task_id},
    )
    await db_session.flush()


async def _notifications_for_task(
    db_session, task_id: uuid.UUID, *, notification_type: str
) -> list[Notification]:
    result = await db_session.execute(
        select(Notification).where(
            Notification.task_id == task_id,
            Notification.notification_type == notification_type,
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Aging scan — required scenarios
# ---------------------------------------------------------------------------


async def test_aging_scan_creates_vietnamese_notification_once(db_session, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    project, states, creator = await _make_project(db_session)
    in_progress = states[2]
    await _set_aging_threshold(db_session, in_progress, days=3)

    assignee = await _insert_employee(db_session, name="AgingAssignee")
    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="Hồ sơ tồn đọng", state_id=in_progress.id),
        creator,
    )
    db_session.add(TaskAssignee(task_id=task.id, employee_id=assignee.id))
    await db_session.flush()

    # Force the task to look 4 days stale (past the 3-day threshold).
    stale_ts = datetime.now(timezone.utc) - timedelta(days=4)
    await _force_task_updated_at(db_session, task.id, stale_ts)

    created = await scan_aging_tasks(db_session)
    relevant = [n for n in created if n.task_id == task.id]

    assert len(relevant) == 1
    notification = relevant[0]
    assert notification.notification_type == NOTIFICATION_TYPE_TASK_AGING_ALERT
    assert notification.recipient_id == assignee.id
    assert notification.is_read is False
    assert notification.title == "Hồ sơ tồn đọng"
    assert notification.body is not None
    assert "Công việc tồn đọng lâu" in notification.body
    assert "Hồ sơ tồn đọng" in notification.body
    assert "ngưỡng: 3 ngày" in notification.body


async def test_aging_scan_deduplication_prevents_second_notification(
    db_session, monkeypatch
):
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    project, states, creator = await _make_project(db_session)
    in_progress = states[2]
    await _set_aging_threshold(db_session, in_progress, days=2)

    assignee = await _insert_employee(db_session, name="DedupeAssignee")
    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="Task lặp", state_id=in_progress.id),
        creator,
    )
    db_session.add(TaskAssignee(task_id=task.id, employee_id=assignee.id))
    await db_session.flush()

    await _force_task_updated_at(
        db_session, task.id, datetime.now(timezone.utc) - timedelta(days=5)
    )

    first = await scan_aging_tasks(db_session)
    await db_session.flush()
    second = await scan_aging_tasks(db_session)

    first_relevant = [n for n in first if n.task_id == task.id]
    second_relevant = [n for n in second if n.task_id == task.id]

    assert len(first_relevant) == 1
    assert second_relevant == []

    persisted = await _notifications_for_task(
        db_session, task.id, notification_type=NOTIFICATION_TYPE_TASK_AGING_ALERT
    )
    assert len(persisted) == 1


async def test_aging_scan_skips_done_tasks(db_session, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    project, states, creator = await _make_project(db_session)
    done_state = states[4]
    cancelled_state = states[5]

    # Both terminal states have aging_warn_days set — scan must still skip them.
    await _set_aging_threshold(db_session, done_state, days=1)
    await _set_aging_threshold(db_session, cancelled_state, days=1)

    assignee = await _insert_employee(db_session, name="DoneAssignee")
    done_task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="Đã xong", state_id=done_state.id),
        creator,
    )
    cancelled_task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="Đã hủy", state_id=cancelled_state.id),
        creator,
    )
    db_session.add(TaskAssignee(task_id=done_task.id, employee_id=assignee.id))
    db_session.add(TaskAssignee(task_id=cancelled_task.id, employee_id=assignee.id))
    await db_session.flush()

    stale_ts = datetime.now(timezone.utc) - timedelta(days=10)
    await _force_task_updated_at(db_session, done_task.id, stale_ts)
    await _force_task_updated_at(db_session, cancelled_task.id, stale_ts)

    created = await scan_aging_tasks(db_session)
    relevant_ids = {n.task_id for n in created}

    assert done_task.id not in relevant_ids
    assert cancelled_task.id not in relevant_ids


# ---------------------------------------------------------------------------
# Aging scan — additional guards (feature flag + null threshold + recent task)
# ---------------------------------------------------------------------------


async def test_aging_scan_noop_when_feature_flag_off(db_session, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", False)
    project, states, creator = await _make_project(db_session)
    in_progress = states[2]
    in_progress.aging_warn_days = 1  # direct ORM set; flag is off so no gate trip
    db_session.add(in_progress)

    assignee = await _insert_employee(db_session, name="FlagOffAssignee")
    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="Cờ tắt", state_id=in_progress.id),
        creator,
    )
    db_session.add(TaskAssignee(task_id=task.id, employee_id=assignee.id))
    await db_session.flush()
    await _force_task_updated_at(
        db_session, task.id, datetime.now(timezone.utc) - timedelta(days=10)
    )

    assert await scan_aging_tasks(db_session) == []


async def test_aging_scan_skips_state_without_threshold(db_session, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    project, states, creator = await _make_project(db_session)
    in_progress = states[2]
    # aging_warn_days deliberately left NULL.
    assert in_progress.aging_warn_days is None

    assignee = await _insert_employee(db_session, name="NoThresholdAssignee")
    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="Không ngưỡng", state_id=in_progress.id),
        creator,
    )
    db_session.add(TaskAssignee(task_id=task.id, employee_id=assignee.id))
    await db_session.flush()
    await _force_task_updated_at(
        db_session, task.id, datetime.now(timezone.utc) - timedelta(days=30)
    )

    assert await scan_aging_tasks(db_session) == []


async def test_aging_scan_skips_recent_task(db_session, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    project, states, creator = await _make_project(db_session)
    in_progress = states[2]
    await _set_aging_threshold(db_session, in_progress, days=7)

    assignee = await _insert_employee(db_session, name="RecentAssignee")
    task = await create_task(
        db_session,
        project.id,
        TaskCreate(title="Mới cập nhật", state_id=in_progress.id),
        creator,
    )
    db_session.add(TaskAssignee(task_id=task.id, employee_id=assignee.id))
    await db_session.flush()
    # Touched 1 day ago — well under the 7-day threshold.
    await _force_task_updated_at(
        db_session, task.id, datetime.now(timezone.utc) - timedelta(days=1)
    )

    assert await scan_aging_tasks(db_session) == []


# ---------------------------------------------------------------------------
# WIP exceeded — notification fan-out from move_task_state(warn)
# ---------------------------------------------------------------------------


async def test_wip_warn_creates_notification_for_assignees(db_session, monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", True)
    project, states, creator = await _make_project(db_session)
    backlog, in_progress = states[0], states[2]

    # Pin a task into the target state so the move trips the warn limit.
    blocker = await create_task(
        db_session,
        project.id,
        TaskCreate(title="blocker", state_id=in_progress.id),
        creator,
    )
    assert blocker.state_id == in_progress.id
    in_progress.wip_limit = 1
    in_progress.wip_policy = "warn"
    db_session.add(in_progress)
    await db_session.flush()

    actor = await _insert_employee(db_session, name="WipActor")
    other_assignee = await _insert_employee(db_session, name="WipAssignee")

    moving = await create_task(
        db_session,
        project.id,
        TaskCreate(title="moving-into-wip", state_id=backlog.id),
        actor,
    )
    db_session.add(TaskAssignee(task_id=moving.id, employee_id=actor.id))
    db_session.add(TaskAssignee(task_id=moving.id, employee_id=other_assignee.id))
    await db_session.flush()

    moved, advisory, _ = await move_task_state(
        db_session, moving.id, in_progress.id, 5000.0, actor
    )
    assert advisory is not None
    assert moved.state_id == in_progress.id

    notifications = await _notifications_for_task(
        db_session, moved.id, notification_type=NOTIFICATION_TYPE_TASK_WIP_EXCEEDED
    )
    # Actor excluded — only the second assignee receives the persistent ping.
    assert {n.recipient_id for n in notifications} == {other_assignee.id}
    assert all(n.actor_id == actor.id for n in notifications)
    assert all(
        n.body == f"Vượt giới hạn việc đang làm tại trạng thái {in_progress.name}"
        for n in notifications
    )


async def test_wip_warn_no_notification_when_feature_flag_off(db_session, monkeypatch):
    # When the flag is off, the WIP advisory check itself short-circuits, so
    # there should be no notification AND no advisory dict.
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_1", False)
    project, states, creator = await _make_project(db_session)
    backlog, in_progress = states[0], states[2]

    await create_task(
        db_session,
        project.id,
        TaskCreate(title="blocker-off", state_id=in_progress.id),
        creator,
    )
    in_progress.wip_limit = 1
    in_progress.wip_policy = "warn"
    db_session.add(in_progress)
    await db_session.flush()

    actor = await _insert_employee(db_session, name="WipActorOff")
    assignee = await _insert_employee(db_session, name="WipAssigneeOff")
    moving = await create_task(
        db_session,
        project.id,
        TaskCreate(title="moving-off", state_id=backlog.id),
        actor,
    )
    db_session.add(TaskAssignee(task_id=moving.id, employee_id=assignee.id))
    await db_session.flush()

    moved, advisory, _ = await move_task_state(
        db_session, moving.id, in_progress.id, 4000.0, actor
    )
    assert advisory is None
    assert moved.state_id == in_progress.id

    notifications = await _notifications_for_task(
        db_session, moved.id, notification_type=NOTIFICATION_TYPE_TASK_WIP_EXCEEDED
    )
    assert notifications == []


# Imports referenced indirectly (e.g. ``Task``, ``TaskState``) keep IDEs happy
# even when unused at module top — the bodies below exercise both via ORM.
_ = (Task, TaskState)
