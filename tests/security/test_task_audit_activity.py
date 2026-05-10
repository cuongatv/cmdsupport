from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.asyncio

BASE_URL = "http://localhost:5055"
ADMIN_EMAIL = "admin@cmdsupport.com"
ADMIN_PASSWORD = "cmd@1234"


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


async def _create_project(api_client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    user = await _admin_user(api_client, headers)
    suffix = str(time.time_ns())[-8:]
    resp = await api_client.post(
        "/api/tasks/projects",
        headers=headers,
        json={
            "name": f"T31 Audit {suffix}",
            "description": "task audit/activity security project",
            "identifier": f"A{suffix[-5:]}",
            "department_id": user["department_id"],
            "allow_any_employee": True,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _states(api_client: httpx.AsyncClient, headers: dict[str, str], project_id: str) -> list[dict[str, Any]]:
    resp = await api_client.get(f"/api/tasks/projects/{project_id}/states", headers=headers)
    assert resp.status_code == 200, resp.text
    states = resp.json()
    assert states
    return states


async def _state_by_group(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
    group: str,
) -> dict[str, Any]:
    return next(state for state in await _states(api_client, headers, project_id) if state["group"] == group)


async def _create_task(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
    state_id: str,
    title: str = "T31 audit task",
) -> dict[str, Any]:
    resp = await api_client.post(
        "/api/tasks",
        headers=headers,
        params={"task_project_id": project_id},
        json={
            "title": title,
            "description": "created for audit/activity coverage",
            "priority": "medium",
            "state_id": state_id,
            "assignee_ids": [],
            "label_ids": [],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _audit_contains(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    *,
    action: str,
    resource_type: str,
    resource_id: str,
) -> bool:
    resp = await api_client.get(
        "/api/audit/log",
        headers=headers,
        params={"action": action, "resource_type": resource_type, "page_size": 100},
    )
    assert resp.status_code == 200, resp.text
    return any(item["resource_id"] == resource_id for item in resp.json()["items"])


async def _activity_verbs(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    task_id: str,
) -> set[str]:
    resp = await api_client.get(f"/api/tasks/{task_id}/activities", headers=headers)
    assert resp.status_code == 200, resp.text
    return {item["verb"] for item in resp.json()}


async def test_task_create_mutation_creates_audit_log_row(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    project = await _create_project(api_client, admin_headers)
    state = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    task = await _create_task(api_client, admin_headers, project["id"], state["id"], "T31 audit create")

    assert await _audit_contains(
        api_client,
        admin_headers,
        action="create",
        resource_type="task",
        resource_id=task["id"],
    )


async def test_task_update_mutation_creates_audit_log_and_activity_row(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    project = await _create_project(api_client, admin_headers)
    state = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    task = await _create_task(api_client, admin_headers, project["id"], state["id"])

    resp = await api_client.patch(
        f"/api/tasks/{task['id']}",
        headers=admin_headers,
        json={"title": "T31 audit updated", "priority": "high", "version": task["version"]},
    )
    assert resp.status_code == 200, resp.text

    assert await _audit_contains(
        api_client,
        admin_headers,
        action="update",
        resource_type="task",
        resource_id=task["id"],
    )
    verbs = await _activity_verbs(api_client, admin_headers, task["id"])
    assert {"title_changed", "priority_changed"} <= verbs


async def test_task_state_change_move_creates_audit_log_and_activity_row(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    project = await _create_project(api_client, admin_headers)
    todo = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    in_progress = await _state_by_group(api_client, admin_headers, project["id"], "in_progress")
    task = await _create_task(api_client, admin_headers, project["id"], todo["id"])

    resp = await api_client.post(
        f"/api/tasks/{task['id']}/move",
        headers=admin_headers,
        json={"state_id": in_progress["id"], "position": 20.0, "version": task["version"]},
    )
    assert resp.status_code == 200, resp.text

    assert await _audit_contains(
        api_client,
        admin_headers,
        action="move",
        resource_type="task",
        resource_id=task["id"],
    )
    assert "state_changed" in await _activity_verbs(api_client, admin_headers, task["id"])


async def test_comment_creation_creates_audit_log_and_activity_row(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    project = await _create_project(api_client, admin_headers)
    state = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    task = await _create_task(api_client, admin_headers, project["id"], state["id"])

    resp = await api_client.post(
        f"/api/tasks/{task['id']}/comments",
        headers=admin_headers,
        json={"body": "T31 audited comment"},
    )
    assert resp.status_code == 201, resp.text
    comment = resp.json()

    assert await _audit_contains(
        api_client,
        admin_headers,
        action="create",
        resource_type="task_comment",
        resource_id=comment["id"],
    )
    assert "commented" in await _activity_verbs(api_client, admin_headers, task["id"])


async def test_attachment_upload_creates_audit_log_activity_and_hides_storage_key(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    project = await _create_project(api_client, admin_headers)
    state = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    task = await _create_task(api_client, admin_headers, project["id"], state["id"])

    upload = await api_client.post(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
        files={"file": ("audit.txt", b"T31 audit attachment", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()
    assert "storage_key" not in attachment

    listed = await api_client.get(f"/api/tasks/{task['id']}/attachments", headers=admin_headers)
    assert listed.status_code == 200, listed.text
    assert listed.json()
    assert all("storage_key" not in item for item in listed.json())

    download = await api_client.get(
        f"/api/tasks/{task['id']}/attachments/{attachment['id']}/download",
        headers=admin_headers,
    )
    assert download.status_code == 200, download.text
    assert "storage_key" not in download.json()

    assert await _audit_contains(
        api_client,
        admin_headers,
        action="create",
        resource_type="task_attachment",
        resource_id=attachment["id"],
    )
    assert "attachment_added" in await _activity_verbs(api_client, admin_headers, task["id"])


async def test_task_delete_mutation_creates_audit_log_row(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    project = await _create_project(api_client, admin_headers)
    state = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    task = await _create_task(api_client, admin_headers, project["id"], state["id"])

    resp = await api_client.delete(f"/api/tasks/{task['id']}", headers=admin_headers)
    assert resp.status_code == 204, resp.text

    assert await _audit_contains(
        api_client,
        admin_headers,
        action="delete",
        resource_type="task",
        resource_id=task["id"],
    )
