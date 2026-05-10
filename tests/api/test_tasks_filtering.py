from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator

import httpx
import pytest

pytestmark = pytest.mark.asyncio

BASE_URL = "http://localhost:5055"
ADMIN_EMAIL = "admin@cmdsupport.com"
ADMIN_PASSWORD = "cmd@1234"
EMPLOYEE_PASSWORD = "cmdtest123"


@pytest.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        try:
            await client.get("/", timeout=5.0)
        except httpx.HTTPError as exc:
            pytest.skip(f"Docker API not reachable at {BASE_URL}: {exc!r}")
        yield client


@pytest.fixture
async def admin_headers(api_client: httpx.AsyncClient) -> dict[str, str]:
    resp = await api_client.post(
        "/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    if resp.status_code != 200:
        pytest.skip(f"Admin login unavailable: {resp.status_code} {resp.text[:200]}")
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _admin_user(api_client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    resp = await api_client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _create_department(api_client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    suffix = str(time.time_ns())[-8:]
    resp = await api_client.post(
        "/api/departments",
        headers=headers,
        json={"name": f"T14 Department {suffix}", "description": "task filtering tests"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_role(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    permissions: list[str],
) -> dict[str, Any]:
    suffix = str(time.time_ns())[-10:]
    resp = await api_client.post(
        "/api/roles",
        headers=headers,
        json={
            "name": f"T14 Role {suffix}",
            "description": "task filtering API test role",
            "permissions": permissions,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_employee(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    department_id: str,
    custom_role_id: str | None = None,
) -> dict[str, Any]:
    suffix = str(time.time_ns())[-10:]
    resp = await api_client.post(
        "/api/employees",
        headers=headers,
        json={
            "name": f"T14 Employee {suffix}",
            "email": f"t14-{suffix}@example.test",
            "password": EMPLOYEE_PASSWORD,
            "role": "employee",
            "department_id": department_id,
            "custom_role_id": custom_role_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _login_employee(api_client: httpx.AsyncClient, email: str) -> dict[str, str]:
    resp = await api_client.post(
        "/api/auth/login",
        json={"email": email, "password": EMPLOYEE_PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _create_project(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    department_id: str | None = None,
) -> dict[str, Any]:
    if department_id is None:
        user = await _admin_user(api_client, headers)
        department_id = user["department_id"]
    suffix = str(time.time_ns())[-8:]
    resp = await api_client.post(
        "/api/tasks/projects",
        headers=headers,
        json={
            "name": f"T14 Tasks {suffix}",
            "description": "advanced filtering test project",
            "identifier": f"F{suffix[-5:]}",
            "department_id": department_id,
            "allow_any_employee": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _states(api_client: httpx.AsyncClient, headers: dict[str, str], project_id: str) -> list[dict[str, Any]]:
    resp = await api_client.get(f"/api/tasks/projects/{project_id}/states", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _state_by_group(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
    group: str,
) -> dict[str, Any]:
    states = await _states(api_client, headers, project_id)
    return next(state for state in states if state["group"] == group)


async def _create_task(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
    state_id: str,
    title: str,
    *,
    priority: str = "none",
    description: str | None = None,
    due_date: datetime | None = None,
    assignee_ids: list[str] | None = None,
) -> dict[str, Any]:
    resp = await api_client.post(
        "/api/tasks",
        headers=headers,
        params={"task_project_id": project_id},
        json={
            "title": title,
            "description": description,
            "priority": priority,
            "state_id": state_id,
            "due_date": due_date.isoformat() if due_date else None,
            "assignee_ids": assignee_ids or [],
            "label_ids": [],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_search_filter_returns_matching_tasks(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    state = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    matching = await _create_task(api_client, admin_headers, project["id"], state["id"], "Alpha Needle Task")
    await _create_task(api_client, admin_headers, project["id"], state["id"], "Beta Haystack Task")

    resp = await api_client.get(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"], "search": "needle"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert [item["id"] for item in data["items"]] == [matching["id"]]


async def test_search_filter_matches_task_description(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    state = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    matching = await _create_task(
        api_client,
        admin_headers,
        project["id"],
        state["id"],
        "Title without target term",
        description="This description contains descriptneedle only",
    )
    await _create_task(
        api_client,
        admin_headers,
        project["id"],
        state["id"],
        "Unrelated title",
        description="No matching token here",
    )

    resp = await api_client.get(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"], "search": "descriptneedle"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert [item["id"] for item in data["items"]] == [matching["id"]]


async def test_priority_filter_returns_correct_tasks(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    state = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    urgent = await _create_task(api_client, admin_headers, project["id"], state["id"], "Urgent filter task", priority="urgent")
    await _create_task(api_client, admin_headers, project["id"], state["id"], "Low filter task", priority="low")

    resp = await api_client.get(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"], "priority": "urgent"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == urgent["id"]


async def test_overdue_filter_excludes_done_cancelled(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    todo = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    done = await _state_by_group(api_client, admin_headers, project["id"], "done")
    cancelled = await _state_by_group(api_client, admin_headers, project["id"], "cancelled")
    past_due = datetime.now(timezone.utc) - timedelta(days=3)
    future_due = datetime.now(timezone.utc) + timedelta(days=3)
    open_overdue = await _create_task(api_client, admin_headers, project["id"], todo["id"], "Open overdue", due_date=past_due)
    await _create_task(api_client, admin_headers, project["id"], done["id"], "Done overdue", due_date=past_due)
    await _create_task(api_client, admin_headers, project["id"], cancelled["id"], "Cancelled overdue", due_date=past_due)
    await _create_task(api_client, admin_headers, project["id"], todo["id"], "Future task", due_date=future_due)

    resp = await api_client.get(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"], "overdue": "true"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == open_overdue["id"]


async def test_pagination_returns_correct_page(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    state = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    created = []
    for index in range(5):
        created.append(
            await _create_task(api_client, admin_headers, project["id"], state["id"], f"Paged task {index}")
        )

    resp = await api_client.get(
        "/api/tasks",
        headers=admin_headers,
        params={
            "task_project_id": project["id"],
            "page": 2,
            "page_size": 2,
            "sort_by": "created_at",
            "sort_dir": "asc",
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 5
    assert data["page"] == 2
    assert data["page_size"] == 2
    assert data["total_pages"] == 3
    assert [item["id"] for item in data["items"]] == [created[2]["id"], created[3]["id"]]


async def test_include_deleted_admin_only(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    state = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    task = await _create_task(api_client, admin_headers, project["id"], state["id"], "Deleted filter task")
    delete_resp = await api_client.delete(f"/api/tasks/{task['id']}", headers=admin_headers)
    assert delete_resp.status_code == 204, delete_resp.text

    hidden = await api_client.get("/api/tasks", headers=admin_headers, params={"task_project_id": project["id"]})
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["total"] == 0

    included = await api_client.get(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"], "include_deleted": "true"},
    )
    assert included.status_code == 200, included.text
    assert included.json()["total"] == 1
    assert included.json()["items"][0]["deleted_at"] is not None

    employee = await _create_employee(api_client, admin_headers, project["department_id"])
    employee_headers = await _login_employee(api_client, employee["email"])
    forbidden = await api_client.get(
        "/api/tasks",
        headers=employee_headers,
        params={"task_project_id": project["id"], "include_deleted": "true"},
    )
    assert forbidden.status_code == 403


async def test_inaccessible_tasks_not_returned(api_client, admin_headers):
    accessible_dept = await _create_department(api_client, admin_headers)
    inaccessible_dept = await _create_department(api_client, admin_headers)
    role = await _create_role(api_client, admin_headers, ["task:read:own_dept"])
    employee = await _create_employee(api_client, admin_headers, accessible_dept["id"], role["id"])
    employee_headers = await _login_employee(api_client, employee["email"])

    accessible_project = await _create_project(api_client, admin_headers, accessible_dept["id"])
    accessible_state = await _state_by_group(api_client, admin_headers, accessible_project["id"], "todo")
    accessible_task = await _create_task(
        api_client,
        admin_headers,
        accessible_project["id"],
        accessible_state["id"],
        "Shared scoped title",
    )

    inaccessible_project = await _create_project(api_client, admin_headers, inaccessible_dept["id"])
    inaccessible_state = await _state_by_group(api_client, admin_headers, inaccessible_project["id"], "todo")
    await _create_task(
        api_client,
        admin_headers,
        inaccessible_project["id"],
        inaccessible_state["id"],
        "Shared scoped title",
    )

    visible = await api_client.get(
        "/api/tasks",
        headers=employee_headers,
        params={"task_project_id": accessible_project["id"], "search": "Shared scoped title"},
    )
    assert visible.status_code == 200, visible.text
    assert visible.json()["total"] == 1
    assert visible.json()["items"][0]["id"] == accessible_task["id"]

    denied = await api_client.get(
        "/api/tasks",
        headers=employee_headers,
        params={"task_project_id": inaccessible_project["id"], "search": "Shared scoped title"},
    )
    assert denied.status_code == 403
