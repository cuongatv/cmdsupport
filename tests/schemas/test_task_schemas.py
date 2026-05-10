from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.tasks import (
    PaginatedResponse,
    TaskCreate,
    TaskOut,
    TaskProjectCreate,
    TaskStateCreate,
)


def test_task_create_rejects_invalid_priority() -> None:
    with pytest.raises(ValidationError):
        TaskCreate(title="x", state_id=uuid4(), priority="critical")


def test_task_create_accepts_valid_priority() -> None:
    task = TaskCreate(title="x", state_id=uuid4(), priority="high")
    assert task.priority == "high"


def test_task_create_rejects_oversized_description() -> None:
    with pytest.raises(ValidationError):
        TaskCreate(title="x", state_id=uuid4(), description="x" * 70000)


def test_task_create_accepts_valid_description() -> None:
    task = TaskCreate(title="x", state_id=uuid4(), description="x" * 64000)
    assert len(task.description or "") == 64000


def test_task_state_create_rejects_invalid_group() -> None:
    with pytest.raises(ValidationError):
        TaskStateCreate(name="Todo", group="sprint")


def test_task_state_create_accepts_valid_group() -> None:
    state = TaskStateCreate(name="In Progress", group="in_progress")
    assert state.group == "in_progress"


def test_pagination_shape() -> None:
    payload = PaginatedResponse[TaskOut](items=[], total=0, page=1, page_size=20, total_pages=0)
    data = payload.model_dump()
    assert set(data.keys()) == {"items", "total", "page", "page_size", "total_pages"}


def test_task_project_identifier_uppercased() -> None:
    project = TaskProjectCreate(name="Project", identifier="proj")
    assert project.identifier == "PROJ"


def test_task_project_identifier_rejects_lowercase_with_spaces() -> None:
    with pytest.raises(ValidationError):
        TaskProjectCreate(name="Project", identifier="my proj")
