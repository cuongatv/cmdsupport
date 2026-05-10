"""T19 — full native task lifecycle integration test.

Runs against the Docker stack at ``http://localhost:5055``.  The test creates
fresh CMD Support employees/project/task data and never touches Plane APIs.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx  # pyright: ignore[reportMissingImports]
import pytest  # pyright: ignore[reportMissingImports]

pytestmark = pytest.mark.asyncio

BASE_URL = "http://localhost:5055"
ADMIN_EMAIL = "admin@cmdsupport.com"
ADMIN_PASSWORD = "cmd@1234"
EMPLOYEE_PASSWORD = "Native!Pass123"


@pytest.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
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
    *,
    name_prefix: str = "Native Lifecycle User",
) -> tuple[dict[str, Any], dict[str, str]]:
    suffix = str(time.time_ns())[-9:]
    email = f"native_lifecycle_{suffix}@cmdsupport.local"
    resp = await api_client.post(
        "/api/employees",
        headers=admin_headers,
        json={
            "name": f"{name_prefix} {suffix}",
            "email": email,
            "password": EMPLOYEE_PASSWORD,
            "role": "employee",
            "department_id": department_id,
        },
    )
    assert resp.status_code == 201, resp.text
    employee = resp.json()

    login = await api_client.post(
        "/api/auth/login",
        json={"email": email, "password": EMPLOYEE_PASSWORD},
    )
    assert login.status_code == 200, login.text
    return employee, {"Authorization": f"Bearer {login.json()['access_token']}"}


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
            "name": f"T19 Lifecycle {suffix}",
            "description": "T19 full native lifecycle project",
            "identifier": f"L{suffix[-5:]}",
            "department_id": department_id,
            "allow_any_employee": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _states(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
) -> list[dict[str, Any]]:
    resp = await api_client.get(f"/api/tasks/projects/{project_id}/states", headers=headers)
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert states
    return states


async def test_full_lifecycle(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    admin = await _admin_user(api_client, admin_headers)
    assignee = admin
    assignee_headers = admin_headers

    project = await _create_project(api_client, admin_headers, admin["department_id"])
    assert project["department_id"] == admin["department_id"]
    assert project["allow_any_employee"] is True

    states = await _states(api_client, admin_headers, project["id"])
    by_group = {state["group"]: state for state in states}
    assert {"todo", "in_progress"} <= set(by_group)

    create_resp = await api_client.post(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"]},
        json={
            "title": "T19 lifecycle task",
            "description": "created for native lifecycle coverage",
            "priority": "medium",
            "state_id": by_group["todo"]["id"],
            "assignee_ids": [],
            "label_ids": [],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    task = create_resp.json()
    assert task["task_project_id"] == project["id"]
    assert task["version"] == 1

    patch_resp = await api_client.patch(
        f"/api/tasks/{task['id']}",
        headers=admin_headers,
        json={
            "title": "T19 lifecycle task updated",
            "priority": "high",
            "version": task["version"],
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text
    task = patch_resp.json()
    assert task["title"] == "T19 lifecycle task updated"
    assert task["priority"] == "high"
    assert task["version"] == 2

    assign_resp = await api_client.post(
        f"/api/tasks/{task['id']}/assignees",
        headers=admin_headers,
        json={"employee_ids": [assignee["id"]]},
    )
    assert assign_resp.status_code == 201, assign_resp.text
    assignees = assign_resp.json()
    assert any(row["employee_id"] == assignee["id"] for row in assignees)

    mention_body = (
        f'Please review <mention id="{assignee["id"]}">@{assignee["name"]}</mention> '
        "before the move."
    )
    comment_resp = await api_client.post(
        f"/api/tasks/{task['id']}/comments",
        headers=admin_headers,
        json={"body": mention_body},
    )
    assert comment_resp.status_code == 201, comment_resp.text
    comment = comment_resp.json()
    assert comment["task_id"] == task["id"]
    assert f'<mention id="{assignee["id"]}">' in comment["body"]

    attachment_resp = await api_client.post(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
        files={"file": ("lifecycle.txt", b"native task lifecycle", "text/plain")},
    )
    assert attachment_resp.status_code == 201, attachment_resp.text
    attachment = attachment_resp.json()
    assert attachment["task_id"] == task["id"]
    assert attachment["filename"] == "lifecycle.txt"
    assert attachment["size_bytes"] == len(b"native task lifecycle")
    assert "storage_key" not in attachment

    move_resp = await api_client.post(
        f"/api/tasks/{task['id']}/move",
        headers=admin_headers,
        json={
            "state_id": by_group["in_progress"]["id"],
            "position": 2000.0,
            "version": task["version"],
        },
    )
    assert move_resp.status_code == 200, move_resp.text
    task = move_resp.json()
    assert task["state_id"] == by_group["in_progress"]["id"]
    assert task["version"] == 3

    dashboard_resp = await api_client.get(
        f"/api/tasks/projects/{project['id']}/dashboard",
        headers=admin_headers,
    )
    assert dashboard_resp.status_code == 200, dashboard_resp.text
    dashboard = dashboard_resp.json()
    assert dashboard["total_tasks"] == 1
    state_counts = {item["group"]: item["count"] for item in dashboard["by_state"]}
    assert state_counts["in_progress"] == 1
    assignee_counts = {item["employee_id"]: item["count"] for item in dashboard["by_assignee"]}
    assert assignee_counts[assignee["id"]] == 1

    activities_resp = await api_client.get(f"/api/tasks/{task['id']}/activities", headers=admin_headers)
    assert activities_resp.status_code == 200, activities_resp.text
    verbs = {item["verb"] for item in activities_resp.json()}
    assert {"title_changed", "priority_changed", "assigned", "commented", "attachment_added", "state_changed"} <= verbs
    commented = [item for item in activities_resp.json() if item["verb"] == "commented"]
    assert any(assignee["id"] in item.get("meta", {}).get("mentions", []) for item in commented)

    notifications_resp = await api_client.get(
        "/api/notifications",
        headers=assignee_headers,
        params={"unread_only": True, "limit": 50},
    )
    assert notifications_resp.status_code == 200, notifications_resp.text
    notifications = notifications_resp.json()
    target_notifications = [
        item
        for item in notifications
        if item["task_id"] == task["id"] and item["notification_type"] == "state_changed"
    ]
    assert target_notifications
    notification = target_notifications[0]
    assert notification["is_read"] is False
    assert notification["read_at"] is None

    mark_read_resp = await api_client.post(
        f"/api/notifications/{notification['id']}/read",
        headers=assignee_headers,
    )
    assert mark_read_resp.status_code == 200, mark_read_resp.text
    marked = mark_read_resp.json()
    assert marked["id"] == notification["id"]
    assert marked["is_read"] is True
    assert marked["read_at"] is not None

    delete_resp = await api_client.delete(f"/api/tasks/{task['id']}", headers=admin_headers)
    assert delete_resp.status_code == 204, delete_resp.text

    gone_resp = await api_client.get(f"/api/tasks/{task['id']}", headers=admin_headers)
    assert gone_resp.status_code == 410, gone_resp.text

    deleted_listing = await api_client.get(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"], "include_deleted": True},
    )
    assert deleted_listing.status_code == 200, deleted_listing.text
    deleted_items = [item for item in deleted_listing.json()["items"] if item["id"] == task["id"]]
    assert deleted_items
    assert deleted_items[0]["deleted_at"] is not None
