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


async def _create_project(api_client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    user = await _admin_user(api_client, headers)
    suffix = str(time.time_ns())[-8:]
    resp = await api_client.post(
        "/api/tasks/projects",
        headers=headers,
        json={
            "name": f"T15 Kanban {suffix}",
            "description": "Kanban move API test project",
            "identifier": f"K{suffix[-5:]}",
            "department_id": user["department_id"],
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
    title: str = "T15 movable task",
) -> dict[str, Any]:
    resp = await api_client.post(
        "/api/tasks",
        headers=headers,
        params={"task_project_id": project_id},
        json={
            "title": title,
            "priority": "medium",
            "state_id": state_id,
            "assignee_ids": [],
            "label_ids": [],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_move_task_to_new_state_increments_version(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    todo = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    in_progress = await _state_by_group(api_client, admin_headers, project["id"], "in_progress")
    task = await _create_task(api_client, admin_headers, project["id"], todo["id"])

    resp = await api_client.post(
        f"/api/tasks/{task['id']}/move",
        headers=admin_headers,
        json={"state_id": in_progress["id"], "position": 42.5, "version": task["version"]},
    )

    assert resp.status_code == 200, resp.text
    moved = resp.json()
    assert moved["state_id"] == in_progress["id"]
    assert moved["position"] == 42.5
    assert moved["version"] == task["version"] + 1

    activities = await api_client.get(f"/api/tasks/{task['id']}/activities", headers=admin_headers)
    assert activities.status_code == 200, activities.text
    state_changes = [item for item in activities.json() if item["verb"] == "state_changed"]
    assert state_changes
    assert state_changes[0]["meta"]["old_state"] == todo["name"]
    assert state_changes[0]["meta"]["new_state"] == in_progress["name"]


async def test_move_task_same_state_updates_position_only(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    todo = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    task = await _create_task(api_client, admin_headers, project["id"], todo["id"])

    resp = await api_client.post(
        f"/api/tasks/{task['id']}/move",
        headers=admin_headers,
        json={"state_id": todo["id"], "position": 77.25, "version": task["version"] - 1},
    )

    assert resp.status_code == 200, resp.text
    moved = resp.json()
    assert moved["state_id"] == todo["id"]
    assert moved["position"] == 77.25
    assert moved["version"] == task["version"]

    activities = await api_client.get(f"/api/tasks/{task['id']}/activities", headers=admin_headers)
    assert activities.status_code == 200, activities.text
    assert not [item for item in activities.json() if item["verb"] == "state_changed"]


async def test_move_archived_project_returns_403(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    todo = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    in_progress = await _state_by_group(api_client, admin_headers, project["id"], "in_progress")
    task = await _create_task(api_client, admin_headers, project["id"], todo["id"])

    archived = await api_client.delete(f"/api/tasks/projects/{project['id']}/archive", headers=admin_headers)
    assert archived.status_code == 200, archived.text

    resp = await api_client.post(
        f"/api/tasks/{task['id']}/move",
        headers=admin_headers,
        json={"state_id": in_progress["id"], "position": 15.0, "version": task["version"]},
    )

    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "project archived"


async def test_stale_state_move_returns_409(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    todo = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    in_progress = await _state_by_group(api_client, admin_headers, project["id"], "in_progress")
    task = await _create_task(api_client, admin_headers, project["id"], todo["id"])

    first = await api_client.patch(
        f"/api/tasks/{task['id']}",
        headers=admin_headers,
        json={"title": "version bump before stale move", "version": task["version"]},
    )
    assert first.status_code == 200, first.text

    stale = await api_client.post(
        f"/api/tasks/{task['id']}/move",
        headers=admin_headers,
        json={"state_id": in_progress["id"], "position": 30.0, "version": task["version"]},
    )

    assert stale.status_code == 409, stale.text
