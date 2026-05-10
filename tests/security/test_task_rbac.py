from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

pytestmark = pytest.mark.asyncio

BASE_URL = "http://localhost:5055"
ADMIN_EMAIL = "admin@cmdsupport.com"
ADMIN_PASSWORD = "cmd@1234"
EMPLOYEE_PASSWORD = "cmdtest123"


@pytest.fixture
async def api_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
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


async def _create_department(api_client: httpx.AsyncClient, headers: dict[str, str]) -> dict[str, Any]:
    suffix = str(time.time_ns())[-9:]
    resp = await api_client.post(
        "/api/departments",
        headers=headers,
        json={"name": f"T31 Security Dept {suffix}", "description": "task security tests"},
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
            "name": f"T31 Security Role {suffix}",
            "description": "task security test role",
            "permissions": permissions,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_employee(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    department_id: str,
    *,
    custom_role_id: str | None = None,
) -> dict[str, Any]:
    suffix = str(time.time_ns())[-10:]
    body: dict[str, Any] = {
        "name": f"T31 Employee {suffix}",
        "email": f"t31-{suffix}@example.test",
        "password": EMPLOYEE_PASSWORD,
        "role": "employee",
        "department_id": department_id,
    }
    if custom_role_id is not None:
        body["custom_role_id"] = custom_role_id

    resp = await api_client.post("/api/employees", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _login_employee(api_client: httpx.AsyncClient, email: str) -> dict[str, str]:
    last_resp: httpx.Response | None = None
    for _ in range(10):
        last_resp = await api_client.post(
            "/api/auth/login",
            json={"email": email, "password": EMPLOYEE_PASSWORD},
        )
        if last_resp.status_code == 200:
            return {"Authorization": f"Bearer {last_resp.json()['access_token']}"}
        await asyncio.sleep(0.2)
    assert last_resp is not None
    assert last_resp.status_code == 200, last_resp.text
    raise AssertionError("employee login failed")


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
            "name": f"T31 Tasks {suffix}",
            "description": "task security project",
            "identifier": f"S{suffix[-5:]}",
            "department_id": department_id,
            "allow_any_employee": allow_any_employee,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _state_by_group(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
    group: str,
) -> dict[str, Any]:
    resp = await api_client.get(f"/api/tasks/projects/{project_id}/states", headers=headers)
    assert resp.status_code == 200, resp.text
    return next(state for state in resp.json() if state["group"] == group)


async def _create_task(
    api_client: httpx.AsyncClient,
    headers: dict[str, str],
    project_id: str,
    state_id: str,
    title: str = "T31 security task",
    *,
    assignee_ids: list[str] | None = None,
) -> dict[str, Any]:
    resp = await api_client.post(
        "/api/tasks",
        headers=headers,
        params={"task_project_id": project_id},
        json={
            "title": title,
            "description": "created for task security hardening coverage",
            "priority": "medium",
            "state_id": state_id,
            "assignee_ids": assignee_ids or [],
            "label_ids": [],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_cross_department_employee_cannot_list_tasks_or_infer_hidden_count(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    visible_dept = await _create_department(api_client, admin_headers)
    hidden_dept = await _create_department(api_client, admin_headers)
    await asyncio.sleep(0.2)
    role = await _create_role(api_client, admin_headers, ["task:read:own_dept"])
    employee = await _create_employee(api_client, admin_headers, visible_dept["id"], custom_role_id=role["id"])
    employee_headers = await _login_employee(api_client, employee["email"])

    visible_project = await _create_project(api_client, admin_headers, visible_dept["id"])
    visible_state = await _state_by_group(api_client, admin_headers, visible_project["id"], "todo")
    visible_task = await _create_task(
        api_client,
        admin_headers,
        visible_project["id"],
        visible_state["id"],
        "T31 same search title",
    )

    hidden_project = await _create_project(api_client, admin_headers, hidden_dept["id"])
    hidden_state = await _state_by_group(api_client, admin_headers, hidden_project["id"], "todo")
    await _create_task(
        api_client,
        admin_headers,
        hidden_project["id"],
        hidden_state["id"],
        "T31 same search title",
    )

    visible = await api_client.get(
        "/api/tasks",
        headers=employee_headers,
        params={"task_project_id": visible_project["id"], "search": "T31 same search title"},
    )
    assert visible.status_code == 200, visible.text
    assert visible.json()["total"] == 1
    assert visible.json()["items"][0]["id"] == visible_task["id"]

    hidden = await api_client.get(
        "/api/tasks",
        headers=employee_headers,
        params={"task_project_id": hidden_project["id"], "search": "T31 same search title"},
    )
    assert hidden.status_code in (200, 403), hidden.text
    if hidden.status_code == 200:
        assert hidden.json()["total"] == 0
        assert hidden.json()["items"] == []
    else:
        assert "T31 same search title" not in hidden.text
        assert "total" not in hidden.text.lower()

    read_hidden = await api_client.get(f"/api/tasks/{visible_task['id']}", headers=employee_headers)
    assert read_hidden.status_code == 200, read_hidden.text


async def test_inactive_employee_cannot_be_newly_assigned(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    dept = await _create_department(api_client, admin_headers)
    await asyncio.sleep(0.2)
    inactive = await _create_employee(api_client, admin_headers, dept["id"])
    toggle = await api_client.patch(f"/api/employees/{inactive['id']}/toggle", headers=admin_headers)
    assert toggle.status_code == 200, toggle.text
    assert toggle.json()["is_active"] is False

    project = await _create_project(api_client, admin_headers, dept["id"], allow_any_employee=True)
    state = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    resp = await api_client.post(
        "/api/tasks",
        headers=admin_headers,
        params={"task_project_id": project["id"]},
        json={
            "title": "T31 inactive assignee create",
            "priority": "medium",
            "state_id": state["id"],
            "assignee_ids": [inactive["id"]],
            "label_ids": [],
        },
    )

    assert resp.status_code == 400, resp.text
    assert "inactive" in resp.text.lower()
    assert "traceback" not in resp.text.lower()


async def test_archived_project_mutation_returns_403(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    dept = await _create_department(api_client, admin_headers)
    await asyncio.sleep(0.2)
    project = await _create_project(api_client, admin_headers, dept["id"])
    todo = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    in_progress = await _state_by_group(api_client, admin_headers, project["id"], "in_progress")
    task = await _create_task(api_client, admin_headers, project["id"], todo["id"])

    archived = await api_client.delete(f"/api/tasks/projects/{project['id']}/archive", headers=admin_headers)
    assert archived.status_code == 200, archived.text

    resp = await api_client.post(
        f"/api/tasks/{task['id']}/move",
        headers=admin_headers,
        json={"state_id": in_progress["id"], "position": 33.0, "version": task["version"]},
    )

    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "project archived"
    assert "traceback" not in resp.text.lower()


async def test_stale_version_conflict_on_task_patch(
    api_client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    dept = await _create_department(api_client, admin_headers)
    await asyncio.sleep(0.2)
    project = await _create_project(api_client, admin_headers, dept["id"])
    state = await _state_by_group(api_client, admin_headers, project["id"], "todo")
    task = await _create_task(api_client, admin_headers, project["id"], state["id"])

    ok = await api_client.patch(
        f"/api/tasks/{task['id']}",
        headers=admin_headers,
        json={"title": "T31 fresh update", "version": task["version"]},
    )
    assert ok.status_code == 200, ok.text

    stale = await api_client.patch(
        f"/api/tasks/{task['id']}",
        headers=admin_headers,
        json={"title": "T31 stale update", "version": task["version"]},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"] == "version conflict"
    assert "expected" not in stale.text.lower()
    assert "traceback" not in stale.text.lower()
