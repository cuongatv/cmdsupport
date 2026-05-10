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
            "name": f"API Tasks {suffix}",
            "description": "T13 integration test project",
            "identifier": f"T{suffix[-5:]}",
            "department_id": user["department_id"],
            "allow_any_employee": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _default_state(api_client: httpx.AsyncClient, headers: dict[str, str], project_id: str) -> dict[str, Any]:
    resp = await api_client.get(f"/api/tasks/projects/{project_id}/states", headers=headers)
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert states
    return states[0]


async def _create_task(api_client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    project = await _create_project(api_client, headers)
    state = await _default_state(api_client, headers, project["id"])
    resp = await api_client.post(
        "/api/tasks",
        headers=headers,
        params={"task_project_id": project["id"]},
        json={
            "title": "T13 API task",
            "description": "created by API integration test",
            "priority": "medium",
            "state_id": state["id"],
            "assignee_ids": [],
            "label_ids": [],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_task_project_returns_201(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    assert project["id"]
    assert project["identifier"].startswith("T")
    assert project["is_archived"] is False


async def test_create_task_returns_201_with_audit_row(api_client, admin_headers):
    project = await _create_project(api_client, admin_headers)
    state = await _default_state(api_client, admin_headers, project["id"])

    resp = await api_client.post(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"]},
        json={
            "title": "Task with audit row",
            "priority": "high",
            "state_id": state["id"],
            "assignee_ids": [],
            "label_ids": [],
        },
    )

    assert resp.status_code == 201, resp.text
    task = resp.json()
    assert task["title"] == "Task with audit row"

    audit = await api_client.get(
        "/api/audit/log",
        headers=admin_headers,
        params={"resource_type": "task", "action": "create", "page_size": 20},
    )
    assert audit.status_code == 200, audit.text
    assert any(item["resource_id"] == task["id"] for item in audit.json()["items"])


async def test_patch_task_returns_409_on_stale_version(api_client, admin_headers):
    task = await _create_task(api_client, admin_headers)

    ok = await api_client.patch(
        f"/api/tasks/{task['id']}",
        headers=admin_headers,
        json={"title": "fresh update", "version": task["version"]},
    )
    assert ok.status_code == 200, ok.text

    stale = await api_client.patch(
        f"/api/tasks/{task['id']}",
        headers=admin_headers,
        json={"title": "stale update", "version": task["version"]},
    )
    assert stale.status_code == 409, stale.text


async def test_list_tasks_requires_task_project_id(api_client, admin_headers):
    resp = await api_client.get("/api/tasks", headers=admin_headers)
    assert resp.status_code == 422


async def test_create_comment_returns_201(api_client, admin_headers):
    task = await _create_task(api_client, admin_headers)
    resp = await api_client.post(
        f"/api/tasks/{task['id']}/comments",
        headers=admin_headers,
        json={"body": "first API comment"},
    )
    assert resp.status_code == 201, resp.text
    comment = resp.json()
    assert comment["task_id"] == task["id"]
    assert comment["body"] == "first API comment"
    assert comment["deleted_at"] is None


async def test_status_endpoint_still_works(api_client, admin_headers):
    resp = await api_client.get("/api/tasks/status", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"native": True}
