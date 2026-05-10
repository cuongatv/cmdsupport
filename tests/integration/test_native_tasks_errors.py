"""T19 — native task HTTP error contract integration tests.

Every test seeds its own CMD Support task data through the live Docker API and
asserts documented native-task HTTP errors. No Plane endpoints or env vars.
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
MAX_ATTACHMENT_BYTES = 26_214_400
UNKNOWN_UUID = "00000000-0000-0000-0000-000000000000"


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


async def _create_department(api_client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    suffix = str(time.time_ns())[-9:]
    resp = await api_client.post(
        "/api/departments",
        headers=headers,
        json={"name": f"T19 Error Dept {suffix}", "description": "T19 isolated department"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_role(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    permissions: list[str],
) -> dict[str, Any]:
    suffix = str(time.time_ns())[-9:]
    resp = await api_client.post(
        "/api/roles",
        headers=headers,
        json={
            "name": f"T19 Error Role {suffix}",
            "description": "native task error test role",
            "permissions": permissions,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_employee(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    department_id: str,
    *,
    custom_role_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    suffix = str(time.time_ns())[-9:]
    email = f"native_errors_{suffix}@cmdsupport.local"
    body: dict[str, Any] = {
        "name": f"Native Error User {suffix}",
        "email": email,
        "password": EMPLOYEE_PASSWORD,
        "role": "employee",
        "department_id": department_id,
    }
    if custom_role_id is not None:
        body["custom_role_id"] = custom_role_id

    resp = await api_client.post("/api/employees", headers=admin_headers, json=body)
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
    *,
    allow_any_employee: bool = True,
) -> dict[str, Any]:
    suffix = str(time.time_ns())[-8:]
    resp = await api_client.post(
        "/api/tasks/projects",
        headers=headers,
        json={
            "name": f"T19 Errors {suffix}",
            "description": "T19 native task error project",
            "identifier": f"E{suffix[-5:]}",
            "department_id": department_id,
            "allow_any_employee": allow_any_employee,
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


async def _create_task(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
    state_id: str,
    *,
    title: str = "T19 error task",
) -> dict[str, Any]:
    resp = await api_client.post(
        "/api/tasks",
        headers=headers,
        params={"task_project_id": project_id},
        json={
            "title": title,
            "description": "created for error contract coverage",
            "priority": "medium",
            "state_id": state_id,
            "assignee_ids": [],
            "label_ids": [],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _seed_task(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
    admin = await _admin_user(api_client, admin_headers)
    project = await _create_project(api_client, admin_headers, admin["department_id"])
    states = await _states(api_client, admin_headers, project["id"])
    by_group = {state["group"]: state for state in states}
    task = await _create_task(api_client, admin_headers, project["id"], by_group["todo"]["id"])
    return project, task, by_group


async def test_401_requires_authentication(api_client: httpx.AsyncClient) -> None:
    resp = await api_client.get("/api/tasks/status")
    assert resp.status_code == 401, resp.text


async def test_403_archived_project_rejects_attachment_mutation(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    project, task, _ = await _seed_task(api_client, admin_headers)

    archive_resp = await api_client.delete(
        f"/api/tasks/projects/{project['id']}/archive",
        headers=admin_headers,
    )
    assert archive_resp.status_code == 200, archive_resp.text

    resp = await api_client.post(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
        files={"file": ("archived.txt", b"archived", "text/plain")},
    )
    assert resp.status_code == 403, resp.text


async def test_404_task_not_found(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    resp = await api_client.get(f"/api/tasks/{UNKNOWN_UUID}", headers=admin_headers)
    assert resp.status_code == 404, resp.text


async def test_409_stale_version(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    _, task, _ = await _seed_task(api_client, admin_headers)

    ok = await api_client.patch(
        f"/api/tasks/{task['id']}",
        headers=admin_headers,
        json={"title": "fresh version", "version": task["version"]},
    )
    assert ok.status_code == 200, ok.text

    stale = await api_client.patch(
        f"/api/tasks/{task['id']}",
        headers=admin_headers,
        json={"title": "stale version", "version": task["version"]},
    )
    assert stale.status_code == 409, stale.text


async def test_410_deleted_task_is_gone(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    _, task, _ = await _seed_task(api_client, admin_headers)

    deleted = await api_client.delete(f"/api/tasks/{task['id']}", headers=admin_headers)
    assert deleted.status_code == 204, deleted.text

    resp = await api_client.get(f"/api/tasks/{task['id']}", headers=admin_headers)
    assert resp.status_code == 410, resp.text


async def test_413_oversize_attachment(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    _, task, _ = await _seed_task(api_client, admin_headers)

    oversized = b"x" * (MAX_ATTACHMENT_BYTES + 1)
    resp = await api_client.post(
        f"/api/tasks/{task['id']}/attachments",
        headers=admin_headers,
        files={"file": ("toobig.bin", oversized, "application/octet-stream")},
        timeout=120.0,
    )
    assert resp.status_code == 413, resp.text
    assert "size" in resp.text.lower()
