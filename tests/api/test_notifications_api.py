from __future__ import annotations

import time
from typing import Any, AsyncIterator

import httpx
import pytest

pytestmark = pytest.mark.asyncio

BASE_URL = "http://localhost:5055"
ADMIN_EMAIL = "admin@cmdsupport.com"
ADMIN_PASSWORD = "cmd@1234"


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


async def _create_employee(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    department_id: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Create a fresh employee and return (user_record, auth_headers)."""
    suffix = str(time.time_ns())[-9:]
    email = f"notif_user_{suffix}@cmdsupport.local"
    password = "Notif!Pass123"
    resp = await api_client.post(
        "/api/employees",
        headers=admin_headers,
        json={
            "name": f"Notif User {suffix}",
            "email": email,
            "password": password,
            "role": "employee",
            "department_id": department_id,
        },
    )
    assert resp.status_code == 201, resp.text
    user = resp.json()

    login = await api_client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return user, headers


async def _create_project(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    department_id: str,
) -> dict[str, Any]:
    suffix = str(time.time_ns())[-8:]
    resp = await api_client.post(
        "/api/tasks/projects",
        headers=headers,
        json={
            "name": f"Notif Project {suffix}",
            "description": "T17 notification API test project",
            "identifier": f"N{suffix[-5:]}",
            "department_id": department_id,
            "allow_any_employee": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _states(
    api_client: httpx.AsyncClient, headers: dict[str, str], project_id: str
) -> list[dict[str, Any]]:
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


async def _create_task_with_assignees(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
    state_id: str,
    assignee_ids: list[str],
    title: str = "T17 notification task",
) -> dict[str, Any]:
    resp = await api_client.post(
        "/api/tasks",
        headers=headers,
        params={"task_project_id": project_id},
        json={
            "title": title,
            "priority": "medium",
            "state_id": state_id,
            "assignee_ids": assignee_ids,
            "label_ids": [],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _move_task(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    task_id: str,
    new_state_id: str,
    version: int,
    position: float = 1.0,
) -> dict[str, Any]:
    resp = await api_client.post(
        f"/api/tasks/{task_id}/move",
        headers=headers,
        json={"state_id": new_state_id, "position": position, "version": version},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _trigger_state_change_notifications(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    department_id: str,
    assignee_ids: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create a project + task assigned to ``assignee_ids`` and move it,
    producing one ``state_changed`` notification per active assignee.

    Returns (project, task_after_move).
    """
    project = await _create_project(api_client, admin_headers, department_id)
    todo = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    in_progress = await _state_by_group(
        api_client, admin_headers, project["id"], "in_progress"
    )
    task = await _create_task_with_assignees(
        api_client,
        admin_headers,
        project["id"],
        todo["id"],
        assignee_ids=assignee_ids,
    )
    moved = await _move_task(
        api_client,
        admin_headers,
        task["id"],
        in_progress["id"],
        version=task["version"],
    )
    return project, moved


async def test_list_notifications_returns_current_user_only(api_client, admin_headers):
    admin = await _admin_user(api_client, admin_headers)
    employee, employee_headers = await _create_employee(
        api_client, admin_headers, admin["department_id"]
    )

    _, task = await _trigger_state_change_notifications(
        api_client,
        admin_headers,
        admin["department_id"],
        assignee_ids=[admin["id"], employee["id"]],
    )

    admin_resp = await api_client.get(
        "/api/notifications", headers=admin_headers, params={"limit": 50}
    )
    assert admin_resp.status_code == 200, admin_resp.text
    admin_items = admin_resp.json()
    assert all(item["recipient_id"] == admin["id"] for item in admin_items)
    assert any(
        item["task_id"] == task["id"]
        and item["notification_type"] == "state_changed"
        for item in admin_items
    )

    emp_resp = await api_client.get(
        "/api/notifications", headers=employee_headers, params={"limit": 50}
    )
    assert emp_resp.status_code == 200, emp_resp.text
    emp_items = emp_resp.json()
    assert emp_items, "employee should see at least their own state_changed notification"
    assert all(item["recipient_id"] == employee["id"] for item in emp_items)
    assert all(item["recipient_id"] != admin["id"] for item in emp_items)
    assert any(
        item["task_id"] == task["id"]
        and item["notification_type"] == "state_changed"
        for item in emp_items
    )


async def test_mark_one_read_sets_read_at(api_client, admin_headers):
    admin = await _admin_user(api_client, admin_headers)
    _, task = await _trigger_state_change_notifications(
        api_client,
        admin_headers,
        admin["department_id"],
        assignee_ids=[admin["id"]],
    )

    listing = await api_client.get(
        "/api/notifications",
        headers=admin_headers,
        params={"unread_only": True, "limit": 50},
    )
    assert listing.status_code == 200, listing.text
    candidates = [item for item in listing.json() if item["task_id"] == task["id"]]
    assert candidates, "expected an unread state_changed notification for this task"
    target = candidates[0]
    assert target["is_read"] is False
    assert target["read_at"] is None

    marked = await api_client.post(
        f"/api/notifications/{target['id']}/read", headers=admin_headers
    )
    assert marked.status_code == 200, marked.text
    body = marked.json()
    assert body["id"] == target["id"]
    assert body["is_read"] is True
    assert body["read_at"] is not None


async def test_mark_all_read_current_user_only(api_client, admin_headers):
    admin = await _admin_user(api_client, admin_headers)
    employee, employee_headers = await _create_employee(
        api_client, admin_headers, admin["department_id"]
    )

    _, task = await _trigger_state_change_notifications(
        api_client,
        admin_headers,
        admin["department_id"],
        assignee_ids=[admin["id"], employee["id"]],
    )

    employee_before = await api_client.get(
        "/api/notifications/unread-count", headers=employee_headers
    )
    assert employee_before.status_code == 200, employee_before.text
    employee_before_count = employee_before.json()["count"]
    assert employee_before_count >= 1

    mark_all = await api_client.post("/api/notifications/read-all", headers=admin_headers)
    assert mark_all.status_code == 200, mark_all.text
    assert mark_all.json()["updated"] >= 1

    admin_after = await api_client.get(
        "/api/notifications/unread-count", headers=admin_headers
    )
    assert admin_after.status_code == 200, admin_after.text
    assert admin_after.json()["count"] == 0

    employee_after = await api_client.get(
        "/api/notifications/unread-count", headers=employee_headers
    )
    assert employee_after.status_code == 200, employee_after.text
    assert employee_after.json()["count"] == employee_before_count

    employee_unread = await api_client.get(
        "/api/notifications",
        headers=employee_headers,
        params={"unread_only": True, "limit": 50},
    )
    assert employee_unread.status_code == 200, employee_unread.text
    employee_items = employee_unread.json()
    assert any(item["task_id"] == task["id"] for item in employee_items)
    assert all(item["is_read"] is False for item in employee_items)


async def test_unread_count_endpoint(api_client, admin_headers):
    admin = await _admin_user(api_client, admin_headers)

    reset = await api_client.post("/api/notifications/read-all", headers=admin_headers)
    assert reset.status_code == 200, reset.text

    baseline = await api_client.get(
        "/api/notifications/unread-count", headers=admin_headers
    )
    assert baseline.status_code == 200, baseline.text
    assert baseline.json()["count"] == 0

    for index in range(2):
        await _trigger_state_change_notifications(
            api_client,
            admin_headers,
            admin["department_id"],
            assignee_ids=[admin["id"]],
        )

    after_create = await api_client.get(
        "/api/notifications/unread-count", headers=admin_headers
    )
    assert after_create.status_code == 200, after_create.text
    assert after_create.json()["count"] == 2

    listing = await api_client.get(
        "/api/notifications",
        headers=admin_headers,
        params={"unread_only": True, "limit": 50},
    )
    assert listing.status_code == 200, listing.text
    items = listing.json()
    assert len(items) >= 2

    marked = await api_client.post(
        f"/api/notifications/{items[0]['id']}/read", headers=admin_headers
    )
    assert marked.status_code == 200, marked.text

    after_one = await api_client.get(
        "/api/notifications/unread-count", headers=admin_headers
    )
    assert after_one.status_code == 200, after_one.text
    assert after_one.json()["count"] == 1
