"""Service-layer tests for Phase 3 squad capacity dashboards."""

from __future__ import annotations

import uuid
from typing import Optional

import pytest
from sqlalchemy import text

from app.config import settings
from app.database.models import (
    Employee,
    EmployeeDepartmentMembership,
    MembershipRole,
    Task,
    TaskAssignee,
    TaskProject,
    TaskState,
)
from app.services.task_dashboard_service import (
    get_squad_capacity,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


async def _insert_department(db_session, name_prefix: str = "P3 Dept") -> uuid.UUID:
    """Insert a department as a ``squad_team``.

    The squad-only membership roles (``product_owner``, ``scrum_master``,
    ``developer``) are gated by a DB trigger from migration 026 that requires
    ``departments.unit_type = 'squad_team'``. Phase 3 capacity rows model
    squad members specifically, so the fixture mirrors production setup.
    """
    department_id = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO departments (id, name, unit_type) "
            "VALUES (:id, :name, 'squad_team')"
        ),
        {
            "id": department_id,
            "name": f"{name_prefix} {department_id.hex[:6]}",
        },
    )
    return department_id


async def _insert_employee(
    db_session, department_id: uuid.UUID, *, name: str = "Employee"
) -> Employee:
    employee_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, role, department_id, is_active)
            VALUES (:id, :name, :email, 'employee', :dept, true)
            """
        ),
        {
            "id": employee_id,
            "name": f"{name}-{employee_id.hex[:6]}",
            "email": f"{employee_id.hex[:12]}@p3.test",
            "dept": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


async def _add_membership(
    db_session,
    employee: Employee,
    department_id: uuid.UUID,
    *,
    capacity_percent: Optional[int] = 100,
    role: MembershipRole = MembershipRole.DEVELOPER,
    is_active: bool = True,
) -> EmployeeDepartmentMembership:
    membership = EmployeeDepartmentMembership(
        employee_id=employee.id,
        department_id=department_id,
        role=role,
        capacity_percent=capacity_percent,
        is_active=is_active,
        is_primary=False,
    )
    db_session.add(membership)
    await db_session.flush()
    return membership


async def _create_dept_project(
    db_session,
    department_id: uuid.UUID,
    creator: Employee,
    *,
    identifier: str,
) -> tuple[TaskProject, list[TaskState]]:
    """Create a department-scoped task project with the three states we need.

    Returns the project plus its (backlog, done, cancelled) states as a tuple
    so callers don't trigger a lazy-load on the ``project.states``
    relationship — that would synchronously touch IO inside the async
    session and raise ``MissingGreenlet``.
    """
    project = TaskProject(
        id=uuid.uuid4(),
        name=f"P3 Project {identifier}",
        identifier=identifier,
        department_id=department_id,
        allow_any_employee=True,
        created_by_id=creator.id,
    )
    db_session.add(project)
    await db_session.flush()

    states: list[TaskState] = []
    for position, (state_name, group) in enumerate(
        [("Backlog", "backlog"), ("Done", "done"), ("Cancelled", "cancelled")]
    ):
        state = TaskState(
            id=uuid.uuid4(),
            task_project_id=project.id,
            name=state_name,
            group=group,
            position=float(position),
            is_default=(position == 0),
        )
        db_session.add(state)
        states.append(state)
    await db_session.flush()
    return project, states


async def _create_task(
    db_session,
    project: TaskProject,
    state: TaskState,
    creator: Employee,
    *,
    title: str = "T",
    story_points: Optional[int] = None,
) -> Task:
    task = Task(
        id=uuid.uuid4(),
        task_project_id=project.id,
        state_id=state.id,
        title=title,
        story_points=story_points,
        created_by_id=creator.id,
    )
    db_session.add(task)
    await db_session.flush()
    return task


async def _assign(db_session, task: Task, employee: Employee) -> None:
    db_session.add(TaskAssignee(task_id=task.id, employee_id=employee.id))
    await db_session.flush()


# ---------------------------------------------------------------------------
# Required scenarios
# ---------------------------------------------------------------------------


async def test_capacity_per_user_per_squad(db_session, monkeypatch):
    """Each active membership in the squad yields one capacity row with the
    employee's own counts. The membership.capacity_percent surfaces verbatim."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_3", True)

    dept_a = await _insert_department(db_session, name_prefix="SquadA")
    creator = await _insert_employee(db_session, dept_a, name="creator")
    alice = await _insert_employee(db_session, dept_a, name="alice")
    bob = await _insert_employee(db_session, dept_a, name="bob")

    await _add_membership(db_session, alice, dept_a, capacity_percent=100)
    await _add_membership(db_session, bob, dept_a, capacity_percent=50)

    project, states = await _create_dept_project(
        db_session, dept_a, creator, identifier="PA"
    )
    backlog = states[0]

    # Alice: 2 open tasks summing to 8 story points.
    t1 = await _create_task(db_session, project, backlog, creator, story_points=3)
    t2 = await _create_task(db_session, project, backlog, creator, story_points=5)
    await _assign(db_session, t1, alice)
    await _assign(db_session, t2, alice)

    # Bob: 1 open task with no story points.
    t3 = await _create_task(db_session, project, backlog, creator)
    await _assign(db_session, t3, bob)

    rows = await get_squad_capacity(db_session, dept_a)
    by_emp = {row.employee_id: row for row in rows}

    # Creator has no membership row → should NOT appear in the squad view
    # even though employees.department_id points at dept_a.
    assert creator.id not in by_emp
    assert alice.id in by_emp
    assert bob.id in by_emp

    alice_row = by_emp[alice.id]
    assert alice_row.department_id == dept_a
    assert alice_row.capacity_percent == 100
    assert alice_row.open_task_count == 2
    assert alice_row.story_points_sum == 8
    assert alice_row.is_overloaded is False

    bob_row = by_emp[bob.id]
    assert bob_row.department_id == dept_a
    assert bob_row.capacity_percent == 50
    assert bob_row.open_task_count == 1
    # No story_points set on Bob's task → SUM returns NULL → None.
    assert bob_row.story_points_sum is None
    assert bob_row.is_overloaded is False


