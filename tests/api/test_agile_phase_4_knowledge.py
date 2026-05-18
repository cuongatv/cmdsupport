"""API tests for the Phase 4 task ↔ wiki knowledge link surface (T15).

Mirrors ``tests/api/test_agile_phase_2_semantics.py``: in-process ASGI client
against the real router + service stack, ``db_session`` rollback fixture for
isolation, ``settings.FEATURE_AGILE_PHASE_4`` flipped per-test via
``monkeypatch``. Synthetic admin actor bypasses ``require_permission`` so the
knowledge-link contract is exercised in isolation from RBAC plumbing.

Covered scenarios (T15 acceptance criteria):

* ``test_add_knowledge_link_enabled`` — POST attaches a wiki page to a task
  and the row round-trips through GET.
* ``test_add_duplicate_link_rejected`` — re-posting the same pair surfaces
  ``409 DUPLICATE_KNOWLEDGE_LINK``.
* ``test_remove_knowledge_link`` — DELETE removes the row; GET reflects the
  removal.
* ``test_knowledge_link_disabled_returns_403`` — POST/DELETE fail with
  ``403 FEATURE_DISABLED`` when the flag is off; GET stays open.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Employee,
    Task,
    TaskKnowledgeLink,
    TaskProject,
    TaskState,
    WikiPage,
)


@pytest_asyncio.fixture
async def admin_employee(db_session: AsyncSession) -> Employee:
    """Synthetic admin ``Employee`` for the rollback session."""
    department_id = uuid.uuid4()
    await db_session.execute(
        text("INSERT INTO departments (id, name) VALUES (:id, :name)"),
        {
            "id": department_id,
            "name": f"Phase 4 Knowledge Dept {department_id.hex[:8]}",
        },
    )
    employee_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO employees (id, name, email, role, department_id, is_active)
            VALUES (:id, :name, :email, 'admin', :department_id, true)
            """
        ),
        {
            "id": employee_id,
            "name": "Phase 4 Knowledge API Admin",
            "email": f"{employee_id.hex[:12]}@example.test",
            "department_id": department_id,
        },
    )
    employee = await db_session.get(Employee, employee_id)
    assert employee is not None
    return employee


@pytest_asyncio.fixture
async def task_with_wiki(
    db_session: AsyncSession,
    admin_employee: Employee,
) -> tuple[Task, WikiPage, WikiPage]:
    """Department-scoped project with a single task + two wiki pages.

    Two wiki pages so the duplicate scenario can use one page while the
    add/remove scenario can use either independently.
    """
    project = TaskProject(
        name="Phase 4 Knowledge Project",
        description=None,
        identifier=f"P4{uuid.uuid4().hex[:5].upper()}",
        workspace_id=None,
        department_id=admin_employee.department_id,
        created_by_id=admin_employee.id,
        allow_any_employee=False,
    )
    db_session.add(project)
    await db_session.flush()

    backlog = TaskState(
        task_project_id=project.id,
        name="Backlog",
        group="backlog",
        position=0.0,
        is_default=True,
    )
    db_session.add(backlog)
    await db_session.flush()

    task = Task(
        task_project_id=project.id,
        state_id=backlog.id,
        title="Knowledge link host task",
        priority="none",
        position=1000.0,
    )
    db_session.add(task)

    page_a = WikiPage(
        slug=f"page-a-{uuid.uuid4().hex[:6]}",
        title="Quy trình phê duyệt",
        page_type="sop",
        content_md="# Quy trình",
        summary="Quy trình phê duyệt nội bộ",
    )
    page_b = WikiPage(
        slug=f"page-b-{uuid.uuid4().hex[:6]}",
        title="Tiêu chuẩn kỹ thuật",
        page_type="reference",
        content_md="# Tiêu chuẩn",
        summary="Tiêu chuẩn kỹ thuật áp dụng",
    )
    db_session.add(page_a)
    db_session.add(page_b)
    await db_session.flush()
    await db_session.refresh(task)
    await db_session.refresh(page_a)
    await db_session.refresh(page_b)
    return task, page_a, page_b


@pytest_asyncio.fixture
async def api_client(
    db_session: AsyncSession, admin_employee: Employee
) -> AsyncIterator[httpx.AsyncClient]:
    """In-process ASGI client wired to the rollback session + admin actor."""
    from app.database import get_db
    from app.main import app
    from app.services.auth_service import get_current_user

    async def _db_override():
        yield db_session

    async def _user_override():
        return admin_employee

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_current_user] = _user_override

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        try:
            yield client
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)


