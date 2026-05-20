# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportExplicitAny=false
from __future__ import annotations

import uuid
from dataclasses import dataclass
from itertools import count
from typing import Callable

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Department,
    Employee,
    EmployeeDepartmentMembership,
    MembershipRole,
    TaskProject,
    TelegramGroupBinding,
    TelegramIdentity,
    UnitType,
)
from app.schemas.tasks import TaskProjectCreate
from app.services.task_project_service import create_task_project


@dataclass(slots=True)
class BoundTelegramGroupFixture:
    department: Department
    project: TaskProject
    binding: TelegramGroupBinding
    lead: Employee
    member: Employee
    lead_identity: TelegramIdentity
    member_identity: TelegramIdentity


@pytest.fixture
def telegram_chat_id_factory() -> Callable[[], int]:
    counter = count(1)

    def _create() -> int:
        return -1_000_000_000_000 - next(counter)

    return _create


@pytest.fixture
def telegram_message_factory(
    telegram_chat_id_factory: Callable[[], int],
) -> Callable[..., dict]:
    counter = count(1)

    def _create(
        *,
        text: str = "Test Telegram message",
        chat_id: int | None = None,
        message_thread_id: int | None = None,
        from_user_id: int = 424242,
        from_username: str = "telegram_user",
        entities: list[dict] | None = None,
        chat_title: str = "CMD Support Telegram Group",
        chat_type: str = "supergroup",
        message_id: int | None = None,
        date: int = 1_700_000_000,
        **extra: dict,
    ) -> dict:
        resolved_chat_id = chat_id if chat_id is not None else telegram_chat_id_factory()
        payload: dict = {
            "message_id": message_id if message_id is not None else next(counter),
            "date": date,
            "chat": {
                "id": resolved_chat_id,
                "title": chat_title,
                "type": chat_type,
            },
            "from": {
                "id": from_user_id,
                "is_bot": False,
                "username": from_username,
                "first_name": extra.pop("from_first_name", "Telegram"),
            },
            "text": text,
        }
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        if entities is not None:
            payload["entities"] = entities
        payload.update(extra)
        return payload

    return _create


@pytest.fixture
def telegram_update_factory(
    telegram_message_factory: Callable[..., dict],
) -> Callable[..., dict]:
    counter = count(1)

    def _create(
        *,
        message: dict | None = None,
        **message_kwargs: dict,
    ) -> dict:
        payload = message if message is not None else telegram_message_factory(**message_kwargs)
        return {
            "update_id": next(counter),
            "message": payload,
        }

    return _create


@pytest_asyncio.fixture
async def department_factory(db_session: AsyncSession):
    async def _create(
        *,
        name: str = "Telegram Department",
        description: str | None = None,
        unit_type: UnitType = UnitType.BUSINESS_GROUP,
        is_archived: bool = False,
    ) -> Department:
        suffix = uuid.uuid4().hex[:8]
        department = Department(
            name=f"{name} {suffix}",
            description=description,
            unit_type=unit_type,
            is_archived=is_archived,
        )
        db_session.add(department)
        await db_session.flush()
        await db_session.refresh(department)
        return department

    return _create


@pytest_asyncio.fixture
async def employee_factory(
    db_session: AsyncSession,
    department_factory,
):
    async def _create(
        *,
        department_id: uuid.UUID | None = None,
        name: str = "Telegram Employee",
        username: str | None = None,
        email: str | None = None,
        role: str = "employee",
        is_active: bool = True,
    ) -> Employee:
        if department_id is None:
            department = await department_factory()
            department_id = department.id
        suffix = uuid.uuid4().hex[:8]
        employee = Employee(
            name=f"{name} {suffix}",
            email=email or f"{suffix}@example.test",
            username=username or f"telegram_{suffix}",
            role=role,
            department_id=department_id,
            is_active=is_active,
        )
        db_session.add(employee)
        await db_session.flush()
        await db_session.refresh(employee)
        return employee

    return _create


@pytest_asyncio.fixture
async def task_project_factory(
    db_session: AsyncSession,
    department_factory,
    employee_factory,
):
    async def _create(
        *,
        department_id: uuid.UUID | None = None,
        creator: Employee | None = None,
        name: str = "Telegram Task Project",
        identifier: str = "TGPROJ",
        allow_any_employee: bool = False,
    ) -> TaskProject:
        if department_id is None:
            department = await department_factory()
            department_id = department.id
        if creator is None:
            creator = await employee_factory(department_id=department_id, name="Project Creator")
        project = await create_task_project(
            db_session,
            TaskProjectCreate(
                name=name,
                identifier=identifier,
                department_id=department_id,
                allow_any_employee=allow_any_employee,
            ),
            creator,
        )
        return project

    return _create


@pytest_asyncio.fixture
async def bound_telegram_group(
    db_session: AsyncSession,
    employee_factory,
    department_factory,
    task_project_factory,
) -> BoundTelegramGroupFixture:
    department = await department_factory(name="Telegram Bound Department")
    lead = await employee_factory(
        department_id=department.id,
        name="Telegram Lead",
        username=f"telegram_lead_{uuid.uuid4().hex[:8]}",
    )
    member = await employee_factory(
        department_id=department.id,
        name="Telegram Member",
        username=f"telegram_member_{uuid.uuid4().hex[:8]}",
    )
    project = await task_project_factory(
        department_id=department.id,
        creator=lead,
        name="Telegram Default Project",
        identifier=f"TGD{uuid.uuid4().hex[:3].upper()}",
    )

    memberships = [
        EmployeeDepartmentMembership(
            employee_id=lead.id,
            department_id=department.id,
            role=MembershipRole.LEAD,
            is_active=True,
        ),
        EmployeeDepartmentMembership(
            employee_id=member.id,
            department_id=department.id,
            role=MembershipRole.MEMBER,
            is_active=True,
        ),
    ]
    binding = TelegramGroupBinding(
        department_id=department.id,
        default_task_project_id=project.id,
        chat_id=-100_000_000_000_1,
        message_thread_id=101,
        chat_title="Telegram Bound Department",
        chat_type="supergroup",
        is_active=True,
        bound_by_id=lead.id,
    )
    lead_identity = TelegramIdentity(
        employee_id=lead.id,
        telegram_user_id=100_000_001,
        telegram_username="telegram_lead",
        display_name=lead.name,
        is_active=True,
    )
    member_identity = TelegramIdentity(
        employee_id=member.id,
        telegram_user_id=100_000_002,
        telegram_username="telegram_member",
        display_name=member.name,
        is_active=True,
    )
    db_session.add_all([*memberships, binding, lead_identity, member_identity])
    await db_session.flush()
    await db_session.refresh(binding)
    await db_session.refresh(lead_identity)
    await db_session.refresh(member_identity)
    return BoundTelegramGroupFixture(
        department=department,
        project=project,
        binding=binding,
        lead=lead,
        member=member,
        lead_identity=lead_identity,
        member_identity=member_identity,
    )