async def test_done_tasks_excluded_from_capacity(db_session, monkeypatch):
    """Tasks whose state.group is done/cancelled are excluded from the open
    count by default; ``include_done=True`` adds them back in."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_3", True)

    dept = await _insert_department(db_session, name_prefix="Done")
    creator = await _insert_employee(db_session, dept, name="dcreator")
    user = await _insert_employee(db_session, dept, name="duser")
    await _add_membership(db_session, user, dept, capacity_percent=100)

    project, states = await _create_dept_project(
        db_session, dept, creator, identifier="PD"
    )
    backlog, done, cancelled = states[0], states[1], states[2]

    # Two open (Backlog) tasks: 2 + 3 story points = 5.
    for sp in (2, 3):
        task = await _create_task(
            db_session, project, backlog, creator, story_points=sp
        )
        await _assign(db_session, task, user)

    # One done + one cancelled (should be excluded by default).
    done_task = await _create_task(
        db_session, project, done, creator, story_points=8
    )
    await _assign(db_session, done_task, user)
    cancelled_task = await _create_task(
        db_session, project, cancelled, creator, story_points=4
    )
    await _assign(db_session, cancelled_task, user)

    rows_default = await get_squad_capacity(db_session, dept)
    row = next(r for r in rows_default if r.employee_id == user.id)
    assert row.open_task_count == 2
    assert row.story_points_sum == 5

    rows_all = await get_squad_capacity(db_session, dept, include_done=True)
    row_all = next(r for r in rows_all if r.employee_id == user.id)
    assert row_all.open_task_count == 4
    assert row_all.story_points_sum == 17


async def test_multisquad_user_appears_separately(db_session, monkeypatch):
    """A user belonging to two squads gets one row PER squad — never aggregated.
    Each row reflects only the tasks scoped to that squad's projects."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_3", True)

    dept_a = await _insert_department(db_session, name_prefix="MSA")
    dept_b = await _insert_department(db_session, name_prefix="MSB")
    creator = await _insert_employee(db_session, dept_a, name="ms-creator")
    multi = await _insert_employee(db_session, dept_a, name="multi")

    # Same employee, two memberships with different capacity_percent.
    await _add_membership(db_session, multi, dept_a, capacity_percent=60)
    await _add_membership(db_session, multi, dept_b, capacity_percent=40)

    project_a, states_a = await _create_dept_project(
        db_session, dept_a, creator, identifier="MSA"
    )
    project_b, states_b = await _create_dept_project(
        db_session, dept_b, creator, identifier="MSB"
    )

    # 1 open task in squad A (2 SP).
    task_a = await _create_task(
        db_session, project_a, states_a[0], creator, story_points=2
    )
    await _assign(db_session, task_a, multi)

    # 2 open tasks in squad B (1 + 4 SP).
    for sp in (1, 4):
        task_b = await _create_task(
            db_session, project_b, states_b[0], creator, story_points=sp
        )
        await _assign(db_session, task_b, multi)

    rows_a = await get_squad_capacity(db_session, dept_a)
    rows_b = await get_squad_capacity(db_session, dept_b)

    multi_in_a = [r for r in rows_a if r.employee_id == multi.id]
    multi_in_b = [r for r in rows_b if r.employee_id == multi.id]

    # One row per (employee, squad) pair — never aggregated across squads.
    assert len(multi_in_a) == 1
    assert len(multi_in_b) == 1

    assert multi_in_a[0].department_id == dept_a
    assert multi_in_a[0].capacity_percent == 60
    assert multi_in_a[0].open_task_count == 1
    assert multi_in_a[0].story_points_sum == 2

    assert multi_in_b[0].department_id == dept_b
    assert multi_in_b[0].capacity_percent == 40
    assert multi_in_b[0].open_task_count == 2
    assert multi_in_b[0].story_points_sum == 5


async def test_returns_empty_when_feature_flag_off(db_session, monkeypatch):
    """Regression guard: Phase 3 short-circuit mirrors Phase 1/2 contracts."""
    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_3", False)

    dept = await _insert_department(db_session, name_prefix="Off")
    creator = await _insert_employee(db_session, dept, name="off-creator")
    user = await _insert_employee(db_session, dept, name="off-user")
    await _add_membership(db_session, user, dept, capacity_percent=100)
    project, states = await _create_dept_project(
        db_session, dept, creator, identifier="POFF"
    )
    task = await _create_task(db_session, project, states[0], creator)
    await _assign(db_session, task, user)

    rows = await get_squad_capacity(db_session, dept)
    assert rows == []