async def test_add_knowledge_link_enabled(
    api_client: httpx.AsyncClient,
    task_with_wiki: tuple[Task, WikiPage, WikiPage],
    admin_employee: Employee,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST attaches a wiki page; GET reflects the link with the right metadata."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_4", True)
    task, page_a, _ = task_with_wiki

    resp = await api_client.post(
        f"/api/tasks/{task.id}/knowledge-links",
        json={
            "wiki_page_id": str(page_a.id),
            "link_type": "requirement",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["task_id"] == str(task.id)
    assert body["wiki_page_id"] == str(page_a.id)
    assert body["link_type"] == "requirement"
    assert body["created_by_id"] == str(admin_employee.id)

    list_resp = await api_client.get(f"/api/tasks/{task.id}/knowledge-links")
    assert list_resp.status_code == 200, list_resp.text
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["wiki_page_id"] == str(page_a.id)
    assert rows[0]["link_type"] == "requirement"


async def test_add_duplicate_link_rejected(
    api_client: httpx.AsyncClient,
    task_with_wiki: tuple[Task, WikiPage, WikiPage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding the same (task, wiki_page) pair twice returns 409 DUPLICATE_KNOWLEDGE_LINK."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_4", True)
    task, page_a, _ = task_with_wiki

    body = {"wiki_page_id": str(page_a.id), "link_type": "reference"}
    r1 = await api_client.post(f"/api/tasks/{task.id}/knowledge-links", json=body)
    assert r1.status_code == 201, r1.text

    r2 = await api_client.post(f"/api/tasks/{task.id}/knowledge-links", json=body)
    assert r2.status_code == 409, r2.text
    assert r2.json()["detail"]["code"] == "DUPLICATE_KNOWLEDGE_LINK"

    # The link set must contain exactly one row — duplicate insert was a no-op.
    list_resp = await api_client.get(f"/api/tasks/{task.id}/knowledge-links")
    assert list_resp.status_code == 200, list_resp.text
    assert len(list_resp.json()) == 1


async def test_remove_knowledge_link(
    api_client: httpx.AsyncClient,
    task_with_wiki: tuple[Task, WikiPage, WikiPage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELETE removes the link and the GET list reflects the removal."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_4", True)
    task, page_a, page_b = task_with_wiki

    # Seed two links so the removal is observably scoped.
    r1 = await api_client.post(
        f"/api/tasks/{task.id}/knowledge-links",
        json={"wiki_page_id": str(page_a.id), "link_type": "reference"},
    )
    assert r1.status_code == 201, r1.text
    r2 = await api_client.post(
        f"/api/tasks/{task.id}/knowledge-links",
        json={"wiki_page_id": str(page_b.id), "link_type": "solution"},
    )
    assert r2.status_code == 201, r2.text

    del_resp = await api_client.delete(
        f"/api/tasks/{task.id}/knowledge-links/{page_a.id}"
    )
    assert del_resp.status_code == 204, del_resp.text

    list_resp = await api_client.get(f"/api/tasks/{task.id}/knowledge-links")
    assert list_resp.status_code == 200, list_resp.text
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["wiki_page_id"] == str(page_b.id)

    # Removing an already-removed link should surface as a 404 from the
    # service translator (``knowledge link not found``).
    second = await api_client.delete(
        f"/api/tasks/{task.id}/knowledge-links/{page_a.id}"
    )
    assert second.status_code == 404, second.text


async def test_wiki_page_deletion_cascades_knowledge_link(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    task_with_wiki: tuple[Task, WikiPage, WikiPage],
    admin_employee: Employee,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deleting a wiki page removes its task knowledge link via FK cascade."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_4", True)
    task, page_a, page_b = task_with_wiki

    for page in (page_a, page_b):
        resp = await api_client.post(
            f"/api/tasks/{task.id}/knowledge-links",
            json={"wiki_page_id": str(page.id), "link_type": "reference"},
        )
        assert resp.status_code == 201, resp.text

    await db_session.execute(delete(WikiPage).where(WikiPage.id == page_a.id))
    await db_session.flush()

    link_rows = (
        await db_session.execute(
            select(TaskKnowledgeLink).where(TaskKnowledgeLink.task_id == task.id)
        )
    ).scalars().all()
    assert len(link_rows) == 1
    assert link_rows[0].wiki_page_id == page_b.id
    assert link_rows[0].created_by_id == admin_employee.id

    list_resp = await api_client.get(f"/api/tasks/{task.id}/knowledge-links")
    assert list_resp.status_code == 200, list_resp.text
    rows = list_resp.json()
    assert len(rows) == 1
    assert rows[0]["wiki_page_id"] == str(page_b.id)


async def test_knowledge_link_disabled_returns_403(
    api_client: httpx.AsyncClient,
    task_with_wiki: tuple[Task, WikiPage, WikiPage],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With Phase 4 OFF, knowledge-link writes fail with 403; GET stays open."""
    from app.config import settings

    monkeypatch.setattr(settings, "FEATURE_AGILE_PHASE_4", False)
    task, page_a, _ = task_with_wiki

    # POST → 403 FEATURE_DISABLED.
    add_resp = await api_client.post(
        f"/api/tasks/{task.id}/knowledge-links",
        json={"wiki_page_id": str(page_a.id), "link_type": "reference"},
    )
    assert add_resp.status_code == 403, add_resp.text
    assert add_resp.json()["detail"]["code"] == "FEATURE_DISABLED"

    # DELETE → 403 FEATURE_DISABLED (gate fires before the not-found probe).
    del_resp = await api_client.delete(
        f"/api/tasks/{task.id}/knowledge-links/{page_a.id}"
    )
    assert del_resp.status_code == 403, del_resp.text
    assert del_resp.json()["detail"]["code"] == "FEATURE_DISABLED"

    # GET stays open under the OFF flag (read-only, no Phase 4 gate).
    list_resp = await api_client.get(f"/api/tasks/{task.id}/knowledge-links")
    assert list_resp.status_code == 200, list_resp.text
    assert list_resp.json() == []
